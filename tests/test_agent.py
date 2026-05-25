"""Tests for celestia_core/agent.py — run_turn() with a mocked Ollama client.

Strategy:
- Mock _ollama_client() to return a MagicMock whose .chat() returns a canned
  dict response.  This avoids any real Ollama dependency.
- Mock _memory_context() to return "" so Chroma is never touched.
- Mock preflight_chat_pc() to return None (no pre-flight short-circuit).
- Lock security mode to "safe" so no PC-control scope checks are triggered.
"""

from unittest.mock import MagicMock, patch

import pytest

import celestia_core.security as sec
from celestia_core.agent import _strip_ephemeral, run_turn


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _fake_chat_response(content: str) -> dict:
    """Minimal response shape that _message_to_dict() accepts."""
    return {"message": {"role": "assistant", "content": content}}


@pytest.fixture()
def mock_ollama(monkeypatch):
    """Patch _ollama_client() so run_turn() never calls a real Ollama server."""
    client = MagicMock()
    client.chat.return_value = _fake_chat_response("Hello from mock!")
    monkeypatch.setattr("celestia_core.agent._ollama_client", lambda: client)
    return client


@pytest.fixture(autouse=True)
def isolate_security(monkeypatch):
    """Pin security mode to 'safe' and bypass disk I/O for all agent tests."""
    monkeypatch.setattr(sec, "get_mode", lambda: "safe")


@pytest.fixture(autouse=True)
def no_memory(monkeypatch):
    """Return empty memory context so Chroma is never touched."""
    monkeypatch.setattr("celestia_core.agent._memory_context", lambda q: "")


@pytest.fixture(autouse=True)
def no_preflight(monkeypatch):
    """Disable preflight short-circuit (tested separately in test_security.py)."""
    monkeypatch.setattr("celestia_core.security.preflight_chat_pc", lambda msg: None)


# ---------------------------------------------------------------------------
# Basic run_turn() behaviour
# ---------------------------------------------------------------------------

def test_run_turn_returns_string_and_history(mock_ollama):
    text, history = run_turn("Hello")
    assert isinstance(text, str)
    assert len(text) > 0
    assert isinstance(history, list)
    assert len(history) > 0


def test_run_turn_reply_matches_mock(mock_ollama):
    text, _ = run_turn("Hello")
    assert text == "Hello from mock!"


def test_run_turn_history_has_user_and_assistant(mock_ollama):
    _, history = run_turn("Hello")
    roles = {m["role"] for m in history}
    assert "user" in roles
    assert "assistant" in roles


def test_run_turn_no_ephemeral_in_history(mock_ollama):
    """Stored history must not contain mid-turn system injections.

    Per-turn hints added AFTER the first user turn (between an assistant reply
    and the next user message) must be stripped by _strip_ephemeral().
    System messages before the first user turn are intentional and kept.
    """
    # Simulate a second turn by providing history from a first turn
    prior = [
        {"role": "system", "content": "You are Celestia."},
        {"role": "user", "content": "Hi"},
        {"role": "assistant", "content": "Hello!"},
    ]
    _, history = run_turn("Open YouTube", history=prior)
    # Find the index of the last user message
    last_user_idx = max(i for i, m in enumerate(history) if m["role"] == "user")
    # Nothing after the last user message should be a system message
    post_user_systems = [m for m in history[last_user_idx + 1:] if m["role"] == "system"]
    assert post_user_systems == [], (
        "System messages must not appear after the last user turn in stored history"
    )


def test_run_turn_with_existing_history(mock_ollama):
    """Passing prior history should not crash and should extend it."""
    prior = [
        {"role": "system", "content": "You are Celestia."},
        {"role": "user", "content": "Hi"},
        {"role": "assistant", "content": "Hey!"},
    ]
    text, history = run_turn("What is 2+2?", history=prior)
    assert isinstance(text, str)
    assert len(history) > len(prior)


# ---------------------------------------------------------------------------
# LLM error path
# ---------------------------------------------------------------------------

def test_run_turn_handles_llm_error(monkeypatch, mock_ollama):
    """If ollama.Client.chat() raises, run_turn must return an error string
    rather than propagating the exception."""
    mock_ollama.chat.side_effect = Exception("connection refused")
    text, history = run_turn("Hello")
    assert "LLM error" in text
    assert isinstance(history, list)


# ---------------------------------------------------------------------------
# Tool-call path
# ---------------------------------------------------------------------------

def test_run_turn_tool_round_then_text(mock_ollama):
    """Simulate one tool call followed by a text reply."""
    tool_response = {
        "message": {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {"function": {"name": "open_path", "arguments": {"path": "notepad"}}}
            ],
        }
    }
    text_response = _fake_chat_response("I tried to open Notepad.")
    mock_ollama.chat.side_effect = [tool_response, text_response]

    with patch("celestia_core.agent.execute_tool", return_value="Blocked: safe mode"):
        text, history = run_turn("Open Notepad")

    assert isinstance(text, str)
    tool_msgs = [m for m in history if m.get("role") == "tool"]
    assert len(tool_msgs) == 1
