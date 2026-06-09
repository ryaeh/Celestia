"""Guards the fix for blocking session-switch: graph extraction (an extra LLM
call) must run only in the background consolidation pass, never on the
synchronous end-of-session finalize that create/switch-chat blocks on.

The typed-memory machinery is short-circuited so the test isolates the graph
branch; both LLM calls are stubbed.
"""

from __future__ import annotations

import json

import pytest

import skills.memory.session_consolidate as sc
import skills.memory.graph_extract as ge
import skills.memory.graph_store as gs


@pytest.fixture()
def consolidate_env(tmp_path, monkeypatch):
    db = tmp_path / "graph.db"
    monkeypatch.setattr(gs, "_db_path", lambda: db)
    gs.reset_connection()
    monkeypatch.setattr(ge, "append_event", lambda **kw: None)

    cfg = {
        "memory.graph.enabled": True,
        "memory.graph.deep_pass": "background",
        "memory.session_consolidate_max_facts": 3,
    }
    monkeypatch.setattr(sc, "get", lambda key, default=None: cfg.get(key, default))
    monkeypatch.setattr(ge, "get", lambda key, default=None: cfg.get(key, default))

    # Short-circuit the typed-memory pipeline (no mem0, empty typed output).
    monkeypatch.setattr(sc, "should_run_consolidation", lambda *a, **k: True)
    monkeypatch.setattr(sc, "get_all_entries", lambda *a, **k: [])
    monkeypatch.setattr(
        sc.ollama,
        "chat",
        lambda *a, **k: {"message": {"content": json.dumps({"facts": [], "instructions": [], "summaries": [], "tasks": []})}},
    )
    # Graph extraction LLM → one relation.
    monkeypatch.setattr(
        ge.ollama,
        "chat",
        lambda *a, **k: {"message": {"content": json.dumps({"relations": [{"subject": "Doruk", "predicate": "works on", "object": "Celestia"}]})}},
    )
    yield gs
    gs.reset_connection()


def _msgs():
    return [
        {"role": "user", "content": "My main project is Celestia and I work on it daily with Ollama."},
        {"role": "assistant", "content": "Got it."},
        {"role": "user", "content": "Yes, please remember that."},
        {"role": "assistant", "content": "Will do."},
    ]


def test_sync_finalize_skips_graph_extraction(consolidate_env) -> None:
    # extract_graph=False is what _maybe_consolidate passes on session finalize.
    sc.consolidate_session_messages(_msgs(), "u1", extract_graph=False)
    assert consolidate_env.stats()["edges"] == 0


def test_background_pass_extracts_graph(consolidate_env) -> None:
    # The background consolidation pass uses the default (extract_graph=True).
    sc.consolidate_session_messages(_msgs(), "u1", extract_graph=True)
    assert "Doruk works on Celestia" in consolidate_env.current_relations()
