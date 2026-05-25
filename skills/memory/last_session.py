"""Rolling 'last session' note — injected on greetings."""

from __future__ import annotations

import json
import re
import threading
import time
from pathlib import Path
from typing import Any

from celestia_core.config import ROOT, get

_lock = threading.Lock()

_GREETING = re.compile(
    r"^(hi|hello|hey|yo|sup|howdy|good\s+(morning|afternoon|evening)|what'?s\s+up)[\s!.,?]*$",
    re.I,
)


def is_greeting(text: str) -> bool:
    return bool(_GREETING.match(text.strip()))


def _path() -> Path:
    rel = get("memory.last_session_path", "data/memory/last_session.json")
    path = Path(rel) if Path(rel).is_absolute() else ROOT / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def read_note() -> dict[str, Any]:
    with _lock:
        path = _path()
        if not path.is_file():
            return {"bullets": [], "text": "", "updated_at": 0}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            bullets = data.get("bullets") or []
            if not isinstance(bullets, list):
                bullets = []
            text = str(data.get("text") or "").strip()
            if not text and bullets:
                text = "\n".join(f"- {b}" for b in bullets)
            return {
                "bullets": [str(b) for b in bullets[:8]],
                "text": text[:600],
                "updated_at": float(data.get("updated_at") or 0),
            }
        except (json.JSONDecodeError, OSError):
            return {"bullets": [], "text": "", "updated_at": 0}


def write_note(bullets: list[str], *, text: str | None = None) -> None:
    clean = [b.strip() for b in bullets if b and b.strip()][:8]
    body = text.strip() if text else "\n".join(f"- {b}" for b in clean)
    payload = {
        "bullets": clean,
        "text": body[:600],
        "updated_at": time.time(),
    }
    with _lock:
        _path().write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def update_from_messages(messages: list[dict[str, Any]] | None) -> None:
    """Build a short last-session note from recent user/assistant turns."""
    if not messages:
        return

    lines: list[str] = []
    for m in messages[-12:]:
        role = m.get("role")
        content = (m.get("content") or "").strip()
        if role == "user" and content:
            lines.append(f"User: {content[:120]}")
        elif role == "assistant" and content:
            lines.append(f"Assistant: {content[:100]}")

    if not lines:
        return

    excerpt = "\n".join(lines[-10:])
    model = get("memory.session_consolidate_model") or get("llm.chat_model", "llama3.2:3b")

    try:
        import ollama

        resp = ollama.chat(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Summarize what happened in this chat session in 2-4 short bullet points "
                        "for 'since last time' context. User-focused, past tense. "
                        "JSON only: {\"bullets\":[\"...\"]}\n\n"
                        f"{excerpt}"
                    ),
                }
            ],
            options={"num_predict": 200, "temperature": 0.2},
        )
        raw = (resp.get("message") or {}).get("content") or ""
        if hasattr(raw, "model_dump"):
            raw = raw.model_dump().get("content", "") or str(raw)
        import re as _re

        match = _re.search(r"\{[\s\S]*\}", str(raw))
        if match:
            data = json.loads(match.group())
            bullets = data.get("bullets") or []
            if isinstance(bullets, list) and bullets:
                write_note([str(b) for b in bullets])
                return
    except Exception:
        pass

    # Fallback: last user message only
    for m in reversed(messages):
        if m.get("role") == "user":
            c = (m.get("content") or "").strip()
            if c:
                write_note([f"Last talked about: {c[:100]}"])
                return


def context_block() -> str:
    note = read_note()
    text = note.get("text") or ""
    if not text:
        return ""
    return f"Since last session:\n{text}"
