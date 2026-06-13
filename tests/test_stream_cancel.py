"""In-flight chat-stream cancellation (UI V2 / F3).

Covers the cancel registry (celestia_core/stream_cancel.py) and run_turn_stream's
between-token cancel hook — stop mid-stream, keep the partial reply.
"""

from unittest.mock import MagicMock

import pytest

import celestia_core.security as sec
import celestia_core.stream_cancel as sc
from celestia_core import agent


# --- registry ---------------------------------------------------------------

def test_request_cancel_on_inactive_is_noop():
    sc.end("s1")  # ensure clean
    assert sc.request_cancel("s1") is False
    assert sc.is_cancelled("s1") is False


def test_begin_then_cancel_flags_session():
    sc.begin("s2")
    assert sc.request_cancel("s2") is True
    assert sc.is_cancelled("s2") is True
    sc.end("s2")
    assert sc.is_cancelled("s2") is False


def test_begin_clears_stale_cancel():
    sc.begin("s3")
    sc.request_cancel("s3")
    sc.begin("s3")  # a new stream on the same session starts clean
    assert sc.is_cancelled("s3") is False
    sc.end("s3")


def test_empty_session_id_is_safe():
    assert sc.request_cancel("") is False
    assert sc.is_cancelled("") is False


# --- run_turn_stream cancel hook --------------------------------------------

@pytest.fixture()
def stream_env(monkeypatch):
    def chunks():
        for t in ["Hel", "lo ", "wor", "ld"]:
            yield {"message": {"content": t}, "done": False}
        yield {"message": {"content": ""}, "done": True}

    client = MagicMock()
    client.chat.return_value = chunks()
    monkeypatch.setattr(agent, "_ollama_client", lambda: client)
    monkeypatch.setattr(agent, "_memory_context", lambda q: "")
    monkeypatch.setattr(sec, "get_mode", lambda: "safe")
    monkeypatch.setattr(sec, "preflight_chat_pc", lambda msg: None)
    return client


def test_stream_cancels_after_first_token(stream_env):
    # cancel_check is polled at the top of each loop iteration; allow the first
    # token through, then request cancel before the second.
    n = {"calls": 0}

    def cancel_check():
        n["calls"] += 1
        return n["calls"] > 1

    events = list(agent.run_turn_stream("hi", cancel_check=cancel_check))
    tokens = [e["token"] for e in events if "token" in e]
    done = [e for e in events if e.get("done")]

    assert tokens == ["Hel"]                       # only the first token streamed
    assert done and done[-1].get("cancelled") is True
    assert done[-1]["reply"] == "Hel"              # partial reply kept


def test_stream_completes_without_cancel(stream_env):
    events = list(agent.run_turn_stream("hi", cancel_check=lambda: False))
    tokens = "".join(e["token"] for e in events if "token" in e)
    done = [e for e in events if e.get("done")]

    assert tokens == "Hello world"
    assert done and not done[-1].get("cancelled")
