"""Tests for skills/memory/entity_resolution.py — the idle merge pass.

Embeddings and the LLM judge are stubbed; the graph runs on a real (tmp)
SQLite store so merges are verified end-to-end.
"""

from __future__ import annotations

import pytest

import skills.memory.entity_resolution as er
import skills.memory.graph_store as gs


@pytest.fixture()
def graph(tmp_path, monkeypatch):
    db = tmp_path / "graph.db"
    monkeypatch.setattr(gs, "_db_path", lambda: db)
    gs.reset_connection()
    yield gs
    gs.reset_connection()


def _fake_embed(vectors: dict[str, list[float]]):
    """Embedding stub keyed by name. Unknown names each get a distinct unit
    vector (hash-derived) so they never look similar to anything."""

    def _embed(names, model):
        out = []
        for k, n in enumerate(names):
            if n in vectors:
                out.append(vectors[n])
            else:
                # One-hot in a dimension past the hand-crafted 3-dim vectors:
                # orthogonal to them and to every other unknown name.
                v = [0.0] * (3 + len(names))
                v[3 + k] = 1.0
                out.append(v)
        return out

    return _embed


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def test_cosine_basics() -> None:
    assert er._cosine([1, 0], [1, 0]) == pytest.approx(1.0)
    assert er._cosine([1, 0], [0, 1]) == pytest.approx(0.0)
    assert er._cosine([0, 0], [1, 0]) == 0.0


def test_candidate_pairs_skips_type_conflicts() -> None:
    nodes = [
        {"id": "a", "canonical_name": "Miso", "type": "person"},
        {"id": "b", "canonical_name": "Miso", "type": "tool"},
        {"id": "c", "canonical_name": "miso", "type": None},
    ]
    embs = [[1.0, 0.0], [1.0, 0.0], [1.0, 0.0]]
    pairs = er.candidate_pairs(nodes, embs, 0.9)
    indexed = {(i, j) for i, j, _, _ in pairs}
    assert (0, 1) not in indexed  # person vs tool never merges
    assert (0, 2) in indexed  # empty type matches anything
    assert (1, 2) in indexed


def test_candidate_pairs_lexical_squash_beats_weak_embedding() -> None:
    nodes = [
        {"id": "a", "canonical_name": "VS Code", "type": None},
        {"id": "b", "canonical_name": "vscode", "type": None},
    ]
    # Embeddings say "not similar" — the squashed names still make the pair.
    pairs = er.candidate_pairs(nodes, [[1.0, 0.0], [0.0, 1.0]], 0.9)
    assert pairs == [(0, 1, 1.0, True)]


def test_candidate_pairs_digit_squash_guard() -> None:
    nodes = [
        {"id": "a", "canonical_name": "1.5", "type": None},
        {"id": "b", "canonical_name": "15", "type": None},
    ]
    # All-digit squashes ('1.5' → '15') must not lexical-match.
    assert er.candidate_pairs(nodes, [[1.0, 0.0], [0.0, 1.0]], 0.9) == []


def test_squash_normalizes_spacing_case_punctuation() -> None:
    assert er._squash("VS Code") == "vscode"
    assert er._squash("qwen 2.5 7b") == er._squash("qwen2.5:7b")
    assert er._squash("") == ""


def test_lexical_pairs_merge_without_judge(graph, monkeypatch) -> None:
    graph.add_relation("user", "uses", "VS Code")
    graph.add_relation("vscode", "has extension", "Vim plugin")

    def _never(a, b, model):
        raise AssertionError("judge must not be consulted for lexical-identical names")

    monkeypatch.setattr(er, "_confirm_same_entity", _never)
    # Embeddings deliberately dissimilar — only the lexical rule applies.
    monkeypatch.setattr(
        er, "_embed_names", _fake_embed({"VS Code": [1.0, 0.0, 0.0], "vscode": [0.0, 1.0, 0.0]})
    )
    report = er.resolve_entities(threshold=0.9)
    assert len(report["merges"]) == 1
    assert graph.resolve_node("VS Code") == graph.resolve_node("vscode")


def test_pick_keeper_prefers_degree_then_age() -> None:
    old_hub = {"id": "a", "degree": 5, "created_at": 100.0}
    young_leaf = {"id": "b", "degree": 1, "created_at": 200.0}
    keep, dup = er._pick_keeper(young_leaf, old_hub)
    assert keep is old_hub and dup is young_leaf

    older = {"id": "a", "degree": 2, "created_at": 100.0}
    newer = {"id": "b", "degree": 2, "created_at": 200.0}
    keep, dup = er._pick_keeper(newer, older)
    assert keep is older and dup is newer


# ---------------------------------------------------------------------------
# resolve_entities
# ---------------------------------------------------------------------------


def test_resolve_merges_confirmed_duplicates(graph, monkeypatch) -> None:
    graph.add_relation("user", "uses", "VS Code")
    graph.add_relation("vscode", "has extension", "Vim plugin")

    monkeypatch.setattr(
        er, "_embed_names", _fake_embed({"VS Code": [1.0, 0.0, 0.0], "vscode": [1.0, 0.0, 0.0]})
    )
    monkeypatch.setattr(er, "_confirm_same_entity", lambda a, b, model: True)

    report = er.resolve_entities(threshold=0.9, max_merges=5)
    assert len(report["merges"]) == 1
    # Higher degree is irrelevant here (1 vs 1) — but both names resolve to one node.
    assert graph.resolve_node("VS Code") == graph.resolve_node("vscode")
    m = report["merges"][0]
    assert {m["kept"], m["merged"]} == {"VS Code", "vscode"}


def test_resolve_dry_run_reports_without_merging(graph, monkeypatch) -> None:
    graph.add_relation("user", "uses", "VS Code")
    graph.add_relation("user", "uses", "vscode")

    monkeypatch.setattr(
        er, "_embed_names", _fake_embed({"VS Code": [1.0, 0.0, 0.0], "vscode": [1.0, 0.0, 0.0]})
    )
    monkeypatch.setattr(er, "_confirm_same_entity", lambda a, b, model: True)

    report = er.resolve_entities(threshold=0.9, dry_run=True)
    assert report["dry_run"] is True
    assert len(report["merges"]) == 1
    # Graph untouched.
    assert graph.resolve_node("VS Code") != graph.resolve_node("vscode")


def test_resolve_respects_judge_rejection(graph, monkeypatch) -> None:
    graph.add_relation("user", "likes", "Celeste")  # the game
    graph.add_relation("Celestia", "runs on", "Ollama")  # the project

    monkeypatch.setattr(
        er,
        "_embed_names",
        _fake_embed({"Celeste": [1.0, 0.1, 0.0], "Celestia": [1.0, 0.0, 0.0]}),
    )
    monkeypatch.setattr(er, "_confirm_same_entity", lambda a, b, model: False)

    report = er.resolve_entities(threshold=0.9)
    assert report["candidates"] >= 1  # similar enough to be checked…
    assert report["merges"] == []  # …but the judge said no
    assert graph.resolve_node("Celeste") != graph.resolve_node("Celestia")


def test_resolve_skips_when_embedding_fails(graph, monkeypatch) -> None:
    graph.add_relation("user", "uses", "VS Code")
    graph.add_relation("user", "uses", "vscode")
    monkeypatch.setattr(er, "_embed_names", lambda names, model: None)

    report = er.resolve_entities()
    assert "skipped" in report
    assert report["merges"] == []


def test_resolve_caps_merges_per_run(graph, monkeypatch) -> None:
    pairs = [("VS Code", "vscode"), ("Hollow Knight", "hollowknight"), ("qwen 2.5", "qwen2.5")]
    vectors = {}
    for k, (a, b) in enumerate(pairs):
        graph.upsert_node(a)
        graph.upsert_node(b)
        v = [0.0, 0.0, 0.0]
        v[k] = 1.0
        vectors[a] = list(v)
        vectors[b] = list(v)

    monkeypatch.setattr(er, "_embed_names", _fake_embed(vectors))
    monkeypatch.setattr(er, "_confirm_same_entity", lambda a, b, model: True)

    report = er.resolve_entities(threshold=0.9, max_merges=2)
    assert len(report["merges"]) == 2  # capped below the 3 available


def test_resolve_empty_graph_is_noop(graph) -> None:
    report = er.resolve_entities()
    assert report == {"nodes": 0, "candidates": 0, "merges": [], "dry_run": False}
