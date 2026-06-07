"""Tests for celestia_core/shell_chat.py — session management and send_message().

File I/O is redirected to tmp_path; the file lock is replaced with a no-op so
tests run without msvcrt/fcntl contention.  run_turn() is stubbed out so no
real Ollama server or Chroma is needed.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Iterator

import pytest

import celestia_core.config as _cfg
import celestia_core.shell_chat as sc


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def chat_tmp(tmp_path, monkeypatch):
    """Redirect all shell_chat disk I/O to a temp directory.

    - _store_path() → tmp_path/shell_chat/sessions.json
    - _file_lock()  → no-op (avoid msvcrt/fcntl in unit tests)
    - sc.load_config / sc.get → patched in sc's namespace (it uses
      `from celestia_core.config import get, load_config` at module level,
      so patching _cfg.get would have no effect on shell_chat's local binding)
    - _should_consolidate_now → always False (avoids importing mem0/Chroma)
    """
    store_file = tmp_path / "shell_chat" / "sessions.json"
    monkeypatch.setattr(sc, "_store_path", lambda: store_file)

    @contextmanager
    def _noop() -> Iterator[None]:
        yield

    monkeypatch.setattr(sc, "_file_lock", _noop)

    monkeypatch.setattr(sc, "load_config", lambda: None)
    monkeypatch.setattr(
        sc,
        "get",
        lambda key, default=None: {
            "chat.session_enabled": True,
            "voice.always_speak": False,
            "memory.session_consolidate": False,
            "memory.session_consolidate_verbose": False,
            "app.user_id": "test_user",
        }.get(key, default),
    )
    # Prevent _should_consolidate_now from importing session_consolidate (which
    # pulls in mem0 / Chroma / Ollama — all heavy deps not available in tests).
    monkeypatch.setattr(sc, "_should_consolidate_now", lambda state, end=False: False)
    return tmp_path / "shell_chat"


@pytest.fixture()
def stub_run_turn(monkeypatch):
    """Replace run_turn with a stub that echoes the message back."""

    def _stub(msg, **kw):
        history = [
            {"role": "user", "content": msg},
            {"role": "assistant", "content": f"echo: {msg}"},
        ]
        return f"echo: {msg}", history

    monkeypatch.setattr(sc, "run_turn", _stub)


# ---------------------------------------------------------------------------
# _title_from_message — pure function, no fixtures needed
# ---------------------------------------------------------------------------


def test_title_short_message() -> None:
    assert sc._title_from_message("hello") == "hello"


def test_title_exactly_48_chars() -> None:
    t = "x" * 48
    assert sc._title_from_message(t) == t


def test_title_long_message_truncated() -> None:
    long = "y" * 60
    result = sc._title_from_message(long)
    assert result.endswith("…")
    assert len(result) <= 46  # 45 chars + "…"


def test_title_empty_returns_new_chat() -> None:
    assert sc._title_from_message("") == "New chat"


# ---------------------------------------------------------------------------
# send_message — empty / whitespace input
# ---------------------------------------------------------------------------


def test_send_message_empty_string_returns_error(chat_tmp) -> None:
    result = sc.send_message("")
    assert result.get("error") == "message required"


def test_send_message_whitespace_only_returns_error(chat_tmp) -> None:
    result = sc.send_message("   ")
    assert result.get("error") == "message required"


# ---------------------------------------------------------------------------
# send_message — happy path
#
# NOTE: send_message() acquires the store lock twice — once to read the session
# state before calling run_turn(), and once to write results back.  It does NOT
# write in the first lock block, so the second read finds the session on disk
# only if it was previously persisted.  Tests must pre-create a session with
# create_session() (which does write) before calling send_message().
# ---------------------------------------------------------------------------


def test_send_message_returns_reply(chat_tmp, stub_run_turn) -> None:
    sid = sc.create_session(finalize_active=False)
    result = sc.send_message("hello", session_id=sid)
    assert result["reply"] == "echo: hello"


def test_send_message_returns_session_id(chat_tmp, stub_run_turn) -> None:
    sid = sc.create_session(finalize_active=False)
    result = sc.send_message("hello", session_id=sid)
    assert "session_id" in result
    assert result["session_id"] == sid


def test_send_message_returns_messages_list(chat_tmp, stub_run_turn) -> None:
    sid = sc.create_session(finalize_active=False)
    result = sc.send_message("hello", session_id=sid)
    msgs = result["messages"]
    assert isinstance(msgs, list)
    roles = {m["role"] for m in msgs}
    assert "user" in roles
    assert "assistant" in roles


def test_send_message_sets_session_title(chat_tmp, stub_run_turn) -> None:
    """First message becomes the session title."""
    sid = sc.create_session(finalize_active=False)
    sc.send_message("What time is it?", session_id=sid)
    sessions = sc.list_sessions()
    assert any("What time" in s["title"] for s in sessions)


def test_send_message_second_turn_uses_history(chat_tmp, monkeypatch) -> None:
    """Second call should pass prior history to run_turn."""
    received_history: list = []

    def _stub(msg, **kw):
        received_history.append(kw.get("history"))
        history = [
            {"role": "user", "content": msg},
            {"role": "assistant", "content": "ok"},
        ]
        return "ok", history

    monkeypatch.setattr(sc, "run_turn", _stub)
    monkeypatch.setattr(sc, "_should_consolidate_now", lambda state, end=False: False)
    sid = sc.create_session(finalize_active=False)
    sc.send_message("first", session_id=sid)
    sc.send_message("second", session_id=sid)
    # Second call must have received the history from the first turn
    assert received_history[1] is not None
    assert len(received_history[1]) > 0


# ---------------------------------------------------------------------------
# create_session / list_sessions / set_active_session
# ---------------------------------------------------------------------------


def test_create_session_returns_uuid(chat_tmp) -> None:
    sid = sc.create_session(finalize_active=False)
    assert len(sid) == 36
    # All UUID chars
    assert all(c in "0123456789abcdef-" for c in sid)


def test_create_session_appears_in_list(chat_tmp) -> None:
    sid = sc.create_session(finalize_active=False)
    ids = [s["id"] for s in sc.list_sessions()]
    assert sid in ids


def test_list_sessions_marks_active(chat_tmp) -> None:
    sid = sc.create_session(finalize_active=False)
    sessions = sc.list_sessions()
    active = next(s for s in sessions if s["id"] == sid)
    assert active["active"] is True


def test_set_active_session_switches_active(chat_tmp) -> None:
    s1 = sc.create_session(finalize_active=False)
    s2 = sc.create_session(finalize_active=False)
    sc.set_active_session(s1)
    sessions = sc.list_sessions()
    assert next(s for s in sessions if s["id"] == s1)["active"] is True
    assert next(s for s in sessions if s["id"] == s2)["active"] is False


def test_set_active_session_unknown_id_returns_false(chat_tmp) -> None:
    sc.create_session(finalize_active=False)
    result = sc.set_active_session("00000000-0000-0000-0000-000000000000")
    assert result is False


# ---------------------------------------------------------------------------
# get_history
# ---------------------------------------------------------------------------


def test_get_history_empty_for_new_session(chat_tmp) -> None:
    sc.create_session(finalize_active=False)
    hist = sc.get_history()
    assert hist == []


def test_get_history_after_messages(chat_tmp, stub_run_turn) -> None:
    sid = sc.create_session(finalize_active=False)
    sc.send_message("hi", session_id=sid)
    hist = sc.get_history(session_id=sid)
    assert any(m["role"] == "user" for m in hist)
    assert any(m["role"] == "assistant" for m in hist)
