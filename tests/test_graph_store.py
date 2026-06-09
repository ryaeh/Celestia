"""Tests for skills/memory/graph_store.py — the temporal knowledge graph (Feature 10).

Pure stdlib sqlite3 — no Ollama / mem0 / Chroma. The DB path is redirected to a
fresh tmp file per test and the cached connection is reset around each one.
"""

from __future__ import annotations

import pytest

import skills.memory.graph_store as gs


@pytest.fixture()
def graph(tmp_path, monkeypatch):
    db = tmp_path / "graph.db"
    monkeypatch.setattr(gs, "_db_path", lambda: db)
    gs.reset_connection()
    yield gs
    gs.reset_connection()


# ---------------------------------------------------------------------------
# Nodes & entity resolution
# ---------------------------------------------------------------------------


def test_upsert_node_creates_and_returns_id(graph) -> None:
    nid = graph.upsert_node("Celestia", "project")
    assert nid
    node = graph.get_node(nid)
    assert node["canonical_name"] == "Celestia"
    assert node["type"] == "project"


def test_upsert_node_is_idempotent_by_name(graph) -> None:
    a = graph.upsert_node("Celestia")
    b = graph.upsert_node("celestia")  # case-insensitive match
    assert a == b


def test_resolve_node_via_alias(graph) -> None:
    nid = graph.upsert_node("Ollama")
    graph.add_alias(nid, "the model runner")
    assert graph.resolve_node("the model runner") == nid
    assert graph.resolve_node("OLLAMA") == nid


def test_resolve_unknown_returns_none(graph) -> None:
    assert graph.resolve_node("nonexistent") is None


def test_upsert_fills_empty_type_later(graph) -> None:
    nid = graph.upsert_node("Doruk")
    assert graph.get_node(nid)["type"] is None
    graph.upsert_node("Doruk", "person")
    assert graph.get_node(nid)["type"] == "person"


def test_upsert_empty_name_raises(graph) -> None:
    with pytest.raises(ValueError):
        graph.upsert_node("   ")


# ---------------------------------------------------------------------------
# add_relation — multi-valued / additive
# ---------------------------------------------------------------------------


def test_add_relation_creates_nodes_and_edge(graph) -> None:
    graph.add_relation("Doruk", "works_on", "Celestia")
    edges = graph.walk("Doruk", hops=1)
    assert len(edges) == 1
    e = edges[0]
    assert e["subject"] == "Doruk"
    assert e["predicate"] == "works_on"
    assert e["object"] == "Celestia"
    assert e["valid_until"] is None


def test_add_relation_is_idempotent(graph) -> None:
    graph.add_relation("Celestia", "uses", "Ollama")
    graph.add_relation("Celestia", "uses", "Ollama")
    assert graph.stats()["current_edges"] == 1


def test_add_relation_keeps_multiple_objects(graph) -> None:
    graph.add_relation("Celestia", "uses", "Ollama")
    graph.add_relation("Celestia", "uses", "Chroma")
    objs = {e["object"] for e in graph.walk("Celestia", hops=1)}
    assert objs == {"Ollama", "Chroma"}


def test_predicate_is_normalised(graph) -> None:
    graph.add_relation("Doruk", "Works On", "Celestia")
    assert graph.walk("Doruk", hops=1)[0]["predicate"] == "works_on"


# ---------------------------------------------------------------------------
# set_relation — single-valued / versioned supersede
# ---------------------------------------------------------------------------


def test_set_relation_supersedes_old_object(graph) -> None:
    graph.set_relation("Ollama", "runs", "Llama 3")
    graph.set_relation("Ollama", "runs", "Qwen")
    current = [e for e in graph.walk("Ollama", hops=1) if e["valid_until"] is None]
    assert len(current) == 1
    assert current[0]["object"] == "Qwen"


def test_supersede_retains_history(graph) -> None:
    graph.set_relation("Ollama", "runs", "Llama 3")
    graph.set_relation("Ollama", "runs", "Qwen")
    hist = graph.history("Ollama", "runs")
    assert len(hist) == 2  # nothing deleted
    ended = [e for e in hist if e["valid_until"] is not None]
    assert len(ended) == 1
    assert ended[0]["object"] == "Llama 3"


def test_set_relation_reassert_is_idempotent(graph) -> None:
    graph.set_relation("Ollama", "runs", "Qwen")
    graph.set_relation("Ollama", "runs", "Qwen")
    assert graph.stats()["edges"] == 1


def test_end_relation_stamps_valid_until(graph) -> None:
    graph.add_relation("Celestia", "uses", "Ollama")
    assert graph.end_relation("Celestia", "uses", "Ollama") is True
    assert graph.stats()["current_edges"] == 0
    assert graph.stats()["edges"] == 1  # retained


def test_end_relation_unknown_returns_false(graph) -> None:
    assert graph.end_relation("Nobody", "likes", "Nothing") is False


# ---------------------------------------------------------------------------
# Temporal queries (as-of time travel)
# ---------------------------------------------------------------------------


def test_walk_as_of_past_sees_old_truth(graph) -> None:
    graph.set_relation("Ollama", "runs", "Llama 3", valid_from=100.0)
    graph.set_relation("Ollama", "runs", "Qwen", valid_from=200.0)
    # At t=150 the model was still Llama 3.
    past = graph.walk("Ollama", hops=1, at=150.0)
    assert [e["object"] for e in past] == ["Llama 3"]
    # Currently it's Qwen.
    now = graph.walk("Ollama", hops=1)
    assert [e["object"] for e in now] == ["Qwen"]


def test_walk_as_of_before_any_edge_is_empty(graph) -> None:
    graph.set_relation("Ollama", "runs", "Llama 3", valid_from=100.0)
    assert graph.walk("Ollama", hops=1, at=50.0) == []


# ---------------------------------------------------------------------------
# Graph-walk (multi-hop)
# ---------------------------------------------------------------------------


def test_walk_two_hops_reaches_connected_entity(graph) -> None:
    graph.add_relation("Doruk", "works_on", "Celestia")
    graph.add_relation("Celestia", "uses", "Ollama")
    reached = {e["object"] for e in graph.walk("Doruk", hops=2)}
    assert {"Celestia", "Ollama"} <= reached


def test_walk_respects_hop_limit(graph) -> None:
    graph.add_relation("Doruk", "works_on", "Celestia")
    graph.add_relation("Celestia", "uses", "Ollama")
    one_hop = {e["object"] for e in graph.walk("Doruk", hops=1)}
    assert one_hop == {"Celestia"}  # Ollama is 2 hops away


def test_walk_unknown_entity_is_empty(graph) -> None:
    assert graph.walk("Ghost", hops=2) == []


def test_recall_returns_readable_lines(graph) -> None:
    graph.add_relation("Doruk", "works_on", "Celestia")
    lines = graph.recall("Doruk", hops=1)
    assert lines == ["Doruk works on Celestia"]


def test_recall_marks_past_relations(graph) -> None:
    graph.set_relation("Ollama", "runs", "Llama 3", valid_from=100.0)
    graph.set_relation("Ollama", "runs", "Qwen", valid_from=200.0)
    # history walk at the old time should mark nothing as past (it was current then)
    lines = graph.recall("Ollama", hops=1)
    assert lines == ["Ollama runs Qwen"]


# ---------------------------------------------------------------------------
# Stats / persistence
# ---------------------------------------------------------------------------


def test_stats_counts(graph) -> None:
    graph.add_relation("Doruk", "works_on", "Celestia")
    graph.set_relation("Ollama", "runs", "Llama 3")
    graph.set_relation("Ollama", "runs", "Qwen")
    s = graph.stats()
    assert s["nodes"] == 5  # Doruk, Celestia, Ollama, Llama 3, Qwen
    assert s["current_edges"] == 2  # works_on + runs→Qwen (runs→Llama 3 ended)
    assert s["edges"] == 3


def test_persists_across_reconnect(graph, tmp_path, monkeypatch) -> None:
    graph.add_relation("Doruk", "works_on", "Celestia")
    graph.reset_connection()  # drop cached handle; reopen same file
    reached = {e["object"] for e in graph.walk("Doruk", hops=1)}
    assert reached == {"Celestia"}


# ---------------------------------------------------------------------------
# resolve_mentions / recall_from_text — hot-path entity recall (A3)
# ---------------------------------------------------------------------------


def test_resolve_mentions_finds_single_word(graph) -> None:
    graph.add_relation("Doruk", "works_on", "Celestia")
    ids = graph.resolve_mentions("what does Celestia depend on?")
    assert graph.resolve_node("Celestia") in ids


def test_resolve_mentions_finds_multiword_entity(graph) -> None:
    graph.set_relation("Ollama", "runs", "Llama 3")
    ids = graph.resolve_mentions("are we still on Llama 3 or did we switch?")
    assert graph.resolve_node("Llama 3") in ids


def test_resolve_mentions_unknown_is_empty(graph) -> None:
    graph.add_relation("Doruk", "works_on", "Celestia")
    assert graph.resolve_mentions("tell me about the weather") == []


def test_resolve_mentions_empty_text(graph) -> None:
    assert graph.resolve_mentions("") == []


def test_recall_from_text_returns_connected_facts(graph) -> None:
    graph.add_relation("Doruk", "works_on", "Celestia")
    graph.add_relation("Celestia", "uses", "Ollama")
    lines = graph.recall_from_text("what is Celestia?", hops=2)
    assert "Celestia uses Ollama" in lines


def test_recall_from_text_no_mention_empty(graph) -> None:
    graph.add_relation("Doruk", "works_on", "Celestia")
    assert graph.recall_from_text("unrelated question") == []


def test_recall_surfaces_only_current_truth(graph) -> None:
    graph.set_relation("Ollama", "runs", "Llama 3", valid_from=100.0)
    graph.set_relation("Ollama", "runs", "Qwen", valid_from=200.0)
    # Live recall injects only the current truth; the superseded fact stays in
    # history (queryable via history()/time-travel) but never clutters context.
    lines = graph.recall_from_text("what does Ollama run?", hops=1, max_lines=5)
    assert lines == ["Ollama runs Qwen"]


def test_recall_time_travel_marks_past(graph) -> None:
    graph.set_relation("Ollama", "runs", "Llama 3", valid_from=100.0)
    graph.set_relation("Ollama", "runs", "Qwen", valid_from=200.0)
    # As-of a past time, the then-current edge surfaces and is flagged past.
    lines = graph.recall_from_text("what did Ollama run?", hops=1, at=150.0)
    assert lines == ["Ollama runs Llama 3 (past)"]


def test_recall_respects_max_lines(graph) -> None:
    for tool in ["Ollama", "Chroma", "Whisper", "Orpheus", "Tauri"]:
        graph.add_relation("Celestia", "uses", tool)
    lines = graph.recall_from_text("Celestia", hops=1, max_lines=3)
    assert len(lines) == 3
