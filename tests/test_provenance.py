"""Tests for build_context provenance (the "why did you say that?" feature).

build_context records which memory/graph entries it injected into a ContextVar,
drained by the chat layer via take_last_provenance(). The mem0/Chroma path is
stubbed so no Ollama/embeddings are needed.
"""

from __future__ import annotations

import pytest

import skills.memory.store as store


def _config(monkeypatch, **overrides):
    cfg = {
        "memory.enabled": True,
        "memory.inject": "always_budgeted",
        "memory.inject_max_lines": 8,
        "memory.inject_max_chars": 1200,
        "memory.ranking.enabled": False,
        "memory.graph.enabled": False,
    }
    cfg.update(overrides)
    monkeypatch.setattr(store, "get", lambda key, default=None: cfg.get(key, default))


def test_provenance_records_injected_memory_hits(monkeypatch):
    monkeypatch.setattr(store, "_get_cached_instructions", lambda uid: [])
    monkeypatch.setattr(
        store,
        "search",
        lambda *a, **k: [
            {"id": "m1", "kind": "fact", "text": "Doruk has an RTX 4090"},
        ],
    )
    _config(monkeypatch)

    out = store.build_context("what gpu do I have?", "u1")
    assert "RTX 4090" in out

    prov = store.take_last_provenance()
    assert len(prov) == 1
    assert prov[0]["id"] == "m1"
    assert prov[0]["kind"] == "fact"
    assert prov[0]["source"] == "memory"
    assert "RTX 4090" in prov[0]["text"]
    # Internal tracking key must not leak.
    assert "_line" not in prov[0]


def test_provenance_drains_to_empty(monkeypatch):
    monkeypatch.setattr(store, "_get_cached_instructions", lambda uid: [])
    monkeypatch.setattr(store, "search", lambda *a, **k: [{"id": "m1", "kind": "fact", "text": "hello world fact"}])
    _config(monkeypatch)

    store.build_context("query", "u1")
    assert store.take_last_provenance()  # non-empty first drain
    assert store.take_last_provenance() == []  # cleared after


def test_provenance_empty_when_nothing_injected(monkeypatch):
    monkeypatch.setattr(store, "_get_cached_instructions", lambda uid: [])
    monkeypatch.setattr(store, "search", lambda *a, **k: [])
    _config(monkeypatch)

    out = store.build_context("a query with no hits", "u1")
    assert out == ""
    assert store.take_last_provenance() == []
