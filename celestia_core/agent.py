from __future__ import annotations

import json
import re
from typing import Any

import ollama

from celestia_core.config import get
from celestia_core.personality import build_system_prompt
from skills.registry import execute_tool, tool_schemas

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
    if not get("memory.enabled", True) or not _needs_memory(query):
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


def _trim_session_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    max_msgs = int(get("chat.session_max_messages", 60))
    if len(messages) <= max_msgs:
        return messages
    head: list[dict[str, Any]] = []
    tail: list[dict[str, Any]] = []
    for m in messages:
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
    mem_ctx = _memory_context(user_message)

    from celestia_core.security import preflight_chat_pc

    early = preflight_chat_pc(user_message)
    if early:
        if history is not None:
            messages = list(history)
            messages.append({"role": "user", "content": user_message})
            messages.append({"role": "assistant", "content": early})
            return early, _trim_session_messages(messages)
        messages = _build_fresh_messages(user_message)
        messages.append({"role": "assistant", "content": early})
        return early, _trim_session_messages(messages)

    if history:
        messages = list(history)
        for hint in _pc_control_hints(user_message):
            messages.append(hint)
        if mem_ctx:
            messages.append({"role": "system", "content": mem_ctx})
        messages.append({"role": "user", "content": user_message})
    else:
        messages = _build_fresh_messages(user_message)

    for _ in range(max_tool_rounds):
        response = ollama.chat(
            model=model,
            messages=messages,
            tools=tool_schemas(user_message),
            options={"num_predict": 1024},
        )
        msg = response["message"]
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
            return text, _trim_session_messages(messages)

        for tc in tool_calls:
            fn = tc.get("function") or {}
            name = fn.get("name", "")
            args = _parse_tool_args(fn.get("arguments"))
            result = execute_tool(name, args, uid, source=source)
            messages.append({"role": "tool", "content": result, "name": name})

    return "Stopped: too many tool rounds.", _trim_session_messages(messages)
