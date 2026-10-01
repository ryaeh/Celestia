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

    def fake_session_pass(history, uid, *, start_index=0, summary=None, **kw):
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

    def fake_session_pass(history, uid, *, start_index=0, summary=None, **kw):
        users = [m["content"] for m in history[start_index:] if m.get("role") == "user"]
        prev = (summary or {}).get("facts", [])
        return wp.SessionPassResult(len(history), [], {"goal": "Testing", "facts": prev + users})

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
    assert not any("Notes on this conversation" in str(m.get("content")) for m in state["history"])


def test_agent_sends_the_note_but_never_stores_it(monkeypatch) -> None:
    monkeypatch.setattr(agent, "_memory_context", lambda q: "")
    monkeypatch.setattr(agent, "_user_id", lambda: "u")
    monkeypatch.setattr("celestia_core.security.preflight_chat_pc", lambda m: None)
    history = [{"role": "system", "content": "persona"}, _u(1), _a(1)]
    note = "Notes on this conversation so far (...):\nGoal: The user is planning a trip."
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


def test_structured_summary_is_rendered_into_the_note(chat) -> None:
    note = sc._session_note({"seq_base": 4, "summary": {
        "goal": "Plan a Berlin trip", "now": "Debugging the server",
        "details": ["Flight May 12", "Port 9000"], "open": ["Renew passport"]}})
    assert note.startswith("Notes on this conversation so far")
    for part in ("Goal: Plan a Berlin trip", "Right now: Debugging the server", "- Flight May 12", "Still open:"):
        assert part in note
    assert sc._session_note({"seq_base": 4, "summary": {"goal": "", "facts": []}}) is None


# ---------------------------------------------------------------------------
# Archive + recall — trimmed messages are kept and come back when referred to
# ---------------------------------------------------------------------------


def test_trimmed_messages_move_to_the_archive(chat) -> None:
    sys_ = {"role": "system", "content": "s"}
    tool = {"role": "tool", "content": "raw tool output"}
    state: dict[str, Any] = {"history": [sys_, _u(1), tool, _a(1), _u(2), _a(2)]}
    sc._record_turn(state, [sys_, _u(2), _a(2), _u(3), _a(3)])         # u1, tool, a1 trimmed
    assert [(m["role"], m["content"], m["seq"]) for m in state["archive"]] == [("user", "u1", 0), ("assistant", "a1", 2)]
    assert state["seq_base"] == 3


def test_archive_cap(chat) -> None:
    CONFIG["chat.archive_max_messages"] = 3
    sys_ = {"role": "system", "content": "s"}
    state: dict[str, Any] = {"history": [sys_] + [_u(i) for i in range(6)]}
    sc._record_turn(state, [sys_, _u(5)])
    assert [m["content"] for m in state["archive"]] == ["u2", "u3", "u4"]


def test_whole_chat_stays_visible_after_trimming(chat, monkeypatch) -> None:
    monkeypatch.setattr(sc, "_should_consolidate_now", lambda state, end=False: False)
    sid = sc.create_session(finalize_active=False)
    for i in range(12):
        sc.send_message(f"m{i}", session_id=sid)
    shown = [m["content"] for m in sc.get_history(sid) if m["role"] == "user"]
    assert shown == [f"m{i}" for i in range(12)]                       # window is 10 messages
    assert len(sc._read_session(sid)["history"]) <= 11              # system prompt + last 10
    assert any(r["id"] == sid for r in sc.search_sessions("m0"))       # search sees the archive too


ARCHIVE = [
    {"role": "user", "content": "my shell server says address already in use on port 8765", "seq": 0},
    {"role": "assistant", "content": "Find the process with: netstat -ano | findstr 8765", "seq": 1},
    {"role": "user", "content": "I'm hosting dinner on Saturday for six people", "seq": 2},
    {"role": "assistant", "content": "Fun! Any dietary restrictions?", "seq": 3},
]


def test_recall_brings_back_the_matching_exchange(chat) -> None:
    note = sc._recall_note({"archive": ARCHIVE}, "what was that netstat command you gave me earlier?")
    assert note.startswith("From earlier in this chat")
    assert "netstat -ano | findstr 8765" in note and "[User] my shell server" in note   # with its question
    assert "dinner" not in note


def test_recall_needs_two_terms_without_a_back_reference(chat) -> None:
    assert sc._recall_note({"archive": ARCHIVE}, "is the server ok") is None          # one weak term
    assert sc._recall_note({"archive": ARCHIVE}, "dinner on Saturday, should I make soup?") is not None
    assert sc._recall_note({"archive": ARCHIVE}, "tell me a joke") is None


def test_recall_is_marked_untrusted_after_a_tainted_window(chat) -> None:
    note = sc._recall_note({"archive": ARCHIVE, "summary_tainted": True}, "which port was it again? 8765?")
    assert "⟦UNTRUSTED DATA" in note


def test_recall_off_switch_and_turn_notes(chat) -> None:
    state = {"archive": ARCHIVE, "seq_base": 4, "summary": {"goal": "Fix the server"}}
    both = sc._turn_notes(state, "what was the netstat command again?")
    assert "Goal: Fix the server" in both and "netstat -ano" in both
    CONFIG["chat.recall_archived"] = False
    assert "netstat" not in sc._turn_notes(state, "what was the netstat command again?")


def test_recall_reaches_the_turn(chat, monkeypatch) -> None:
    got: list = []

    def fake_turn(msg, history=None, session_note=None, **kw):
        got.append(session_note)
        return "ok", list(history or []) + [{"role": "user", "content": msg}, {"role": "assistant", "content": "ok"}]

    monkeypatch.setattr(sc, "run_turn", fake_turn)
    monkeypatch.setattr(sc, "_should_consolidate_now", lambda state, end=False: False)
    sid = sc.create_session(finalize_active=False)
    with sc._store_lock():
        state = sc._read_session(sid)
        state.update(history=[{"role": "system", "content": "s"}, _u(9), _a(9)], archive=ARCHIVE, seq_base=4,
                     consolidated_seq=6)
        sc._write_session(sid, state)
    sc.send_message("what was the netstat command you gave me earlier?", session_id=sid)
    assert got and "netstat -ano" in got[0]


# ---------------------------------------------------------------------------
# Step 4 — idle end of chat, the "saving" notice, the notes panel
# ---------------------------------------------------------------------------


def _idle_session(chat, *, pairs: int = 3, idle_s: float = 0.0) -> str:
    sid = chat.create_session(finalize_active=False)
    with chat._store_lock():
        state = chat._read_session(sid)
        state.update(_state(pairs))
        state["updated_at"] = time.time() - idle_s
        chat._write_session(sid, state)
    return sid


def test_idle_sweep_saves_a_chat_left_idle(chat, monkeypatch) -> None:
    seen: list = []

    def fake_consolidate(history, uid, *, start_index=0, end=False, **kw):
        seen.append((start_index, len(history), end))
        return len(history), ["saved"]

    monkeypatch.setattr("skills.memory.writer_pass.consolidate", fake_consolidate)
    sid = _idle_session(chat, idle_s=21 * 60)
    assert chat.idle_sweep() == ["saved"]
    assert seen == [(1, 7, True)]
    with chat._store_lock():
        assert chat._cursor(chat._read_session(sid))[0] == 7
    assert chat.idle_sweep() == [] and len(seen) == 1   # nothing new: no second pass
    assert chat.memory_saving() is None                 # released


def test_idle_sweep_waits_for_the_idle_time(chat, monkeypatch) -> None:
    monkeypatch.setattr("skills.memory.writer_pass.consolidate",
                        lambda *a, **k: pytest.fail("ran too early"))
    _idle_session(chat, idle_s=5 * 60)
    assert chat.idle_sweep() == []
    CONFIG["memory.writer.idle_minutes"] = 0             # off switch
    assert chat.idle_sweep(now=time.time() + 10_000) == []


def test_idle_sweep_skips_a_session_already_being_saved(chat, monkeypatch) -> None:
    monkeypatch.setattr("skills.memory.writer_pass.consolidate",
                        lambda *a, **k: pytest.fail("stacked a second pass"))
    sid = _idle_session(chat, idle_s=30 * 60)
    assert chat._claim_pass(sid, "checkpoint")
    assert chat.idle_sweep() == []
    assert chat.memory_saving()["kind"] == "checkpoint"
    chat._release_pass(sid)


def test_memory_saving_reports_the_running_pass(chat) -> None:
    assert chat.memory_saving() is None
    assert chat._claim_pass("s1", "end")
    info = chat.memory_saving()
    assert info["kind"] == "end" and info["since"] > 0
    chat._release_pass("s1")
    assert chat.memory_saving() is None


def test_voice_notice(chat, monkeypatch) -> None:
    spoken: list[str] = []
    monkeypatch.setattr("skills.tts.speak", lambda text, *a, **k: spoken.append(text))
    chat._voice_notice()
    assert spoken == [chat._VOICE_NOTICE]
    CONFIG["memory.writer.voice_notice_text"] = "Hold on."
    chat._voice_notice()
    CONFIG["memory.writer.voice_notice"] = False
    chat._voice_notice()
    assert spoken == [chat._VOICE_NOTICE, "Hold on."]


def test_get_notes(chat) -> None:
    sid = chat.create_session(finalize_active=False)
    notes = chat.get_notes(sid)
    assert notes["session_id"] == sid and notes["empty"] and not notes["in_use"]
    with chat._store_lock():
        state = chat._read_session(sid)
        state.update(summary={"goal": "Plan a trip", "details": ["Flight LH123"]},
                     archive=ARCHIVE, seq_base=4, summary_tainted=True)
        chat._write_session(sid, state)
    notes = chat.get_notes(sid)
    assert notes["notes"]["goal"] == "Plan a trip" and notes["notes"]["details"] == ["Flight LH123"]
    assert not notes["empty"] and notes["in_use"] and notes["untrusted"]
    assert notes["archived"] == len(ARCHIVE)
