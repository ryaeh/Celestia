"""Recall counting should reflect *genuine* recall, not every vector hit.

build_context injects the top vector hits for any query; counting all of them
inflated recall on memories the user never actually recalled. These tests pin
the lexical-relevance gate that fixes it.
"""

from __future__ import annotations

import pytest

import skills.memory.store as store
import skills.memory.ranking as ranking


def _config(monkeypatch, **overrides):
    cfg = {
        "memory.enabled": True,
        "memory.inject": "always_budgeted",
        "memory.inject_max_lines": 8,
        "memory.inject_max_chars": 1200,
        "memory.ranking.enabled": True,
        "memory.graph.enabled": False,
    }
    cfg.update(overrides)
    monkeypatch.setattr(store, "get", lambda key, default=None: cfg.get(key, default))


@pytest.fixture
def capture_bump(monkeypatch):
    calls: list[list[str]] = []
    monkeypatch.setattr(ranking, "bump_recall", lambda ids, **k: calls.append(list(ids)))
    # rank_order is a no-op pass-through so order is deterministic.
    monkeypatch.setattr(ranking, "rank_order", lambda entries, **k: entries)
    monkeypatch.setattr(store, "_get_cached_instructions", lambda uid: [])
    return calls


def test_relevant_query_bumps_recall(capture_bump, monkeypatch):
    monkeypatch.setattr(
        store,
        "search",
        lambda *a, **k: [{"id": "m1", "kind": "fact", "text": "Doruk is building the Celestia project"}],
    )
    _config(monkeypatch)
    store.build_context("how is the Celestia project going?", "u1")
    assert capture_bump == [["m1"]]


def test_irrelevant_query_does_not_bump(capture_bump, monkeypatch):
    # Memory is injected by (mocked) vector similarity, but shares no content word
    # with the query → it must NOT be counted as recalled.
    monkeypatch.setattr(
        store,
        "search",
        lambda *a, **k: [{"id": "m1", "kind": "fact", "text": "Doruk is building the Celestia project"}],
    )
    _config(monkeypatch)
    store.build_context("what should I cook for dinner tonight?", "u1")
    assert capture_bump == []  # no bump call at all (no relevant ids)


def test_recall_relevant_helper():
    assert store._recall_relevant("the Celestia project status", "Celestia project notes")
    assert not store._recall_relevant("dinner plans", "Celestia project notes")
    # Stopword-only overlap doesn't count.
    assert not store._recall_relevant("what is that", "that was the thing")
