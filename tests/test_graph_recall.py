"""Tests for the graph branch of store.build_context (Feature 10, A3).

These verify the *hybrid retrieval* wiring: when memory.graph.enabled is on and
the query names a known entity, graph-walk lines are injected alongside (mocked)
similarity hits. The mem0/Chroma path is stubbed out (search +
_get_cached_instructions), so no Ollama/embeddings are needed.
"""

from __future__ import annotations

import pytest

import skills.memory.store as store
import skills.memory.graph_store as gs


@pytest.fixture()
def wired(tmp_path, monkeypatch):
    """Graph db redirected to tmp; mem0 similarity + instructions stubbed empty."""
    db = tmp_path / "graph.db"
    monkeypatch.setattr(gs, "_db_path", lambda: db)
    gs.reset_connection()
    # Isolate the graph branch: no semantic hits, no pinned instructions.
    monkeypatch.setattr(store, "search", lambda *a, **k: [])
    monkeypatch.setattr(store, "_get_cached_instructions", lambda uid: [])
    yield
    gs.reset_connection()


def _config(monkeypatch, **overrides):
    cfg = {
        "memory.enabled": True,
        "memory.inject": "always_budgeted",
        "memory.inject_max_lines": 8,
        "memory.inject_max_chars": 1200,
        "memory.graph.enabled": True,
        "memory.graph.walk_hops": 2,
    }
    cfg.update(overrides)
    monkeypatch.setattr(store, "get", lambda key, default=None: cfg.get(key, default))


def test_build_context_injects_graph_facts(wired, monkeypatch) -> None:
    gs.add_relation("Celestia", "uses", "Ollama")
    _config(monkeypatch)
    out = store.build_context("what does Celestia use?", "u1")
    assert "[graph]" in out
    assert "Celestia uses Ollama" in out


def test_build_context_walks_multiple_hops(wired, monkeypatch) -> None:
    gs.add_relation("Doruk", "works_on", "Celestia")
    gs.add_relation("Celestia", "uses", "Ollama")
    _config(monkeypatch)
    out = store.build_context("tell me about Doruk", "u1")
    assert "Celestia uses Ollama" in out  # reached at hop 2


def test_build_context_graph_disabled_no_graph_lines(wired, monkeypatch) -> None:
    gs.add_relation("Celestia", "uses", "Ollama")
    _config(monkeypatch, **{"memory.graph.enabled": False})
    out = store.build_context("what does Celestia use?", "u1")
    assert "[graph]" not in out


def test_build_context_unknown_entity_no_graph_lines(wired, monkeypatch) -> None:
    gs.add_relation("Celestia", "uses", "Ollama")
    _config(monkeypatch)
    out = store.build_context("what's the weather like today?", "u1")
    assert "[graph]" not in out


def test_build_context_respects_hop_config(wired, monkeypatch) -> None:
    gs.add_relation("Doruk", "works_on", "Celestia")
    gs.add_relation("Celestia", "uses", "Ollama")
    _config(monkeypatch, **{"memory.graph.walk_hops": 1})
    out = store.build_context("tell me about Doruk", "u1")
    assert "Doruk works on Celestia" in out
    assert "Celestia uses Ollama" not in out  # 2 hops away, hop limit is 1


def test_build_context_empty_when_nothing_relevant(wired, monkeypatch) -> None:
    _config(monkeypatch)
    out = store.build_context("random text with no entities", "u1")
    assert out == ""
