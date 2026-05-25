from __future__ import annotations

import json
import re
from typing import Any, Generator

import ollama

from celestia_core.config import get
from celestia_core.personality import build_system_prompt
from skills.registry import execute_tool, tool_schemas

# Cached Ollama client — rebuilt if the host or timeout config changes.
_ollama_client_cache: dict[str, ollama.Client] = {}


def _ollama_client() -> ollama.Client:
    """Return a cached Ollama client with the configured host and request timeout."""
    host = get("llm.host", "http://127.0.0.1:11434")
    timeout = float(get("llm.request_timeout_seconds", 60))
    key = f"{host}:{timeout}"
    if key not in _ollama_client_cache:
        _ollama_client_cache.clear()
        _ollama_client_cache[key] = ollama.Client(host=host, timeout=timeout)
    return _ollama_client_cache[key]

_GREETING_ONLY = re.compile(
    r"^(hi|hello|hey|yo|sup|howdy|good\s+(morning|afternoon|evening)|what'?s\s+up)[\s!.,?]*$",
    re.I,
)
_FALSE_SUCCESS = re.compile(
    r"\b(i\s+)?(have\s+)?(opened|launched|started|visited|navigated to)\b",
    re.I,
)
_FAKE_NARRATION = re.compile(
    r"\[.*\bopens?\b.*\]|^opening url:",
    re.I | re.M,
)


def _user_id() -> str:
    return get("app.user_id", "atlas_user")


def _needs_memory(query: str) -> bool:
    mode = get("memory.inject", "smart").lower()
    if mode == "always":
        return not _GREETING_ONLY.match(query.strip())
    if mode == "off":
        return False

    q = query.strip().lower()
    if _GREETING_ONLY.match(q):
        return False
    if any(
        k in q
        for k in (
            "remember",
            "memory",
            "memories",
            "favorite",
            "prefer",
            "what is my",
            "what's my",
            "what do you know",
            "recall",
            "forget",
            "delete",
            "update",
            "change my",
            "my color",
            "my theme",
            "about me",
            "stored",
            "you know",
        )
    ):
        return True
    if "?" in q and any(k in q for k in ("my ", "me ", "i ", "mine")):
        return True
    return False


def _memory_context(query: str) -> str:
    if not get("memory.enabled", True):
        return ""
    try:
        from skills.memory.store import build_context

        return build_context(query, _user_id())
    except Exception:
        return ""


def _parse_tool_args(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        return json.loads(raw) if raw else {}
    return {}


def _message_to_dict(msg: Any) -> dict[str, Any]:
    """Plain dict for JSON session store (ollama returns Message objects)."""
    if isinstance(msg, dict):
        data = dict(msg)
    elif hasattr(msg, "model_dump"):
        data = msg.model_dump(exclude_none=True)
    else:
        raise TypeError(f"Cannot serialize chat message: {type(msg)!r}")

    out: dict[str, Any] = {"role": str(data.get("role") or "assistant")}
    content = data.get("content")
    if content is not None:
        out["content"] = content if isinstance(content, str) else str(content)
    name = data.get("name")
    if name:
        out["name"] = str(name)
    tool_calls = data.get("tool_calls")
    if tool_calls:
        serializable: list[dict[str, Any]] = []
        for tc in tool_calls:
            if hasattr(tc, "model_dump"):
                serializable.append(tc.model_dump(exclude_none=True))
            elif isinstance(tc, dict):
                serializable.append(tc)
        if serializable:
            out["tool_calls"] = serializable
    return out


def _normalize_history(history: list[Any] | None) -> list[dict[str, Any]] | None:
    if not history:
        return None
    return [_message_to_dict(m) for m in history]


def _trim_session_messages(messages: list[Any]) -> list[dict[str, Any]]:
    normalized = [_message_to_dict(m) for m in messages]
    max_msgs = int(get("chat.session_max_messages", 60))
    if len(normalized) <= max_msgs:
        return normalized
    head: list[dict[str, Any]] = []
    tail: list[dict[str, Any]] = []
    for m in normalized:
        if m.get("role") == "system" and not tail:
            head.append(m)
        else:
            tail.append(m)
    keep = max(max_msgs - len(head), 10)
    return head + tail[-keep:]


def _pc_control_hints(user_message: str) -> list[dict[str, Any]]:
    from celestia_core import security
    from celestia_core.open_dispatch import extract_url

    hints: list[dict[str, Any]] = []
    msg_low = user_message.lower()
    mode = security.get_mode()
    url = extract_url(user_message)

    if mode == "safe":
        hints.append(
            {
                "role": "system",
                "content": (
                    "PC control is SAFE (off). You cannot open apps, URLs, or files. "
                    "Do NOT say you opened, launched, or visited anything. "
                    "Tell the user to use scope scoped, arm, or the direct command: open https://…"
                ),
            }
        )
    elif mode == "scoped":
        hints.append(
            {
                "role": "system",
                "content": (
                    "PC control is SCOPED: open_path for allowlisted apps (notepad, calc, …); "
                    "file_read/write only under workspace folders. "
                    "For web links use open_url (only hosts on url_allowlist). "
                    "Never pass a URL to open_path. No PowerShell, no System32."
                ),
            }
        )
    elif mode == "armed":
        hints.append(
            {
                "role": "system",
                "content": (
                    "PC control is ARMED. For http(s) links use open_url with the URL only. "
                    "For apps/files use open_path. Report Blocked messages honestly."
                ),
            }
        )

    if url:
        hints.append(
            {
                "role": "system",
                "content": (
                    f"User wants a browser link. Call open_url with url={url!r} only. "
                    "Do NOT use open_path for URLs. "
                    "Never describe opening in brackets like [site opens] — call the tool or say you cannot."
                ),
            }
        )
    elif any(
        t in msg_low
        for t in ("open ", "launch ", "start ", "notepad", "not defteri", "calc", "explorer")
    ):
        hints.append(
            {
                "role": "system",
                "content": (
                    "User asked to open/launch something (not a URL). Call open_path with app name "
                    "(e.g. notepad). Do not only chat — call the tool, then confirm from its result."
                ),
            }
        )
    return hints


def _honest_reply(messages: list[dict[str, Any]], text: str) -> str:
    """If tools were blocked but the model claims success, append the real tool result."""
    blocked: list[str] = []
    seen_user = False
    for m in reversed(messages):
        if m.get("role") == "user":
            if not seen_user:
                seen_user = True
                continue
            break
        if seen_user and m.get("role") == "tool":
            body = str(m.get("content") or "")
            if body.startswith("Blocked:"):
                blocked.append(body)

    open_ok = any(
        m.get("role") == "tool"
        and m.get("name") == "open_url"
        and not str(m.get("content") or "").startswith("Blocked:")
        for m in messages
    )

    if not blocked and not (_FALSE_SUCCESS.search(text) or _FAKE_NARRATION.search(text)):
        return text
    if open_ok and "block" not in text.lower():
        return text

    low = text.lower()
    if blocked and (
        "block" in low
        or "could not" in low
        or "did not open" in low
        or "can't open" in low
    ):
        return text
    if blocked:
        return f"{text}\n\n(Tool result: {blocked[-1]})"
    if _FALSE_SUCCESS.search(text) or _FAKE_NARRATION.search(text):
        return (
            f"{text}\n\n(I did not run a successful open — nothing was opened. "
            "Try: open https://github.com or ask again.)"
        )
    return text


def _strip_ephemeral(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove per-turn system messages (mode hints, memory context) from stored history.

    Only the first system message (personality prompt) is kept. All subsequent
    system messages are ephemeral injections that must be rebuilt fresh each turn
    — storing them wastes the session context budget.
    """
    result: list[dict[str, Any]] = []
    passed_first_user = False
    for m in messages:
        role = m.get("role", "")
        if role == "system":
            if not passed_first_user:
                result.append(m)  # keep personality prompt; skip repeated hints
        else:
            if role == "user":
                passed_first_user = True
            result.append(m)
    return result


def _build_fresh_messages(user_message: str) -> list[dict[str, Any]]:
    mem_ctx = _memory_context(user_message)
    messages: list[dict[str, Any]] = [{"role": "system", "content": build_system_prompt()}]
    messages.extend(_pc_control_hints(user_message))
    if mem_ctx:
        messages.append({"role": "system", "content": mem_ctx})
    messages.append({"role": "user", "content": user_message})
    return messages


def run_turn(
    user_message: str,
    *,
    speak: bool = False,
    max_tool_rounds: int = 8,
    source: str = "cli",
    history: list[dict[str, Any]] | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    uid = _user_id()
    model = get("llm.chat_model", "llama3.2:3b")

    from celestia_core.security import preflight_chat_pc

    early = preflight_chat_pc(user_message)
    if early:
        if history is not None:
            messages = _normalize_history(history) or []
            messages.append({"role": "user", "content": user_message})
            messages.append({"role": "assistant", "content": early})
            return early, _trim_session_messages(_strip_ephemeral(messages))
        messages = _build_fresh_messages(user_message)
        messages.append({"role": "assistant", "content": early})
        return early, _trim_session_messages(_strip_ephemeral(messages))

    mem_ctx = _memory_context(user_message)

    if history:
        messages = _normalize_history(history) or []
        for hint in _pc_control_hints(user_message):
            messages.append(hint)
        if mem_ctx:
            messages.append({"role": "system", "content": mem_ctx})
        messages.append({"role": "user", "content": user_message})
    else:
        messages = _build_fresh_messages(user_message)

    client = _ollama_client()
    for _ in range(max_tool_rounds):
        try:
            response = client.chat(
                model=model,
                messages=messages,
                tools=tool_schemas(user_message),
                options={"num_predict": 1024},
            )
        except Exception as e:
            err = f"LLM error: {e}"
            messages.append({"role": "assistant", "content": err})
            return err, _trim_session_messages(_strip_ephemeral(messages))

        msg = _message_to_dict(response["message"])
        messages.append(msg)

        tool_calls = msg.get("tool_calls") or []
        if not tool_calls:
            text = _honest_reply(messages, (msg.get("content") or "").strip())
            if speak and text:
                try:
                    from skills.tts import speak as tts_speak

                    tts_speak(text)
                except Exception as e:
                    print(f"[warn] TTS: {e}")
            return text, _trim_session_messages(_strip_ephemeral(messages))

        for tc in tool_calls:
            fn = tc.get("function") or {}
            name = fn.get("name", "")
            args = _parse_tool_args(fn.get("arguments"))
            result = execute_tool(name, args, uid, source=source)
            messages.append({"role": "tool", "content": result, "name": name})

    return "Stopped: too many tool rounds.", _trim_session_messages(_strip_ephemeral(messages))


def run_turn_stream(
    user_message: str,
    *,
    source: str = "cli",
    history: list[dict[str, Any]] | None = None,
    max_tool_rounds: int = 8,
) -> Generator[dict[str, Any], None, None]:
    """Generator that yields token events then a final done/error event.

    Yields one of:
        {"token": str}                                                — per Ollama chunk
        {"done": True, "reply": str, "messages": list[dict]}         — completion
        {"error": str}                                                — LLM failure

    Tool-call turns are handled synchronously (non-streaming) so the caller
    always receives a clean done event with the full message history.
    """
    uid = _user_id()
    model = get("llm.chat_model", "llama3.2:3b")

    from celestia_core.security import preflight_chat_pc

    early = preflight_chat_pc(user_message)
    if early:
        if history is not None:
            messages = _normalize_history(history) or []
            messages.append({"role": "user", "content": user_message})
            messages.append({"role": "assistant", "content": early})
        else:
            messages = _build_fresh_messages(user_message)
            messages.append({"role": "assistant", "content": early})
        yield {
            "done": True,
            "reply": early,
            "messages": _trim_session_messages(_strip_ephemeral(messages)),
        }
        return

    mem_ctx = _memory_context(user_message)

    if history:
        messages = _normalize_history(history) or []
        for hint in _pc_control_hints(user_message):
            messages.append(hint)
        if mem_ctx:
            messages.append({"role": "system", "content": mem_ctx})
        messages.append({"role": "user", "content": user_message})
    else:
        messages = _build_fresh_messages(user_message)

    client = _ollama_client()

    # --- Round 1: stream the first response ---------------------------------
    try:
        stream = client.chat(
            model=model,
            messages=messages,
            tools=tool_schemas(user_message),
            options={"num_predict": 1024},
            stream=True,
        )
    except Exception as e:
        yield {"error": f"LLM error: {e}"}
        return

    full_content = ""
    tool_calls_found: list[dict[str, Any]] = []

    for chunk in stream:
        # Normalize the partial message from the chunk
        try:
            if hasattr(chunk, "message"):
                msg_part = _message_to_dict(chunk.message)
            elif isinstance(chunk, dict):
                raw_msg = chunk.get("message")
                msg_part = _message_to_dict(raw_msg) if raw_msg is not None else {}
            else:
                msg_part = {}
        except Exception:
            msg_part = {}

        piece = msg_part.get("content") or ""
        if piece:
            full_content += piece
            yield {"token": piece}

        # Tool calls appear only in the final chunk (done=True)
        is_done = (
            getattr(chunk, "done", False)
            if not isinstance(chunk, dict)
            else chunk.get("done", False)
        )
        if is_done:
            tcs = msg_part.get("tool_calls") or []
            if tcs:
                tool_calls_found = tcs

    if not tool_calls_found:
        # Clean text reply — finish here
        final_msg = {"role": "assistant", "content": full_content}
        messages.append(final_msg)
        text = _honest_reply(messages, full_content.strip())
        yield {
            "done": True,
            "reply": text,
            "messages": _trim_session_messages(_strip_ephemeral(messages)),
        }
        return

    # --- Tool-call rounds (synchronous fallback) ----------------------------
    # First round produced tool calls; handle them and continue non-streaming.
    messages.append({
        "role": "assistant",
        "content": full_content,
        "tool_calls": tool_calls_found,
    })
    for tc in tool_calls_found:
        fn = tc.get("function") or {}
        name = fn.get("name", "")
        args = _parse_tool_args(fn.get("arguments"))
        result = execute_tool(name, args, uid, source=source)
        messages.append({"role": "tool", "content": result, "name": name})

    for _ in range(max_tool_rounds - 1):
        try:
            response = client.chat(
                model=model,
                messages=messages,
                tools=tool_schemas(user_message),
                options={"num_predict": 1024},
            )
        except Exception as e:
            yield {"error": f"LLM error: {e}"}
            return

        msg = _message_to_dict(response["message"])
        messages.append(msg)
        next_tool_calls = msg.get("tool_calls") or []
        if not next_tool_calls:
            text = _honest_reply(messages, (msg.get("content") or "").strip())
            yield {
                "done": True,
                "reply": text,
                "messages": _trim_session_messages(_strip_ephemeral(messages)),
            }
            return
        for tc in next_tool_calls:
            fn = tc.get("function") or {}
            name = fn.get("name", "")
            args = _parse_tool_args(fn.get("arguments"))
            result = execute_tool(name, args, uid, source=source)
            messages.append({"role": "tool", "content": result, "name": name})

    yield {
        "done": True,
        "reply": "Stopped: too many tool rounds.",
        "messages": _trim_session_messages(_strip_ephemeral(messages)),
    }
