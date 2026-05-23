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


def run_turn(
    user_message: str,
    *,
    speak: bool = False,
    max_tool_rounds: int = 8,
    source: str = "cli",
) -> str:
    uid = _user_id()
    model = get("llm.chat_model", "llama3.2:3b")
    mem_ctx = _memory_context(user_message)

    messages: list[dict[str, Any]] = [{"role": "system", "content": build_system_prompt()}]
    from celestia_core import security

    msg_low = user_message.lower()
    mode = security.get_mode()
    if mode == "safe":
        messages.append(
            {
                "role": "system",
                "content": (
                    "PC control is SAFE (off). For allowlisted apps use scope scoped; for full PC use arm. "
                    "Never claim you opened something unless a tool succeeded without 'Blocked'."
                ),
            }
        )
    elif mode == "scoped":
        messages.append(
            {
                "role": "system",
                "content": (
                    "PC control is SCOPED: open_path for allowlisted apps (notepad, calc, mspaint, …); "
                    "file_read only under workspace folders. No PowerShell, no URLs, no System32. "
                    "Call tools when needed; report Blocked messages honestly."
                ),
            }
        )
    elif any(
        t in msg_low
        for t in ("open ", "launch ", "start ", "notepad", "not defteri", "calc", "explorer")
    ):
        messages.append(
            {
                "role": "system",
                "content": (
                    "User asked to open/launch something. You MUST call open_path with the app name "
                    "(e.g. notepad or not defteri). Do not only chat — call the tool, then confirm from its result."
                ),
            }
        )
    if mem_ctx:
        messages.append({"role": "system", "content": mem_ctx})
    messages.append({"role": "user", "content": user_message})

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
            text = (msg.get("content") or "").strip()
            if speak and text:
                try:
                    from skills.tts import speak as tts_speak

                    tts_speak(text)
                except Exception as e:
                    print(f"[warn] TTS: {e}")
            return text

        for tc in tool_calls:
            fn = tc.get("function") or {}
            name = fn.get("name", "")
            args = _parse_tool_args(fn.get("arguments"))
            result = execute_tool(name, args, uid, source=source)
            messages.append({"role": "tool", "content": result, "name": name})

    return "Stopped: too many tool rounds."
