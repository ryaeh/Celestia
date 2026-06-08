"""Multi-turn chat sessions for the desktop shell (CC-5) — persisted to disk."""

from __future__ import annotations

import json
import sys
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator, Iterator

from celestia_core.agent import run_turn, run_turn_stream
from celestia_core.config import ROOT, get, load_config

_thread_lock = threading.Lock()


def _store_path() -> Path:
    """Legacy path — used only for migration detection."""
    rel = get("ui.shell_chat_store", "data/shell_chat/sessions.json")
    path = Path(rel) if Path(rel).is_absolute() else ROOT / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _sessions_dir() -> Path:
    d = _store_path().parent / "sessions"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _active_path() -> Path:
    return _store_path().parent / "active"


def _lock_path() -> Path:
    return _store_path().parent / ".lock"


def _migrate_legacy() -> None:
    """One-time migration: split sessions.json into per-session files."""
    legacy = _store_path()
    if not legacy.is_file():
        return
    try:
        raw = json.loads(legacy.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        legacy.rename(legacy.with_suffix(".bak"))
        return
    active = raw.get("active")
    sessions = raw.get("sessions") or {}
    if not isinstance(sessions, dict):
        legacy.rename(legacy.with_suffix(".bak"))
        return
    sdir = _sessions_dir()
    ap = _active_path()
    for sid, state in sessions.items():
        dest = sdir / f"{sid}.json"
        if not dest.exists():
            dest.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    if active and not ap.exists():
        ap.write_text(active, encoding="utf-8")
    legacy.rename(legacy.with_suffix(".bak"))


@contextmanager
def _file_lock() -> Iterator[None]:
    """Exclusive lock shared across tray, shell API, and CLI processes."""
    lock_path = _lock_path()
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "a+b") as lock_file:
        if sys.platform == "win32":
            import msvcrt

            lock_file.seek(0)
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if sys.platform == "win32":
                import msvcrt

                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


@contextmanager
def _store_lock() -> Iterator[None]:
    with _thread_lock:
        load_config()
        with _file_lock():
            yield


def _sanitize_history(history: Any) -> list[dict[str, Any]] | None:
    if not history:
        return None
    if not isinstance(history, list):
        return None
    from celestia_core.agent import _message_to_dict

    out: list[dict[str, Any]] = []
    for item in history:
        try:
            out.append(_message_to_dict(item))
        except TypeError:
            continue
    return out or None


def _new_session_state() -> dict[str, Any]:
    return {
        "title": "New chat",
        "updated_at": time.time(),
        "history": None,
        "consolidate_from": 0,
        "turn_count": 0,
    }


def _list_session_ids() -> list[str]:
    return [f.stem for f in _sessions_dir().glob("*.json")]


def _read_active() -> str | None:
    path = _active_path()
    if path.is_file():
        try:
            return path.read_text(encoding="utf-8").strip() or None
        except OSError:
            pass
    return None


def _write_active(active_id: str | None) -> None:
    _active_path().write_text(active_id or "", encoding="utf-8")


def _read_session(sid: str) -> dict[str, Any] | None:
    """Read a single session file. Returns None if missing or corrupt."""
    path = _sessions_dir() / f"{sid}.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def _write_session(sid: str, state: dict[str, Any]) -> None:
    """Write a single session file — touches only the one session that changed."""
    st = dict(state)
    st["history"] = _sanitize_history(st.get("history"))
    (_sessions_dir() / f"{sid}.json").write_text(
        json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _resolve_active(*, create: bool = True) -> str | None:
    """Return the active session id without reading any session bodies.

    Touches only the active pointer and the directory listing. Ensures at least
    one session exists (when ``create``) and that the active pointer references a
    real session, persisting the pointer only when it is created or corrected.
    """
    _migrate_legacy()
    active = _read_active()
    ids = _list_session_ids()
    if not ids:
        if not create:
            return active
        sid = str(uuid.uuid4())
        _write_session(sid, _new_session_state())
        _write_active(sid)
        return sid
    if active not in ids:
        active = ids[0]
        _write_active(active)
    return active


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


def _should_consolidate_now(state: dict[str, Any], *, end: bool = False) -> bool:
    """Check — while holding the store lock — whether consolidation should run."""
    history = state.get("history")
    if not history:
        return False

    from skills.memory.session_consolidate import (
        consolidate_mode,
        should_run_consolidation,
    )

    if consolidate_mode() == "off" or not get("memory.session_consolidate", True):
        return False

    start = int(state.get("consolidate_from") or 0)
    if not should_run_consolidation(history, start_index=start, end=end):
        return False

    if not end:
        turn_count = int(state.get("turn_count") or 0)
        every = int(get("memory.session_consolidate_every", 6))
        if turn_count < every or turn_count % every != 0:
            return False

    return True


def _run_consolidation_bg(
    sid: str,
    history: list[dict[str, Any]],
    start_index: int,
) -> None:
    """Background thread: run LLM consolidation, then write consolidate_from back."""
    uid = get("app.user_id", "atlas_user")
    try:
        from skills.memory.session_consolidate import consolidate_session_messages

        new_start, stored_lines = consolidate_session_messages(
            history, uid, start_index=start_index
        )
    except Exception as e:
        stored_lines = [f"consolidate error: {e}"]
        new_start = start_index

    with _store_lock():
        state = _read_session(sid)
        if state is not None:
            state["consolidate_from"] = new_start
            _write_session(sid, state)

    if stored_lines and get("memory.session_consolidate_verbose", False):
        for line in stored_lines:
            print(f"[memory] saved: {line}")


def _maybe_consolidate(state: dict[str, Any], *, end: bool = False) -> list[str]:
    """Synchronous consolidation used only for end-of-session finalization."""
    history = state.get("history")
    if not history:
        return []

    from skills.memory.session_consolidate import (
        consolidate_mode,
        consolidate_session_messages,
        should_run_consolidation,
    )

    if consolidate_mode() == "off" or not get("memory.session_consolidate", True):
        return []

    start = int(state.get("consolidate_from") or 0)
    if not should_run_consolidation(history, start_index=start, end=end):
        return []

    uid = get("app.user_id", "atlas_user")
    new_start, stored = consolidate_session_messages(history, uid, start_index=start)
    state["consolidate_from"] = new_start
    return stored


def finalize_active_session() -> None:
    """Consolidate + last-session note for the current active chat."""
    with _store_lock():
        active_id = _resolve_active()
        if active_id:
            state = _read_session(active_id)
            if state is not None:
                _finalize_session(state)
                _write_session(active_id, state)


def get_active_session_id() -> str:
    with _store_lock():
        active_id = _resolve_active()
        assert active_id is not None
        return active_id


def set_active_session(session_id: str) -> bool:
    with _store_lock():
        _resolve_active()
        if session_id not in _list_session_ids():
            return False
        _write_active(session_id)
        return True


def list_sessions() -> list[dict[str, Any]]:
    with _store_lock():
        active_id = _resolve_active()
        rows = []
        for sid in _list_session_ids():
            state = _read_session(sid) or {}
            rows.append(
                {
                    "id": sid,
                    "title": state.get("title") or "New chat",
                    "updated_at": state.get("updated_at", 0),
                    "when": _relative_time(float(state.get("updated_at", time.time()))),
                    "active": sid == active_id,
                }
            )
        rows.sort(key=lambda r: r["updated_at"], reverse=True)
        return rows


def _finalize_session(state: dict[str, Any]) -> None:
    """Consolidate + update last-session note before ending a chat."""
    history = state.get("history")
    if not history:
        return
    _maybe_consolidate(state, end=True)
    try:
        from skills.memory.last_session import update_from_messages

        update_from_messages(history)
    except Exception:
        pass


def create_session(*, finalize_active: bool = True) -> str:
    with _store_lock():
        active_id = _resolve_active()
        if finalize_active and active_id:
            state = _read_session(active_id)
            if state is not None:
                _finalize_session(state)
                _write_session(active_id, state)
        sid = str(uuid.uuid4())
        _write_session(sid, _new_session_state())
        _write_active(sid)
        return sid


def get_history(session_id: str | None = None) -> list[dict[str, str]]:
    with _store_lock():
        sid = session_id or _resolve_active()
        assert sid is not None
        hist = (_read_session(sid) or {}).get("history")
    return _ui_messages(hist)


def send_message(
    message: str,
    *,
    session_id: str | None = None,
    source: str = "shell",
    voice_mode: bool = False,
) -> dict[str, Any]:
    text = message.strip()
    if not text:
        return {"error": "message required"}

    load_config()
    use_session = get("chat.session_enabled", True)
    speak = get("voice.always_speak", False)

    with _store_lock():
        sid = session_id or _resolve_active()
        assert sid is not None
        state = _read_session(sid) or _new_session_state()
        history = state.get("history") if use_session else None
        if state.get("title") in (None, "", "New chat"):
            state["title"] = _title_from_message(text)
            _write_session(sid, state)

    if use_session:
        reply, new_history = run_turn(text, speak=speak, source=source, history=history, voice_mode=voice_mode)
    else:
        reply, new_history = run_turn(text, speak=speak, source=source, voice_mode=voice_mode)

    run_consolidation_bg: bool = False
    consolidation_history: list[dict[str, Any]] = []
    consolidation_start: int = 0

    with _store_lock():
        # Re-read the single session so a concurrent consolidation write
        # (consolidate_from) is preserved rather than clobbered.
        state = _read_session(sid) or _new_session_state()
        if use_session:
            state["history"] = new_history
            state["turn_count"] = int(state.get("turn_count") or 0) + 1
            # Check whether to consolidate — do it in a background thread so it
            # does not block the response being returned to the user (CC-94).
            if _should_consolidate_now(state):
                run_consolidation_bg = True
                consolidation_history = list(state["history"])
                consolidation_start = int(state.get("consolidate_from") or 0)
        state["updated_at"] = time.time()
        _write_session(sid, state)
        _write_active(sid)
        messages = _ui_messages(state.get("history"))

    if run_consolidation_bg:
        threading.Thread(
            target=_run_consolidation_bg,
            args=(sid, consolidation_history, consolidation_start),
            daemon=True,
            name="celestia-consolidate",
        ).start()

    return {
        "reply": reply,
        "session_id": sid,
        "messages": messages,
    }


def send_message_stream(
    message: str,
    *,
    session_id: str | None = None,
    source: str = "shell",
    voice_mode: bool = False,
) -> Generator[dict[str, Any], None, None]:
    """Generator yielding token events then a final done/error event (CC-89).

    Yields the same events as run_turn_stream(), plus the final done event
    includes "session_id" and the UI-ready "messages" list.
    """
    text = message.strip()
    if not text:
        yield {"error": "message required"}
        return

    load_config()
    use_session = get("chat.session_enabled", True)

    # Phase 1: load session state (under lock)
    with _store_lock():
        sid = session_id or _resolve_active()
        assert sid is not None
        state = _read_session(sid) or _new_session_state()
        history = state.get("history") if use_session else None
        if state.get("title") in (None, "", "New chat"):
            state["title"] = _title_from_message(text)
            _write_session(sid, state)

    # Phase 2: stream LLM response (outside lock — this is the long operation)
    final_event: dict[str, Any] | None = None

    for event in run_turn_stream(
        text, source=source, history=history if use_session else None, voice_mode=voice_mode
    ):
        if "token" in event:
            yield event  # forward token immediately
        else:
            final_event = event  # hold done/error until session is saved

    if final_event is None:
        # Generator ended without a done event (should not happen)
        yield {"error": "stream ended unexpectedly"}
        return

    if "error" in final_event:
        yield final_event
        return

    # Phase 3: save session state (under lock)
    new_history = final_event.get("messages")
    reply = final_event.get("reply", "")

    run_consolidation_bg = False
    consolidation_history: list[dict[str, Any]] = []
    consolidation_start = 0

    with _store_lock():
        # Re-read the single session so a concurrent consolidation write
        # (consolidate_from) is preserved rather than clobbered.
        state = _read_session(sid) or _new_session_state()
        if use_session and new_history:
            state["history"] = new_history
            state["turn_count"] = int(state.get("turn_count") or 0) + 1
            if _should_consolidate_now(state):
                run_consolidation_bg = True
                consolidation_history = list(state["history"])
                consolidation_start = int(state.get("consolidate_from") or 0)
        state["updated_at"] = time.time()
        _write_session(sid, state)
        _write_active(sid)
        messages = _ui_messages(state.get("history"))

    if run_consolidation_bg:
        threading.Thread(
            target=_run_consolidation_bg,
            args=(sid, consolidation_history, consolidation_start),
            daemon=True,
            name="celestia-consolidate",
        ).start()

    # Phase 4: yield the final done event (with session context added)
    yield {
        "done": True,
        "reply": reply,
        "session_id": sid,
        "messages": messages,
    }


def append_raw_turn(
    user_text: str,
    assistant_text: str,
    *,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Append a user+assistant pair to a session without LLM inference.

    Used by the vision confirm flow (CC-49) to persist screenshot Q&A.
    """
    with _store_lock():
        sid = session_id or _resolve_active()
        assert sid is not None
        state = _read_session(sid) or _new_session_state()
        history = list(state.get("history") or [])
        history.append({"role": "user", "content": user_text})
        history.append({"role": "assistant", "content": assistant_text})
        state["history"] = history
        state["updated_at"] = time.time()
        if state.get("title") in (None, "", "New chat"):
            state["title"] = _title_from_message(user_text)
        _write_session(sid, state)
        messages = _ui_messages(history)
    return {"session_id": sid, "messages": messages}


def clear_session(session_id: str | None = None) -> str:
    """Start a fresh session. Returns new session id."""
    with _store_lock():
        sid = session_id or _resolve_active()
        if sid:
            state = _read_session(sid)
            if state is not None:
                _finalize_session(state)
    return create_session(finalize_active=False)
