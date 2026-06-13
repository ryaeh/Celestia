"""In-flight chat-stream cancellation registry (UI V2 / F3).

A streaming turn registers its session id while running; `POST /chat/cancel` sets a
flag the stream loop polls between tokens (`is_cancelled`), so a slow or runaway
reply can be stopped cleanly — the partial text is kept — without killing the
process. Thread-safe; the flag auto-clears when the stream ends.

Keyed by session id: at most one stream runs per session, and that's the unit the
shell's stop button targets.
"""

from __future__ import annotations

import threading

_lock = threading.Lock()
_active: set[str] = set()      # sessions currently streaming
_cancelled: set[str] = set()   # sessions with a pending cancel request


def begin(session_id: str) -> None:
    """Mark a session as actively streaming (clears any stale cancel flag)."""
    if not session_id:
        return
    with _lock:
        _active.add(session_id)
        _cancelled.discard(session_id)


def end(session_id: str) -> None:
    """Mark a session's stream as finished and drop any cancel flag."""
    if not session_id:
        return
    with _lock:
        _active.discard(session_id)
        _cancelled.discard(session_id)


def request_cancel(session_id: str) -> bool:
    """Flag a session for cancellation.

    Returns True if the session was actively streaming (so the caller can tell a
    real stop from a no-op on an already-finished turn).
    """
    if not session_id:
        return False
    with _lock:
        active = session_id in _active
        if active:
            _cancelled.add(session_id)
        return active


def is_cancelled(session_id: str) -> bool:
    if not session_id:
        return False
    with _lock:
        return session_id in _cancelled
