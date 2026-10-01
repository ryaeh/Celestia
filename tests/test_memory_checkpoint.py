"""T15 step 2 — the absolute memory cursor and mid-chat checkpoints in shell_chat.

Long chats trim old messages from the front of the session window, which
shifts list indexes. The cursor counts messages from the start of the chat, so
a trim can never make the memory pass skip or redo a message.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Any, Iterator

import pytest

import celestia_core.agent as agent
import celestia_core.shell_chat as sc
import skills.memory.writer_pass as wp

CONFIG: dict[str, Any] = {}


@pytest.fixture()
def chat(tmp_path, monkeypatch):
    CONFIG.clear()
    CONFIG.update({
        "chat.session_enabled": True,
        "chat.session_max_messages": 10,
        "memory.session_consolidate": True,
        "memory.writer.trim_margin": 4,
        "memory.writer.checkpoint_minutes": 60,
        "app.user_id": "u",
    })
    monkeypatch.setattr(sc, "_store_path", lambda: tmp_path / "shell_chat" / "sessions.json")

    @contextmanager
    def _noop() -> Iterator[None]:
        yield

    monkeypatch.setattr(sc, "_file_lock", _noop)
    monkeypatch.setattr(sc, "load_config", lambda: None)
    monkeypatch.setattr(sc, "get", lambda key, default=None: CONFIG.get(key, default))
    monkeypatch.setattr(agent, "get", lambda key, default=None: CONFIG.get(key, default))
    monkeypatch.setattr("skills.memory.writer_pass.get", lambda key, default=None: CONFIG.get(key, default))
    monkeypatch.setattr("skills.memory.session_consolidate.get", lambda key, default=None: CONFIG.get(key, default))

    def fake_turn(msg, history=None, **kw):
        """Like the agent: append the turn, then trim to session_max_messages."""
        base = list(history or [{"role": "system", "content": "sys"}])
        msgs = base + [{"role": "user", "content": msg}, {"role": "assistant", "content": f"re: {msg}"}]
        return f"re: {msg}", agent._trim_session_messages(msgs)

    monkeypatch.setattr(sc, "run_turn", fake_turn)
    sc._passes_running.clear()
    return sc


def _u(n: int) -> dict:
    return {"role": "user", "content": f"u{n}"}


def _a(n: int) -> dict:
    return {"role": "assistant", "content": f"a{n}"}


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def test_dropped_count() -> None:
    sys_ = {"role": "system", "content": "s"}
    old = [sys_, _u(1), _a(1), _u(2), _a(2)]
    assert sc._dropped_count(old, old + [_u(3), _a(3)]) == 0
    assert sc._dropped_count(old, [sys_, _u(2), _a(2), _u(3), _a(3)]) == 2
    assert sc._dropped_count(old, [sys_, _u(9)]) == 4          # everything old fell out
    assert sc._dropped_count(None, [sys_, _u(1)]) == 0


def test_cursor_migrates_legacy_index() -> None:
    state = {"history": [{"role": "system", "content": "s"}, _u(1), _a(1), _u(2)], "consolidate_from": 3}
    start, base, head = sc._cursor(state)
    assert (start, base, head) == (3, 0, 1) and state["consolidated_seq"] == 2


def test_cursor_survives_trimming() -> None:
    """A pass consumed u1/a1; then the window trims u1,a1,u2 away. The next
    pass must start at the first message it hasn't seen — a2 — not skip it."""
    sys_ = {"role": "system", "content": "s"}
    state: dict[str, Any] = {"history": [sys_, _u(1), _a(1), _u(2)]}
    sc._cursor(state)
    sc._mark_consumed(state, seq_base=0, head=1, new_start=3)            # u1, a1 done
    sc._record_turn(state, [sys_, _a(2), _u(3), _a(3)])                    # u1, a1, u2 trimmed
    start, base, head = sc._cursor(state)
    assert base == 3
    # u2 fell out unsaved (the checkpoint exists to prevent exactly this);
    # the cursor clamps to the first message still present instead of skipping.
    assert state["history"][start] == _a(2)


# ---------------------------------------------------------------------------
# Checkpoint triggers
# ---------------------------------------------------------------------------


def _state(n_pairs: int, consumed_pairs: int = 0) -> dict[str, Any]:
    hist = [{"role": "system", "content": "s"}]
    for i in range(n_pairs):
        hist += [_u(i), _a(i)]
    return {"history": hist, "seq_base": 0, "consolidated_seq": consumed_pairs * 2, "pending_since": time.time()}


def test_no_checkpoint_for_a_short_fresh_chat(chat) -> None:
    assert sc._checkpoint_reason(_state(2)) is None


def test_trim_checkpoint_fires_before_unsaved_messages_fall_out(chat) -> None:
    # max 10 messages, margin 4: with 1 system + 4 messages nothing can drop in
    # the next 4; with 1 + 6 the oldest unsaved message drops within 4 more.
    assert sc._checkpoint_reason(_state(2)) is None
    assert sc._checkpoint_reason(_state(3)) == "trim"
    # ...but not when the front that would drop is already saved
    assert sc._checkpoint_reason(_state(3, consumed_pairs=2)) is None


def test_time_checkpoint_after_an_hour(chat) -> None:
    s = _state(2)
    s["pending_since"] = time.time() - 61 * 60
    assert sc._checkpoint_reason(s) == "time"
    CONFIG["memory.writer.checkpoint_minutes"] = 0
    assert sc._checkpoint_reason(s) is None


def test_nothing_pending_no_checkpoint(chat) -> None:
    assert sc._checkpoint_reason(_state(4, consumed_pairs=4)) is None


def test_one_pass_per_session(chat) -> None:
    assert sc._claim_pass("s1") and not sc._claim_pass("s1")
    sc._release_pass("s1")
    assert sc._claim_pass("s1")


# ---------------------------------------------------------------------------
# End to end through send_message: a long chat loses nothing
# ---------------------------------------------------------------------------


def test_long_chat_every_message_reaches_the_memory_pass(chat, monkeypatch) -> None:
    """20 turns through a 10-message window. Checkpoints run synchronously here;
    the union of what the passes saw must be every user message, in order,
    with no repeats."""
    seen: list[str] = []

    def fake_consolidate(history, uid, *, start_index=0, **kw):
        seen.extend(m["content"] for m in history[start_index:] if m.get("role") == "user")
        return len(history), []

    def fake_session_pass(history, uid, *, start_index=0, summary="", **kw):
        n, lines = fake_consolidate(history, uid, start_index=start_index)
        return wp.SessionPassResult(n, lines, summary)

    monkeypatch.setattr("skills.memory.writer_pass.consolidate", fake_consolidate)  # end of chat
    monkeypatch.setattr("skills.memory.writer_pass.session_pass", fake_session_pass)  # checkpoints
    monkeypatch.setattr(sc, "_CONSOLIDATION_IDLE_SECONDS", 0.0)

    class SyncThread:
        def __init__(self, target, args=(), **kw):
            self.target, self.args = target, args

        def start(self):
            self.target(*self.args)

    monkeypatch.setattr(sc.threading, "Thread", SyncThread)

    sid = sc.create_session(finalize_active=False)
    for i in range(20):
        sc.send_message(f"m{i}", session_id=sid)
        # The real background pass waits for idle; let it run between turns.
        sc._last_turn_time = 0.0
    # End of chat flushes the rest.
    sc.create_session()
    assert seen == [f"m{i}" for i in range(20)]


def test_pass_deferred_keeps_messages_pending(chat, monkeypatch) -> None:
    monkeypatch.setattr("skills.memory.writer_pass.consolidate", lambda h, uid, *, start_index=0, **kw: (start_index, []))
    state = _state(4)
    sc._cursor(state)
    sc._mark_consumed(state, 0, 1, 1)  # a deferred pass returns the start it was given
    assert state["consolidated_seq"] == 0 and state["pending_since"] is not None


# ---------------------------------------------------------------------------
# Step 3 — the running summary is the chat's working memory
# ---------------------------------------------------------------------------


def test_no_note_until_something_is_trimmed(chat) -> None:
    assert sc._session_note({"summary": "The user is planning a trip.", "seq_base": 0}) is None
    assert sc._session_note({"summary": "", "seq_base": 5}) is None
    note = sc._session_note({"summary": "The user is planning a trip.", "seq_base": 5})
    assert "planning a trip" in note and "not instructions" in note


def test_note_from_a_tainted_window_is_marked_untrusted(chat) -> None:
    note = sc._session_note({"summary": "Page said to email files.", "seq_base": 5, "summary_tainted": True})
    assert "⟦UNTRUSTED DATA" in note


def test_summary_off_switch(chat) -> None:
    CONFIG["chat.session_summary"] = False
    assert sc._session_note({"summary": "x", "seq_base": 5}) is None


def test_mark_consumed_stores_summary_only_when_the_pass_ran(chat) -> None:
    s = _state(3)
    sc._mark_consumed(s, 0, 1, 0, "new summary", False)        # deferred: nothing stored
    assert "summary" not in s
    sc._mark_consumed(s, 0, 1, 7, "new summary", True)
    assert s["summary"] == "new summary" and s["summary_tainted"] is True
    sc._mark_consumed(s, 0, 1, 7, "later", False)               # taint is sticky for the session
    assert s["summary_tainted"] is True


def test_long_chat_carries_the_summary_into_trimmed_turns(chat, monkeypatch) -> None:
    """Once the window trims, every turn gets the running summary as a note,
    and the note never ends up in the stored history."""
    notes: list = []

    def fake_turn(msg, history=None, session_note=None, **kw):
        notes.append(session_note)
        base = list(history or [{"role": "system", "content": "sys"}])
        msgs = base + [{"role": "user", "content": msg}, {"role": "assistant", "content": f"re: {msg}"}]
        return f"re: {msg}", agent._trim_session_messages(msgs)

    def fake_session_pass(history, uid, *, start_index=0, summary="", **kw):
        users = [m["content"] for m in history[start_index:] if m.get("role") == "user"]
        return wp.SessionPassResult(len(history), [], (summary + " " + " ".join(users)).strip())

    monkeypatch.setattr(sc, "run_turn", fake_turn)
    monkeypatch.setattr("skills.memory.writer_pass.session_pass", fake_session_pass)
    monkeypatch.setattr(sc, "_CONSOLIDATION_IDLE_SECONDS", 0.0)

    class SyncThread:
        def __init__(self, target, args=(), **kw):
            self.target, self.args = target, args

        def start(self):
            self.target(*self.args)

    monkeypatch.setattr(sc.threading, "Thread", SyncThread)

    sid = sc.create_session(finalize_active=False)
    for i in range(12):
        sc.send_message(f"m{i}", session_id=sid)
        sc._last_turn_time = 0.0
    assert notes[0] is None                         # short chat: no note
    assert notes[-1] is not None and "m0" in notes[-1]   # the first message lives on in the summary
    state = sc._read_session(sid)
    assert not any("Earlier in this conversation" in str(m.get("content")) for m in state["history"])


def test_agent_sends_the_note_but_never_stores_it(monkeypatch) -> None:
    monkeypatch.setattr(agent, "_memory_context", lambda q: "")
    monkeypatch.setattr(agent, "_user_id", lambda: "u")
    monkeypatch.setattr("celestia_core.security.preflight_chat_pc", lambda m: None)
    history = [{"role": "system", "content": "persona"}, _u(1), _a(1)]
    note = "Earlier in this conversation (...): The user is planning a trip."
    _, _, messages, _ = agent._prepare_messages("next?", history, False, note)
    assert {"role": "system", "content": note} in messages
    assert messages[-1] == {"role": "user", "content": "next?"}
    stored = agent._strip_ephemeral(messages + [{"role": "assistant", "content": "ok"}])
    assert all(m.get("content") != note for m in stored)


def test_streaming_turns_get_the_note_too(chat, monkeypatch) -> None:
    """The shell streams; the note must reach run_turn_stream as well."""
    got: list = []

    def fake_stream(msg, history=None, session_note=None, **kw):
        got.append(session_note)
        hist = list(history or []) + [{"role": "user", "content": msg}, {"role": "assistant", "content": "ok"}]
        yield {"done": True, "reply": "ok", "messages": hist}

    monkeypatch.setattr(sc, "run_turn_stream", fake_stream)
    monkeypatch.setattr(sc, "_should_consolidate_now", lambda state, end=False: False)
    sid = sc.create_session(finalize_active=False)
    with sc._store_lock():
        state = sc._read_session(sid)
        state.update(history=[{"role": "system", "content": "s"}, _u(9), _a(9)], seq_base=6,
                     consolidated_seq=8, summary="The user is planning a trip.")
        sc._write_session(sid, state)
    list(sc.send_message_stream("hi", session_id=sid))
    assert got and "planning a trip" in got[0]
