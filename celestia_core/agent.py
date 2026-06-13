from __future__ import annotations

import json
from typing import Any, Callable, Generator

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

def _user_id() -> str:
    return get("app.user_id", "atlas_user")


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
                    "Do NOT say you opened, launched, or visited anything — not even in brackets. "
                    "Tell the user to use scoped mode, arm, or the direct command: open https://…"
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
                    "Never pass a URL to open_path. No PowerShell, no System32. "
                    "IMPORTANT: call the tool first — do NOT describe the action in text before calling it. "
                    "Report the tool result honestly; never claim success without a successful tool call."
                ),
            }
        )
    elif mode == "armed":
        hints.append(
            {
                "role": "system",
                "content": (
                    "PC control is ARMED. For http(s) links use open_url with the URL only. "
                    "For apps/files use open_path. "
                    "IMPORTANT: call the tool first — do NOT describe the action in text before calling it. "
                    "Report the tool result honestly; never claim success without a successful tool call."
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


def _build_fresh_messages(
    user_message: str, mem_ctx: str | None = None
) -> list[dict[str, Any]]:
    if mem_ctx is None:
        mem_ctx = _memory_context(user_message)
    messages: list[dict[str, Any]] = [{"role": "system", "content": build_system_prompt()}]
    messages.extend(_pc_control_hints(user_message))
    if mem_ctx:
        messages.append({"role": "system", "content": mem_ctx})
    messages.append({"role": "user", "content": user_message})
    return messages


_VOICE_CAP_HINT = (
    "[Voice reply] Keep your answer to 2 sentences maximum. "
    "Be direct and conversational — no lists, no markdown, no headers."
)


def _prepare_messages(
    user_message: str,
    history: list[dict[str, Any]] | None,
    voice_mode: bool,
) -> tuple[str, str, list[dict[str, Any]], str | None]:
    """Build the initial message list for a turn.

    Returns (uid, model, messages, early_reply_or_None).
    When early_reply_or_None is not None, the preflight fired and messages
    already includes the canned assistant reply — callers should return/yield
    immediately without hitting Ollama.
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
        return uid, model, messages, early

    mem_ctx = _memory_context(user_message)
    if history:
        messages = _normalize_history(history) or []
        for hint in _pc_control_hints(user_message):
            messages.append(hint)
        if mem_ctx:
            messages.append({"role": "system", "content": mem_ctx})
        if voice_mode and get("voice.reply_cap_voice", True):
            messages.append({"role": "system", "content": _VOICE_CAP_HINT})
        messages.append({"role": "user", "content": user_message})
    else:
        messages = _build_fresh_messages(user_message, mem_ctx)
        if voice_mode and get("voice.reply_cap_voice", True):
            messages.insert(-1, {"role": "system", "content": _VOICE_CAP_HINT})

    return uid, model, messages, None


def _sync_tool_rounds(
    messages: list[dict[str, Any]],
    model: str,
    client: ollama.Client,
    user_message: str,
    uid: str,
    source: str,
    max_rounds: int,
) -> tuple[str, list[dict[str, Any]]]:
    """Run synchronous LLM + tool-call rounds until text reply or round cap.

    Mutates *messages* in place. Raises RuntimeError on LLM failure so callers
    can handle it their own way (return tuple vs. yield error dict).
    """
    schemas = tool_schemas()
    for _ in range(max_rounds):
        try:
            response = client.chat(
                model=model,
                messages=messages,
                tools=schemas,
                options={"num_predict": int(get("llm.max_tokens", 1024))},
            )
        except Exception as e:
            raise RuntimeError(f"LLM error: {e}") from e

        msg = _message_to_dict(response["message"])
        messages.append(msg)
        tool_calls = msg.get("tool_calls") or []
        if not tool_calls:
            text = (msg.get("content") or "").strip()
            return text, _trim_session_messages(_strip_ephemeral(messages))

        for tc in tool_calls:
            fn = tc.get("function") or {}
            name = fn.get("name", "")
            args = _parse_tool_args(fn.get("arguments"))
            result = execute_tool(name, args, uid, source=source)
            messages.append({"role": "tool", "content": result, "name": name})

    return "Stopped: too many tool rounds.", _trim_session_messages(_strip_ephemeral(messages))


def run_turn(
    user_message: str,
    *,
    speak: bool = False,
    max_tool_rounds: int = 8,
    source: str = "cli",
    history: list[dict[str, Any]] | None = None,
    voice_mode: bool = False,
) -> tuple[str, list[dict[str, Any]]]:
    uid, model, messages, early = _prepare_messages(user_message, history, voice_mode)
    if early is not None:
        return early, _trim_session_messages(_strip_ephemeral(messages))

    client = _ollama_client()
    try:
        text, final_messages = _sync_tool_rounds(
            messages, model, client, user_message, uid, source, max_tool_rounds
        )
    except RuntimeError as e:
        err = str(e)
        messages.append({"role": "assistant", "content": err})
        return err, _trim_session_messages(_strip_ephemeral(messages))

    if speak and text:
        try:
            from skills.tts import speak as tts_speak

            tts_speak(text)
        except Exception as e:
            print(f"[warn] TTS: {e}")

    return text, final_messages


def run_turn_stream(
    user_message: str,
    *,
    source: str = "cli",
    history: list[dict[str, Any]] | None = None,
    max_tool_rounds: int = 8,
    voice_mode: bool = False,
    cancel_check: Callable[[], bool] | None = None,
) -> Generator[dict[str, Any], None, None]:
    """Generator that yields token events then a final done/error event.

    Yields one of:
        {"token": str}                                                — per Ollama chunk
        {"done": True, "reply": str, "messages": list[dict]}         — completion
        {"done": True, ..., "cancelled": True}                        — stopped mid-stream
        {"error": str}                                                — LLM failure

    ``cancel_check`` is polled between streamed tokens; when it returns True the
    stream stops and the partial reply is returned (and saved) with cancelled=True.

    Tool-call turns are handled synchronously (non-streaming) so the caller
    always receives a clean done event with the full message history.
    """
    uid, model, messages, early = _prepare_messages(user_message, history, voice_mode)
    if early is not None:
        yield {
            "done": True,
            "reply": early,
            "messages": _trim_session_messages(_strip_ephemeral(messages)),
        }
        return

    client = _ollama_client()
    schemas = tool_schemas()
    max_tokens = int(get("llm.max_tokens", 1024))

    # --- Round 1: stream the first response ---------------------------------
    try:
        stream = client.chat(
            model=model,
            messages=messages,
            tools=schemas,
            options={"num_predict": max_tokens},
            stream=True,
        )
    except Exception as e:
        yield {"error": f"LLM error: {e}"}
        return

    full_content = ""
    tool_calls_found: list[dict[str, Any]] = []
    cancelled = False

    for chunk in stream:
        # Stop between tokens if the caller requested cancellation. The partial
        # reply collected so far is kept and saved below.
        if cancel_check is not None and cancel_check():
            cancelled = True
            break

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

    if cancelled:
        # Stopped mid-stream: keep whatever was generated so far.
        messages.append({"role": "assistant", "content": full_content})
        yield {
            "done": True,
            "reply": full_content.strip(),
            "cancelled": True,
            "messages": _trim_session_messages(_strip_ephemeral(messages)),
        }
        return

    if not tool_calls_found:
        # Clean text reply — finish here
        messages.append({"role": "assistant", "content": full_content})
        text = full_content.strip()
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

    try:
        text, final_messages = _sync_tool_rounds(
            messages, model, client, user_message, uid, source, max_tool_rounds - 1
        )
        yield {"done": True, "reply": text, "messages": final_messages}
    except RuntimeError as e:
        yield {"error": str(e)}
