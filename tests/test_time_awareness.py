"""Message timestamps + the per-turn time note (agent side).

- ``ts`` survives _message_to_dict / history normalisation but never reaches Ollama.
- Every turn carries a "[Time] It is …" system note right before the user message;
  after a long idle gap it also says when the previous message was sent.
- The note is never stored, not even on turn 1.
"""

from datetime import datetime
from unittest.mock import MagicMock

import pytest

import celestia_core.agent as agent
import celestia_core.security as sec


@pytest.fixture()
def mock_ollama(monkeypatch):
    client = MagicMock()
    client.chat.return_value = {"message": {"role": "assistant", "content": "Hi!"}}
    monkeypatch.setattr(agent, "_ollama_client", lambda: client)
    return client


@pytest.fixture(autouse=True)
def isolate(monkeypatch):
    monkeypatch.setattr(sec, "get_mode", lambda: "safe")
    monkeypatch.setattr(agent, "_memory_context", lambda q: "")
    monkeypatch.setattr("celestia_core.security.preflight_chat_pc", lambda msg: None)


def _sent_messages(client) -> list[dict]:
    return client.chat.call_args.kwargs["messages"]


def test_message_to_dict_keeps_numeric_ts():
    assert agent._message_to_dict({"role": "user", "content": "hi", "ts": 12.5})["ts"] == 12.5
    assert "ts" not in agent._message_to_dict({"role": "user", "content": "hi", "ts": "x"})


def test_ts_never_sent_to_model(mock_ollama):
    prior = [
        {"role": "system", "content": "You are Celestia."},
        {"role": "user", "content": "Hi", "ts": 1000.0},
        {"role": "assistant", "content": "Hey!", "ts": 1001.0},
    ]
    _, history = agent.run_turn("And now?", history=prior)
    assert all("ts" not in m for m in _sent_messages(mock_ollama))
    # ...but the stored history keeps the stamps it already had
    assert [m.get("ts") for m in history if m["role"] != "system"][:2] == [1000.0, 1001.0]


def test_time_note_sits_right_before_user_message(mock_ollama):
    agent.run_turn("What day is it?")
    sent = _sent_messages(mock_ollama)
    assert sent[-1] == {"role": "user", "content": "What day is it?"}
    assert sent[-2]["role"] == "system"
    assert sent[-2]["content"].startswith(agent._TIME_NOTE_PREFIX + "It is ")


def test_time_note_not_stored_fresh_or_continued(mock_ollama):
    _, history = agent.run_turn("Hello")
    assert not any(str(m.get("content", "")).startswith(agent._TIME_NOTE_PREFIX) for m in history)
    _, history = agent.run_turn("Again", history=history)
    assert not any(str(m.get("content", "")).startswith(agent._TIME_NOTE_PREFIX) for m in history)


def test_time_note_mentions_long_gap():
    now = datetime(2026, 10, 7, 14, 5).timestamp()
    history = [{"role": "user", "content": "x", "ts": now - 2 * 86400}]
    note = agent._time_note(history, now=now)
    assert "It is Wednesday 7 October 2026, 14:05" in note
    assert "2 days ago" in note
    assert "Monday 5 October 2026, 14:05" in note


def test_time_note_skips_short_gap_and_unstamped_history():
    now = datetime(2026, 10, 7, 14, 5).timestamp()
    assert "ago" not in agent._time_note([{"role": "user", "content": "x", "ts": now - 600}], now=now)
    assert "ago" not in agent._time_note([{"role": "user", "content": "x"}], now=now)


def test_time_note_can_be_turned_off(monkeypatch):
    monkeypatch.setattr(agent, "get", lambda key, default=None: False if key == "chat.time_awareness" else default)
    assert agent._time_note(None) is None


@pytest.mark.parametrize(
    ("seconds", "text"),
    [(5 * 60, "5 minutes"), (3 * 3600, "3 hours"), (47 * 3600, "47 hours"), (3 * 86400, "3 days")],
)
def test_fmt_gap(seconds, text):
    assert agent._fmt_gap(seconds) == text
