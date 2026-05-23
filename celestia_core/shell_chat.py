"""Multi-turn chat sessions for the desktop shell (CC-5) — persisted to disk."""

from __future__ import annotations

import json
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from celestia_core.agent import run_turn
from celestia_core.config import ROOT, get, load_config

_lock = threading.Lock()
_active_id: str | None = None
_sessions: dict[str, dict[str, Any]] = {}
_loaded = False


def _store_path() -> Path:
    rel = get("ui.shell_chat_store", "data/shell_chat/sessions.json")
    path = Path(rel) if Path(rel).is_absolute() else ROOT / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _relative_time(ts: float) -> str:
    delta = max(0, time.time() - ts)
    if delta < 3600:
        return f"{int(delta // 60) or 1}m ago"
    if delta < 86400:
        return f"{int(delta // 3600)}h ago"
    if delta < 604800:
        return f"{int(delta // 86400)}d ago"
    return "Last week"


def _title_from_message(text: str) -> str:
    t = " ".join(text.strip().split())
    if len(t) <= 48:
        return t or "New chat"
    return t[:45] + "…"


def _ui_messages(history: list[dict[str, Any]] | None) -> list[dict[str, str]]:
    if not history:
        return []
    out: list[dict[str, str]] = []
    for msg in history:
        role = msg.get("role")
        content = (msg.get("content") or "").strip()
        if role in ("user", "assistant") and content:
            out.append({"role": role, "content": content})
    return out


def _ensure_loaded() -> None:
    global _loaded, _active_id, _sessions
    if _loaded:
        return
    load_config()
    path = _store_path()
    if path.is_file():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            _active_id = raw.get("active")
            _sessions = raw.get("sessions") or {}
        except (json.JSONDecodeError, OSError):
            _sessions = {}
            _active_id = None
    if not _sessions:
        sid = str(uuid.uuid4())
        _sessions[sid] = {
            "title": "New chat",
            "updated_at": time.time(),
            "history": None,
        }
        _active_id = sid
    if _active_id not in _sessions:
        _active_id = next(iter(_sessions))
    _loaded = True


def _save() -> None:
    path = _store_path()
    payload = {"active": _active_id, "sessions": _sessions}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _session(session_id: str) -> dict[str, Any]:
    _ensure_loaded()
    if session_id not in _sessions:
        _sessions[session_id] = {
            "title": "New chat",
            "updated_at": time.time(),
            "history": None,
        }
    return _sessions[session_id]


def get_active_session_id() -> str:
    with _lock:
        _ensure_loaded()
        assert _active_id is not None
        return _active_id


def set_active_session(session_id: str) -> bool:
    with _lock:
        _ensure_loaded()
        if session_id not in _sessions:
            return False
        global _active_id
        _active_id = session_id
        _save()
        return True


def list_sessions() -> list[dict[str, Any]]:
    with _lock:
        _ensure_loaded()
        rows = []
        for sid, state in _sessions.items():
            rows.append(
                {
                    "id": sid,
                    "title": state.get("title") or "New chat",
                    "updated_at": state.get("updated_at", 0),
                    "when": _relative_time(float(state.get("updated_at", time.time()))),
                    "active": sid == _active_id,
                }
            )
        rows.sort(key=lambda r: r["updated_at"], reverse=True)
        return rows


def create_session() -> str:
    with _lock:
        _ensure_loaded()
        sid = str(uuid.uuid4())
        global _active_id
        _sessions[sid] = {
            "title": "New chat",
            "updated_at": time.time(),
            "history": None,
        }
        _active_id = sid
        _save()
        return sid


def get_history(session_id: str | None = None) -> list[dict[str, str]]:
    load_config()
    with _lock:
        _ensure_loaded()
        sid = session_id or _active_id
        assert sid is not None
        hist = _session(sid).get("history")
    return _ui_messages(hist)


def send_message(
    message: str,
    *,
    session_id: str | None = None,
    source: str = "shell",
) -> dict[str, Any]:
    global _active_id
    text = message.strip()
    if not text:
        return {"error": "message required"}

    load_config()
    use_session = get("chat.session_enabled", True)
    speak = get("voice.always_speak", False)

    with _lock:
        _ensure_loaded()
        sid = session_id or _active_id
        assert sid is not None
        _active_id = sid
        state = _session(sid)
        history = state.get("history") if use_session else None
        if state.get("title") in (None, "", "New chat"):
            state["title"] = _title_from_message(text)

    if use_session:
        reply, new_history = run_turn(text, speak=speak, source=source, history=history)
    else:
        reply, new_history = run_turn(text, speak=speak, source=source)

    with _lock:
        state = _session(sid)
        if use_session:
            state["history"] = new_history
        state["updated_at"] = time.time()
        _save()

    return {
        "reply": reply,
        "session_id": sid,
        "messages": get_history(sid),
    }


def clear_session(session_id: str | None = None) -> str:
    """Legacy: start a fresh session (creates new id). Returns new session id."""
    return create_session()
