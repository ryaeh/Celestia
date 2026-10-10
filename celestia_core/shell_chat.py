"""Multi-turn chat sessions for the desktop shell (CC-5) — persisted to disk."""

from __future__ import annotations

import json
import queue
import re
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator, Iterator

from celestia_core.agent import run_turn, run_turn_stream
from celestia_core.config import ROOT, get, load_config
from celestia_core.file_utils import file_lock

_thread_lock = threading.Lock()
_last_turn_time: float = 0.0


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
    with file_lock(_lock_path()):
        yield


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
        # T15 memory cursor — see _cursor(): absolute message numbers.
        "seq_base": 0,
        "consolidated_seq": 0,
        "pending_since": None,
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


def _full_chat(state: dict[str, Any]) -> list[dict[str, Any]]:
    """Archived (trimmed) messages + the live history: the whole chat as the user saw it."""
    return list(state.get("archive") or []) + list(state.get("history") or [])


def _ui_messages(history: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if not history:
        return []
    out: list[dict[str, Any]] = []
    for msg in history:
        role = msg.get("role")
        content = (msg.get("content") or "").strip()
        if role in ("user", "assistant") and content:
            item: dict[str, Any] = {"role": role, "content": content}
            if isinstance(msg.get("ts"), (int, float)):
                item["ts"] = msg["ts"]
            out.append(item)
    return out


# ---------------------------------------------------------------------------
# Memory checkpoints (T15)
#
# The cursor is *absolute*: ``consolidated_seq`` counts non-system messages
# since the chat began, and ``seq_base`` is the absolute number of the first
# non-system message still in ``history``. The agent trims old messages from
# the front of long chats, which shifts list indexes; absolute numbers don't
# move, so trimming can never make the memory pass skip (or redo) a message.
# ---------------------------------------------------------------------------


def _head_len(history: list[dict[str, Any]]) -> int:
    n = 0
    for m in history:
        if m.get("role") != "system":
            break
        n += 1
    return n


def _msg_key(m: dict[str, Any]) -> str:
    return json.dumps(m, sort_keys=True, ensure_ascii=False, default=str)


def _dropped_count(old: list[dict[str, Any]] | None, new: list[dict[str, Any]]) -> int:
    """How many non-system messages the turn trimmed from the front of ``old``.

    ``agent._trim_session_messages`` only ever drops from the front (after the
    leading system messages), so ``old[d:]`` must be a prefix of ``new``.
    """
    o = [_msg_key(m) for m in (old or [])[_head_len(old or []):]]
    n = [_msg_key(m) for m in new[_head_len(new):]]
    for d in range(len(o) + 1):
        rest = o[d:]
        if n[: len(rest)] == rest:
            return d
    return len(o)


def _cursor(state: dict[str, Any]) -> tuple[int, int, int]:
    """(start index into history, seq_base, head length) for the next pass.

    Migrates the pre-T15 index cursor (``consolidate_from``) on first use.
    """
    history = state.get("history") or []
    head = _head_len(history)
    base = int(state.get("seq_base") or 0)
    if "consolidated_seq" not in state:
        state["consolidated_seq"] = base + max(0, int(state.get("consolidate_from") or 0) - head)
    done = int(state["consolidated_seq"])
    return min(head + max(0, done - base), len(history)), base, head


def _record_turn(state: dict[str, Any], new_history: list[dict[str, Any]]) -> None:
    """Store a turn's history, advancing ``seq_base`` past anything trimmed.

    Trimmed user/assistant messages move to the session's ``archive`` instead of
    being lost: the chat page still shows the whole chat, and ``_recall_note``
    can bring an old message back when the user refers to it.
    """
    _cursor(state)  # migrate before the history (and its indexes) change
    old = state.get("history") or []
    dropped = _dropped_count(old, new_history)
    base = int(state.get("seq_base") or 0)
    if dropped:
        archive = list(state.get("archive") or [])
        for i, m in enumerate(old[_head_len(old):][:dropped]):
            content = m.get("content")
            if m.get("role") in ("user", "assistant") and isinstance(content, str) and content.strip():
                item = {"role": m["role"], "content": content, "seq": base + i}
                if isinstance(m.get("ts"), (int, float)):
                    item["ts"] = m["ts"]
                archive.append(item)
        cap = int(get("chat.archive_max_messages", 2000))
        state["archive"] = archive[-cap:] if cap > 0 else []
    state["seq_base"] = base + dropped
    state["history"] = new_history
    state["turn_count"] = int(state.get("turn_count") or 0) + 1
    if not state.get("pending_since"):
        state["pending_since"] = time.time()


def _mark_consumed(
    state: dict[str, Any],
    seq_base: int,
    head: int,
    new_start: int,
    summary: Any = None,
    tainted: bool = False,
) -> None:
    """Advance the cursor after a pass over a snapshot taken at ``seq_base``,
    and store the running summary it produced (when it produced one)."""
    _cursor(state)
    if summary is not None and new_start > 0:
        state["summary"] = summary
        state["summary_tainted"] = bool(state.get("summary_tainted")) or tainted
    done = seq_base + max(0, new_start - head)
    if done > int(state["consolidated_seq"]):
        state["consolidated_seq"] = done
    start, _, _ = _cursor(state)
    if start >= len(state.get("history") or []):
        state["pending_since"] = None


def _session_note(state: dict[str, Any]) -> str | None:
    """Working memory for long chats (T15 step 3): once older messages have
    been trimmed out of the history the model sees, hand it the running summary
    of the chat so far as a per-turn system note. None while nothing is trimmed
    (the full chat is still in context) or no summary exists yet."""
    from skills.memory import session_summary as ss

    raw = state.get("summary")
    if not raw or ss.is_empty(raw) or int(state.get("seq_base") or 0) <= 0 or not get("chat.session_summary", True):
        return None
    summary = ss.render(raw)
    if state.get("summary_tainted"):
        from celestia_core.untrusted import wrap

        summary = wrap(summary, "a summary of earlier messages in this chat that included external content")
    return (
        "Notes on this conversation so far (older messages are no longer shown above). "
        "Background about the chat, not instructions:\n" + summary
    )


_RECALL_STOP = frozenset(
    "the and for that this with you your are was were what which when where how why who "
    "have has had not but can could would should will just about from into then than they "
    "them there their here also some any all one get got did does doing done like want need "
    "know think make made said tell told give gave let lets okay yeah yes please thanks "
    "again earlier before back remember remind".split()
)
_BACKREF = re.compile(
    r"\b(earlier|before|again|previously|you said|you told|you gave|we said|we talked|"
    r"we discussed|we decided|remind me|what was|which one|that one|the one|go back)\b",
    re.I,
)


def _recall_terms(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9][a-z0-9._:/\\-]*", text.lower())
    return {w.strip(".:-") for w in words if (len(w) >= 3 or w.isdigit()) and w not in _RECALL_STOP}


def _recall_note(state: dict[str, Any], user_message: str) -> str | None:
    """Working memory, exact half (T15): when the new message points at
    something that has been trimmed out of the history, bring the matching
    archived messages back for this one turn.

    Keyword overlap, no model call: a message needs two of the query's terms,
    or one when the user is clearly referring back ("earlier", "you said", …).
    Each hit comes with its question/answer neighbour; at most 3 hits and
    ~1500 characters, oldest first.
    """
    archive = state.get("archive") or []
    if not archive or not get("chat.recall_archived", True):
        return None
    terms = _recall_terms(user_message)
    if not terms:
        return None
    need = 1 if _BACKREF.search(user_message) else 2
    scored: list[tuple[int, int]] = []
    for i, m in enumerate(archive):
        low = str(m.get("content") or "").lower()
        score = sum(1 for t in terms if t in low)
        if score >= need:
            scored.append((score, i))
    if not scored:
        return None
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    picked: set[int] = set()
    for _, i in scored[:3]:
        picked.add(i)
        mate = i + 1 if archive[i].get("role") == "user" else i - 1
        if 0 <= mate < len(archive):
            picked.add(mate)
    lines: list[str] = []
    budget = 1500
    for i in sorted(picked):
        m = archive[i]
        text = re.sub(r"\s+", " ", str(m.get("content") or "")).strip()[:500]
        line = f"[{'User' if m.get('role') == 'user' else 'Assistant'}] {text}"
        if budget - len(line) < 0:
            break
        budget -= len(line)
        lines.append(line)
    if not lines:
        return None
    block = "\n".join(lines)
    if state.get("summary_tainted"):
        from celestia_core.untrusted import wrap

        block = wrap(block, "earlier messages in this chat that included external content")
    return "From earlier in this chat (these messages are no longer shown above):\n" + block


def _turn_notes(state: dict[str, Any], user_message: str) -> str | None:
    """The per-turn working-memory note: running summary + any recalled messages."""
    parts = [n for n in (_session_note(state), _recall_note(state, user_message)) if n]
    return "\n\n".join(parts) or None


def _checkpoint_reason(state: dict[str, Any]) -> str | None:
    """Why a mid-chat memory pass should run now (writer pipeline), or None.

    - ``trim``: unsaved messages are about to fall out of the session window
      (``chat.session_max_messages``) within the next few turns.
    - ``time``: the oldest unsaved message is older than
      ``memory.writer.checkpoint_minutes`` (a long chat).
    The end of a chat is handled by session finalize, not here.
    """
    history = state.get("history") or []
    start, _, head = _cursor(state)
    if start >= len(history):
        return None
    max_msgs = int(get("chat.session_max_messages", 60))
    margin = int(get("memory.writer.trim_margin", 12))
    if (start - head) < (len(history) - max_msgs + margin):
        return "trim"
    minutes = float(get("memory.writer.checkpoint_minutes", 60) or 0)
    since = state.get("pending_since")
    if minutes > 0 and since and time.time() - float(since) >= minutes * 60:
        return "time"
    return None


def _stamp_turn(history: list[dict[str, Any]] | None, turn_start: float) -> None:
    """Stamp this turn's messages with ``ts`` (epoch seconds), in place.

    The turn starts at the last user message that has no ``ts`` yet: that user
    line gets the time it was sent, everything after it (tool calls, the reply)
    the time it finished. Messages from before timestamps existed stay unstamped.
    """
    if not history:
        return
    start = None
    for i in range(len(history) - 1, -1, -1):
        if history[i].get("role") == "user" and "ts" not in history[i]:
            start = i
            break
    if start is None:
        return
    now = round(time.time(), 3)
    history[start]["ts"] = round(turn_start, 3)
    for msg in history[start + 1:]:
        if msg.get("role") != "system":
            msg.setdefault("ts", now)


def _should_consolidate_now(state: dict[str, Any], *, end: bool = False) -> bool:
    """Check — while holding the store lock — whether a background pass should run.

    A pass serves long-term memory *and* the running summary (working memory),
    so it still runs at the trim checkpoint when memory saving is off.
    """
    history = state.get("history")
    if not history:
        return False

    from skills.memory.session_consolidate import (
        consolidate_mode,
        should_run_consolidation,
    )
    from skills.memory.writer_pass import pipeline

    memory_on = consolidate_mode() != "off" and bool(get("memory.session_consolidate", True))
    summary_on = bool(get("chat.session_summary", True))
    if not (memory_on or summary_on):
        return False

    reason = _checkpoint_reason(state)
    if pipeline() == "writer":
        return reason is not None
    if reason == "trim" and summary_on:
        return True
    if not memory_on:
        return False

    start, _, _ = _cursor(state)
    if not should_run_consolidation(history, start_index=start, end=end):
        return False

    if not end:
        turn_count = int(state.get("turn_count") or 0)
        every = int(get("memory.session_consolidate_every", 6))
        if turn_count < every or turn_count % every != 0:
            return False

    return True


_CONSOLIDATION_IDLE_SECONDS = 5.0
_passes_lock = threading.Lock()
_passes_running: dict[str, dict[str, Any]] = {}


def _claim_pass(sid: str, kind: str = "checkpoint") -> bool:
    """One memory pass per session at a time (a slow pass mustn't be stacked).
    ``kind`` (checkpoint / idle / end) is what the shell's notice reports."""
    with _passes_lock:
        if sid in _passes_running:
            return False
        _passes_running[sid] = {"kind": kind, "since": time.time()}
        return True


def _release_pass(sid: str) -> None:
    with _passes_lock:
        _passes_running.pop(sid, None)


def memory_saving() -> dict[str, Any] | None:
    """The memory pass running in this process, if any — drives the shell's
    "Saving memories…" notice via /ws/state. ``{"kind", "since"}`` or None."""
    with _passes_lock:
        for info in _passes_running.values():
            return dict(info)
    return None


_VOICE_NOTICE = "One moment, I'm saving what I've learned so far."


def _voice_notice() -> None:
    """Spoken heads-up before a mid-chat memory pass in a voice chat (the pass
    can slow the next reply while the memory model holds the GPU)."""
    if not get("memory.writer.voice_notice", True):
        return
    try:
        from skills.tts import speak

        speak(str(get("memory.writer.voice_notice_text", _VOICE_NOTICE)))
    except Exception:
        pass


def idle_sweep(now: float | None = None) -> list[str]:
    """Save the active chat's unsaved messages once it has been idle for
    ``memory.writer.idle_minutes`` (default 20) — the "end of chat" for people
    who just walk away. Runs on the caller's thread (the idle daemon).
    Returns log lines; [] when nothing was due."""
    minutes = float(get("memory.writer.idle_minutes", 20) or 0)
    if minutes <= 0:
        return []
    now = time.time() if now is None else now
    with _store_lock():
        sid = _read_active()
        state = _read_session(sid) if sid else None
        if not state or not state.get("history"):
            return []
        start, base, head = _cursor(state)
        history = list(state["history"])
        idle_for = now - float(state.get("updated_at") or now)
        if start >= len(history) or idle_for < minutes * 60:
            return []
        if not _claim_pass(sid, "idle"):
            return []
    try:
        from skills.memory.writer_pass import consolidate

        uid = get("app.user_id", "atlas_user")
        new_start, lines = consolidate(history, uid, start_index=start, end=True)
        with _store_lock():
            state = _read_session(sid)
            if state is not None:
                _mark_consumed(state, base, head, new_start)
                _write_session(sid, state)
        return lines
    finally:
        _release_pass(sid)


def _chat_quiet() -> bool:
    """No reply is streaming and the last turn is a couple of minutes old.

    Background model work waits for this: the chat model and the memory model
    often can't sit in VRAM together, and loading one evicts the other, which
    would slow the next reply a lot (``memory.graph.backfill_quiet_seconds``).
    """
    from celestia_core import stream_cancel

    if stream_cancel.any_active():
        return False
    quiet = float(get("memory.graph.backfill_quiet_seconds", 120) or 0)
    return time.time() - _last_turn_time >= quiet


_idle_thread: threading.Thread | None = None


def start_idle_daemon(interval: float = 60.0) -> None:
    """Background loop: idle sweep (and, when the graph is on, a small batch
    of linking older memories to it). Started once by the shell server."""
    global _idle_thread
    if _idle_thread is not None and _idle_thread.is_alive():
        return

    def _loop() -> None:
        while True:
            time.sleep(interval)
            try:
                idle_sweep()
            except Exception as e:
                print(f"[memory] idle sweep failed: {e}")
            try:
                from skills.memory.graph_backfill import backfill_step

                if _chat_quiet():
                    backfill_step(get("app.user_id", "atlas_user"))
            except Exception as e:
                print(f"[memory] graph backfill failed: {e}")

    _idle_thread = threading.Thread(target=_loop, name="memory-idle", daemon=True)
    _idle_thread.start()


def _run_consolidation_bg(
    sid: str,
    history: list[dict[str, Any]],
    start_index: int,
    seq_base: int = 0,
    head: int = 0,
    summary: Any = None,
    announce: bool = False,
) -> None:
    """Background thread: wait for idle then run the memory pass.

    Sleeps briefly so a new turn arriving immediately after the done event
    cancels the pass — avoiding GPU contention with an in-flight chat request.
    """
    try:
        time.sleep(_CONSOLIDATION_IDLE_SECONDS)
        if time.time() - _last_turn_time < _CONSOLIDATION_IDLE_SECONDS - 0.5:
            return  # new turn started during the wait; the next turn re-checks
        if announce:
            _voice_notice()

        uid = get("app.user_id", "atlas_user")
        new_summary: Any = None
        tainted = False
        try:
            from skills.memory.writer_pass import session_pass

            r = session_pass(history, uid, start_index=start_index, summary=summary)
            new_start, stored_lines, new_summary, tainted = r.new_start, r.lines, r.summary, r.tainted
        except Exception as e:
            stored_lines = [f"consolidate error: {e}"]
            new_start = start_index

        with _store_lock():
            state = _read_session(sid)
            if state is not None:
                _mark_consumed(state, seq_base, head, new_start, new_summary, tainted)
                _write_session(sid, state)

        if stored_lines and get("memory.session_consolidate_verbose", False):
            for line in stored_lines:
                print(f"[memory] {line}")
    finally:
        _release_pass(sid)


def _maybe_consolidate(state: dict[str, Any], *, end: bool = False) -> list[str]:
    """Synchronous consolidation used only for end-of-session finalization."""
    history = state.get("history")
    if not history:
        return []

    from skills.memory.session_consolidate import (
        consolidate_mode,
        should_run_consolidation,
    )
    if consolidate_mode() == "off" or not get("memory.session_consolidate", True):
        return []

    start, base, head = _cursor(state)
    if not should_run_consolidation(history, start_index=start, end=end):
        return []

    uid = get("app.user_id", "atlas_user")
    # Legacy: graph extraction is a background-only deep pass — never block
    # session finalize on the extra LLM call. The writer pipeline writes the
    # graph from the same single call, so the flag doesn't apply to it.
    from skills.memory.writer_pass import session_pass

    r = session_pass(
        history, uid, start_index=start, summary=state.get("summary"), end=end, extract_graph=False
    )
    _mark_consumed(state, base, head, r.new_start, r.summary, r.tainted)
    return r.lines


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


def _search_tokens(query: str) -> list[str]:
    return [t for t in re.findall(r"\w+", query.lower()) if len(t) >= 2]


def _match_score(text_low: str, query_low: str, terms: list[str]) -> int:
    """2 = full phrase present, 1 = all terms present, 0 = no match."""
    if query_low and query_low in text_low:
        return 2
    if terms and all(t in text_low for t in terms):
        return 1
    return 0


def _snippet(content: str, terms: list[str], query_low: str, width: int = 160) -> str:
    """A ~width-char window of *content* centered on the first matched term."""
    low = content.lower()
    pos = low.find(query_low) if query_low else -1
    if pos < 0:
        for t in terms:
            pos = low.find(t)
            if pos >= 0:
                break
    if pos < 0:
        pos = 0
    start = max(0, pos - width // 3)
    end = min(len(content), start + width)
    snip = content[start:end].strip()
    if start > 0:
        snip = "…" + snip
    if end < len(content):
        snip = snip + "…"
    return snip


def search_sessions(query: str, *, limit: int = 20) -> list[dict[str, Any]]:
    """Keyword search over past chat sessions (titles + message content).

    Returns rows shaped like list_sessions() plus a ``snippet`` and ``matches``
    count, ranked by match strength then recency. Read-only; no LLM, no index.
    """
    q = query.strip().lower()
    terms = _search_tokens(q)
    if not q:
        return []

    with _store_lock():
        active_id = _resolve_active()
        ids = _list_session_ids()
        rows: list[dict[str, Any]] = []
        for sid in ids:
            state = _read_session(sid)
            if not state:
                continue
            title = state.get("title") or "New chat"
            title_score = _match_score(title.lower(), q, terms)

            best_snippet = ""
            match_count = 0
            best_msg_score = 0
            for msg in _full_chat(state):
                if msg.get("role") not in ("user", "assistant"):
                    continue
                content = (msg.get("content") or "").strip()
                if not content:
                    continue
                score = _match_score(content.lower(), q, terms)
                if score:
                    match_count += 1
                    if score > best_msg_score:
                        best_msg_score = score
                        best_snippet = _snippet(content, terms, q)

            if not title_score and not match_count:
                continue

            if not best_snippet and title_score:
                best_snippet = title
            rows.append(
                {
                    "id": sid,
                    "title": title,
                    "updated_at": state.get("updated_at", 0),
                    "when": _relative_time(float(state.get("updated_at", time.time()))),
                    "active": sid == active_id,
                    "snippet": best_snippet,
                    "matches": match_count,
                    "_rank": max(title_score * 2, best_msg_score) + min(match_count, 5) * 0.1,
                }
            )

    rows.sort(key=lambda r: (r.pop("_rank"), r["updated_at"]), reverse=True)
    return rows[:limit]


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


def _run_finalize_bg(
    sid: str, history: list[dict[str, Any]], start: int, seq_base: int = 0, head: int = 0
) -> None:
    """Background end-of-session finalize: last-session note + the memory pass
    (text memory + knowledge graph). Kept off the create_session path so
    starting a new chat returns immediately instead of blocking on the LLM.
    """
    try:
        from skills.memory.last_session import update_from_messages

        update_from_messages(history)
    except Exception:
        pass

    uid = get("app.user_id", "atlas_user")
    if _claim_pass(sid, "end"):
        try:
            from skills.memory.writer_pass import consolidate

            new_start, _ = consolidate(history, uid, start_index=start, end=True, extract_graph=True)
            with _store_lock():
                state = _read_session(sid)
                if state is not None:
                    _mark_consumed(state, seq_base, head, new_start)
                    _write_session(sid, state)
        except Exception:
            pass
        finally:
            _release_pass(sid)

    # Memory lifecycle step 3: throttled decay-delete of memories that earned no
    # keep. Internally gated by memory.decay.enabled + a once-per-interval throttle,
    # so this is a cheap no-op when disabled or recently swept.
    try:
        from skills.memory.decay import sweep_decay

        sweep_decay(uid)
    except Exception:
        pass


def create_session(*, finalize_active: bool = True) -> str:
    finalize_sid: str | None = None
    finalize_history: list[dict[str, Any]] = []
    finalize_start = finalize_base = finalize_head = 0
    with _store_lock():
        active_id = _resolve_active()
        if finalize_active and active_id:
            state = _read_session(active_id)
            if state is not None and state.get("history"):
                finalize_sid = active_id
                finalize_history = list(state["history"])
                finalize_start, finalize_base, finalize_head = _cursor(state)
        sid = str(uuid.uuid4())
        _write_session(sid, _new_session_state())
        _write_active(sid)

    # Finalize the previous chat in the background so the new chat is instant.
    if finalize_sid:
        threading.Thread(
            target=_run_finalize_bg,
            args=(finalize_sid, finalize_history, finalize_start, finalize_base, finalize_head),
            name="finalize-session",
            daemon=True,
        ).start()
    return sid


def get_notes(session_id: str | None = None) -> dict[str, Any]:
    """Working-memory notes for the shell's "What I'm keeping in mind" panel."""
    from skills.memory import session_summary as ss

    with _store_lock():
        sid = session_id or _resolve_active()
        state = (_read_session(sid) if sid else None) or {}
    notes = ss.coerce(state.get("summary"))
    return {
        "session_id": sid,
        "notes": notes,
        "empty": ss.is_empty(notes),
        "in_use": _session_note(state) is not None,   # trimmed → sent with each turn
        "archived": len(state.get("archive") or []),
        "untrusted": bool(state.get("summary_tainted")),
    }


def get_history(session_id: str | None = None) -> list[dict[str, Any]]:
    with _store_lock():
        sid = session_id or _resolve_active()
        assert sid is not None
        state = _read_session(sid) or {}
    return _ui_messages(_full_chat(state))


def send_message(
    message: str,
    *,
    session_id: str | None = None,
    source: str = "shell",
    voice_mode: bool = False,
) -> dict[str, Any]:
    global _last_turn_time
    text = message.strip()
    if not text:
        return {"error": "message required"}

    _last_turn_time = time.time()
    turn_start = _last_turn_time
    load_config()
    use_session = get("chat.session_enabled", True)
    speak = get("voice.always_speak", False)

    with _store_lock():
        sid = session_id or _resolve_active()
        assert sid is not None
        state = _read_session(sid) or _new_session_state()
        history = state.get("history") if use_session else None
        note = _turn_notes(state, text) if use_session else None
        if state.get("title") in (None, "", "New chat"):
            state["title"] = _title_from_message(text)
            _write_session(sid, state)

    if use_session:
        reply, new_history = run_turn(
            text, speak=speak, source=source, history=history, voice_mode=voice_mode, session_note=note
        )
    else:
        reply, new_history = run_turn(text, speak=speak, source=source, voice_mode=voice_mode)

    # Drain the provenance the turn's memory injection recorded (for the
    # "why did you say that?" UI). Same thread/context, so the ContextVar is set.
    from skills.memory.store import take_last_provenance

    provenance = take_last_provenance()

    run_consolidation_bg: bool = False
    consolidation_history: list[dict[str, Any]] = []
    consolidation_start: int = 0
    consolidation_base = consolidation_head = 0
    consolidation_summary: Any = None

    with _store_lock():
        # Re-read the single session so a concurrent consolidation write
        # (the memory cursor) is preserved rather than clobbered.
        state = _read_session(sid) or _new_session_state()
        if use_session:
            _stamp_turn(new_history, turn_start)
            _record_turn(state, new_history)
            # Check whether to consolidate — do it in a background thread so it
            # does not block the response being returned to the user (CC-94).
            if _should_consolidate_now(state) and _claim_pass(sid):
                run_consolidation_bg = True
                consolidation_history = list(state["history"])
                consolidation_start, consolidation_base, consolidation_head = _cursor(state)
                consolidation_summary = state.get("summary")
        state["updated_at"] = time.time()
        _write_session(sid, state)
        _write_active(sid)
        messages = _ui_messages(_full_chat(state))

    if run_consolidation_bg:
        threading.Thread(
            target=_run_consolidation_bg,
            args=(
                sid, consolidation_history, consolidation_start,
                consolidation_base, consolidation_head, consolidation_summary,
                source == "voice",
            ),
            daemon=True,
            name="celestia-consolidate",
        ).start()

    return {
        "reply": reply,
        "session_id": sid,
        "messages": messages,
        "provenance": provenance,
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

    The turn runs on its own thread and this generator only relays its events.
    If the client goes away mid-reply (page reload, closed window, sleep) the
    generator is closed, but the turn still finishes and is saved to the
    session, so the reply is waiting when the page comes back. (Saving used to
    happen in this generator after the last token, so a dropped connection
    lost the whole turn, including the user's message.)
    """
    events: queue.Queue[Any] = queue.Queue()
    finished = object()

    def _run() -> None:
        try:
            for event in _stream_turn(message, session_id, source, voice_mode):
                events.put(event)
        except Exception as e:
            events.put({"error": str(e)})
        finally:
            events.put(finished)

    threading.Thread(target=_run, daemon=True, name="celestia-chat-stream").start()
    while True:
        event = events.get()
        if event is finished:
            return
        yield event


def _stream_turn(
    message: str,
    session_id: str | None,
    source: str,
    voice_mode: bool,
) -> Generator[dict[str, Any], None, None]:
    """The streaming turn itself (see ``send_message_stream``)."""
    global _last_turn_time
    text = message.strip()
    if not text:
        yield {"error": "message required"}
        return

    _last_turn_time = time.time()
    turn_start = _last_turn_time
    load_config()
    use_session = get("chat.session_enabled", True)

    # Phase 1: load session state (under lock)
    with _store_lock():
        sid = session_id or _resolve_active()
        assert sid is not None
        state = _read_session(sid) or _new_session_state()
        history = state.get("history") if use_session else None
        note = _turn_notes(state, text) if use_session else None
        if state.get("title") in (None, "", "New chat"):
            state["title"] = _title_from_message(text)
            _write_session(sid, state)

    # Phase 2: stream LLM response (outside lock — this is the long operation)
    final_event: dict[str, Any] | None = None

    from celestia_core import stream_cancel

    stream_cancel.begin(sid)
    try:
        for event in run_turn_stream(
            text,
            source=source,
            history=history if use_session else None,
            voice_mode=voice_mode,
            cancel_check=lambda: stream_cancel.is_cancelled(sid),
            session_note=note,
        ):
            if "token" in event or "tool" in event:
                yield event  # forward token / tool-activity events immediately
            else:
                final_event = event  # hold done/error until session is saved
    finally:
        stream_cancel.end(sid)

    if final_event is None:
        # Generator ended without a done event (should not happen)
        yield {"error": "stream ended unexpectedly"}
        return

    if "error" in final_event:
        yield final_event
        return

    # Drain provenance recorded during the streamed turn (same context).
    from skills.memory.store import take_last_provenance

    provenance = take_last_provenance()

    # Phase 3: save session state (under lock)
    new_history = final_event.get("messages")
    reply = final_event.get("reply", "")

    run_consolidation_bg = False
    consolidation_history: list[dict[str, Any]] = []
    consolidation_start = consolidation_base = consolidation_head = 0
    consolidation_summary: Any = None

    with _store_lock():
        # Re-read the single session so a concurrent consolidation write
        # (the memory cursor) is preserved rather than clobbered.
        state = _read_session(sid) or _new_session_state()
        if use_session and new_history:
            _stamp_turn(new_history, turn_start)
            _record_turn(state, new_history)
            if _should_consolidate_now(state) and _claim_pass(sid):
                run_consolidation_bg = True
                consolidation_history = list(state["history"])
                consolidation_start, consolidation_base, consolidation_head = _cursor(state)
                consolidation_summary = state.get("summary")
        state["updated_at"] = time.time()
        _write_session(sid, state)
        _write_active(sid)
        messages = _ui_messages(_full_chat(state))

    if run_consolidation_bg:
        threading.Thread(
            target=_run_consolidation_bg,
            args=(
                sid, consolidation_history, consolidation_start,
                consolidation_base, consolidation_head, consolidation_summary,
                source == "voice",
            ),
            daemon=True,
            name="celestia-consolidate",
        ).start()

    # Phase 4: yield the final done event (with session context added)
    yield {
        "done": True,
        "reply": reply,
        "session_id": sid,
        "messages": messages,
        "provenance": provenance,
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
        now = round(time.time(), 3)
        history.append({"role": "user", "content": user_text, "ts": now})
        history.append({"role": "assistant", "content": assistant_text, "ts": now})
        state["history"] = history
        state["updated_at"] = time.time()
        if state.get("title") in (None, "", "New chat"):
            state["title"] = _title_from_message(user_text)
        _write_session(sid, state)
        messages = _ui_messages(_full_chat(state))
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


def delete_session(session_id: str) -> dict[str, Any]:
    """Delete a chat session, keeping what Celestia learned from it.

    By default (``chat.consolidate_before_delete``) the chat is consolidated into
    long-term memory first — typed memories + the knowledge graph — so only the
    raw transcript is removed; the distilled knowledge survives. Consolidation
    runs off the hot path against a history snapshot, so the file can be removed
    immediately (its memory writes don't depend on the file still existing).

    If the active chat is deleted, the active pointer falls back to the most
    recently updated remaining chat, or a fresh one when none are left.

    Returns ``{"deleted": bool, "active_id": str, "error"?: str}``.
    """
    consolidate = bool(get("chat.consolidate_before_delete", True))
    finalize_history: list[dict[str, Any]] = []
    finalize_start = finalize_base = finalize_head = 0

    with _store_lock():
        _resolve_active()
        if session_id not in _list_session_ids():
            return {"deleted": False, "error": "no such session"}

        if consolidate:
            state = _read_session(session_id)
            if state is not None and state.get("history"):
                finalize_history = list(state["history"])
                finalize_start, finalize_base, finalize_head = _cursor(state)

        try:
            (_sessions_dir() / f"{session_id}.json").unlink(missing_ok=True)
        except OSError:
            pass

        # Repair the active pointer only if we just removed the active chat.
        if _read_active() == session_id:
            remaining = _list_session_ids()
            if remaining:
                remaining.sort(
                    key=lambda sid: float((_read_session(sid) or {}).get("updated_at", 0)),
                    reverse=True,
                )
                _write_active(remaining[0])
            else:
                fresh = str(uuid.uuid4())
                _write_session(fresh, _new_session_state())
                _write_active(fresh)
        active_id = _read_active()

    # Distill from the snapshot in the background. The session file is already
    # gone; consolidation writes to the memory store, so the learnings persist.
    # _run_finalize_bg's trailing cursor write-back is a harmless no-op against
    # the now-deleted session.
    if consolidate and finalize_history:
        threading.Thread(
            target=_run_finalize_bg,
            args=(session_id, finalize_history, finalize_start, finalize_base, finalize_head),
            name="delete-finalize-session",
            daemon=True,
        ).start()

    return {"deleted": True, "active_id": active_id or ""}
