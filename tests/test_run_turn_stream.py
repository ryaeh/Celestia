"""Tests for celestia_core/agent.py — run_turn_stream() generator.

Strategy mirrors test_agent.py: mock _ollama_client(), _memory_context(),
preflight_chat_pc(), build_system_prompt(), and tool_schemas() so no real
Ollama server, Chroma, or disk access is needed.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

import celestia_core.agent as agent_mod
import celestia_core.security as sec
from celestia_core.agent import run_turn_stream


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _stream_chunks(pieces: list[str], *, tool_calls: list | None = None) -> list[dict]:
    """Build a list of dict chunks that mimic Ollama streaming output."""
    chunks = []
    for i, piece in enumerate(pieces):
        is_last = i == len(pieces) - 1
        msg: dict[str, Any] = {"role": "assistant", "content": piece}
        if is_last and tool_calls:
            msg["tool_calls"] = tool_calls
        chunks.append({"message": msg, "done": is_last})
    return chunks


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    """Standard isolation: safe mode, no memory, no preflight, no real prompts."""
    monkeypatch.setattr(sec, "get_mode", lambda: "safe")
    monkeypatch.setattr("celestia_core.agent._memory_context", lambda q: "")
    monkeypatch.setattr("celestia_core.security.preflight_chat_pc", lambda msg: None)
    monkeypatch.setattr(agent_mod, "build_system_prompt", lambda: "You are Celestia.")
    monkeypatch.setattr(agent_mod, "tool_schemas", lambda msg="": [])


@pytest.fixture()
def stream_client(monkeypatch) -> MagicMock:
    """Mock client whose first .chat() call returns a two-chunk stream."""
    client = MagicMock()
    client.chat.return_value = iter(_stream_chunks(["Hi ", "there"]))
    monkeypatch.setattr("celestia_core.agent._ollama_client", lambda: client)
    return client


# ---------------------------------------------------------------------------
# Token streaming
# ---------------------------------------------------------------------------


def test_stream_yields_individual_tokens(stream_client) -> None:
    events = list(run_turn_stream("Hello"))
    tokens = [e for e in events if "token" in e]
    assert tokens == [{"token": "Hi "}, {"token": "there"}]


def test_stream_tokens_before_done(stream_client) -> None:
    events = list(run_turn_stream("Hello"))
    last = events[-1]
    assert "done" in last
    for e in events[:-1]:
        assert "token" in e


# ---------------------------------------------------------------------------
# Done event
# ---------------------------------------------------------------------------


def test_stream_ends_with_single_done_event(stream_client) -> None:
    events = list(run_turn_stream("Hello"))
    done_events = [e for e in events if "done" in e]
    assert len(done_events) == 1


def test_stream_done_event_contains_reply(stream_client) -> None:
    events = list(run_turn_stream("Hello"))
    done = next(e for e in events if "done" in e)
    assert done["done"] is True
    assert done["reply"] == "Hi there"


def test_stream_done_event_contains_messages(stream_client) -> None:
    events = list(run_turn_stream("Hello"))
    done = next(e for e in events if "done" in e)
    assert isinstance(done["messages"], list)
    roles = {m["role"] for m in done["messages"]}
    assert "user" in roles
    assert "assistant" in roles


# ---------------------------------------------------------------------------
# Error path
# ---------------------------------------------------------------------------


def test_stream_llm_connection_error_yields_error(monkeypatch) -> None:
    client = MagicMock()
    client.chat.side_effect = Exception("connection refused")
    monkeypatch.setattr("celestia_core.agent._ollama_client", lambda: client)
    events = list(run_turn_stream("Hello"))
    assert any("error" in e for e in events)


def test_stream_error_event_contains_message(monkeypatch) -> None:
    client = MagicMock()
    client.chat.side_effect = Exception("timeout")
    monkeypatch.setattr("celestia_core.agent._ollama_client", lambda: client)
    events = list(run_turn_stream("Hello"))
    error_events = [e for e in events if "error" in e]
    assert len(error_events) == 1
    assert "timeout" in error_events[0]["error"]


# ---------------------------------------------------------------------------
# Preflight short-circuit
# ---------------------------------------------------------------------------


def test_stream_preflight_skips_ollama(monkeypatch) -> None:
    """When preflight returns a reply, Ollama must not be called."""
    monkeypatch.setattr("celestia_core.security.preflight_chat_pc", lambda msg: "No PC access.")
    client = MagicMock()
    monkeypatch.setattr("celestia_core.agent._ollama_client", lambda: client)
    events = list(run_turn_stream("Open YouTube"))
    client.chat.assert_not_called()


def test_stream_preflight_yields_done_immediately(monkeypatch) -> None:
    monkeypatch.setattr("celestia_core.security.preflight_chat_pc", lambda msg: "No PC access.")
    monkeypatch.setattr("celestia_core.agent._ollama_client", lambda: MagicMock())
    events = list(run_turn_stream("Open YouTube"))
    tokens = [e for e in events if "token" in e]
    done = [e for e in events if "done" in e]
    assert tokens == []
    assert len(done) == 1
    assert done[0]["reply"] == "No PC access."


# ---------------------------------------------------------------------------
# Tool-call path (one round then text)
# ---------------------------------------------------------------------------


def test_stream_tool_call_then_text_reply(monkeypatch) -> None:
    """First stream has a tool call; second (non-stream) call returns text."""
    tool_call = {
        "function": {"name": "get_system_status", "arguments": {}}
    }
    stream_chunks = _stream_chunks([""], tool_calls=[tool_call])

    text_response = {"message": {"role": "assistant", "content": "Done."}}

    client = MagicMock()
    # First call (stream=True) → tool call chunk; second call (non-stream) → text
    client.chat.side_effect = [iter(stream_chunks), text_response]
    monkeypatch.setattr("celestia_core.agent._ollama_client", lambda: client)
    monkeypatch.setattr(
        agent_mod, "execute_tool", lambda name, args, uid, **kw: "CPU: 10%"
    )

    events = list(run_turn_stream("What is my CPU?"))
    done = next((e for e in events if "done" in e), None)
    assert done is not None
    assert done["reply"] == "Done."
