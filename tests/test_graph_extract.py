"""Tests for skills/memory/graph_extract.py — relation extraction into the graph (A2).

The LLM call (ollama.chat) is replaced with a canned-JSON stub; the graph store
is redirected to a fresh tmp SQLite db. No Ollama / GPU needed.
"""

from __future__ import annotations

import json

import pytest

import skills.memory.graph_extract as ge
import skills.memory.graph_store as gs


@pytest.fixture()
def graph_db(tmp_path, monkeypatch):
    db = tmp_path / "graph.db"
    monkeypatch.setattr(gs, "_db_path", lambda: db)
    gs.reset_connection()
    # Silence the activity feed (writes to disk + SSE) during extraction.
    monkeypatch.setattr(ge, "append_event", lambda **kw: None)
    yield gs
    gs.reset_connection()


def _stub_ollama(monkeypatch, payload) -> None:
    content = payload if isinstance(payload, str) else json.dumps(payload)

    def _chat(*_a, **_k):
        return {"message": {"content": content}}

    monkeypatch.setattr(ge.ollama, "chat", _chat)
    monkeypatch.setattr(ge, "get", lambda key, default=None: default)


# ---------------------------------------------------------------------------
# _parse_relations — pure parser
# ---------------------------------------------------------------------------


def test_parse_valid_relations() -> None:
    raw = json.dumps(
        {"relations": [{"subject": "Doruk", "predicate": "works on", "object": "Celestia"}]}
    )
    rels = ge._parse_relations(raw)
    assert len(rels) == 1
    assert rels[0]["subject"] == "Doruk"
    assert rels[0]["object"] == "Celestia"
    assert rels[0]["single_valued"] is False


def test_parse_ignores_incomplete_triples() -> None:
    raw = json.dumps(
        {"relations": [{"subject": "X", "predicate": "uses"}, {"subject": "A", "predicate": "uses", "object": "B"}]}
    )
    rels = ge._parse_relations(raw)
    assert [r["object"] for r in rels] == ["B"]


def test_parse_skips_self_referential() -> None:
    raw = json.dumps({"relations": [{"subject": "X", "predicate": "is", "object": "x"}]})
    assert ge._parse_relations(raw) == []


def test_parse_skips_overlong_terms() -> None:
    raw = json.dumps({"relations": [{"subject": "X", "predicate": "is", "object": "y" * 200}]})
    assert ge._parse_relations(raw) == []


def test_parse_caps_relation_count() -> None:
    rels = [{"subject": f"s{i}", "predicate": "p", "object": f"o{i}"} for i in range(50)]
    parsed = ge._parse_relations(json.dumps({"relations": rels}))
    assert len(parsed) == ge._MAX_RELATIONS


def test_parse_bad_json_returns_empty() -> None:
    assert ge._parse_relations("not json at all") == []
    assert ge._parse_relations("") == []


def test_parse_extracts_json_embedded_in_prose() -> None:
    raw = 'Sure! Here you go:\n{"relations":[{"subject":"A","predicate":"uses","object":"B"}]} cheers'
    assert len(ge._parse_relations(raw)) == 1


# ---------------------------------------------------------------------------
# store_relations — writes to graph
# ---------------------------------------------------------------------------


def test_store_add_vs_set(graph_db) -> None:
    rels = [
        {"subject": "Celestia", "predicate": "uses", "object": "Ollama", "single_valued": False, "subject_type": None, "object_type": None},
        {"subject": "Ollama", "predicate": "runs", "object": "Qwen", "single_valued": True, "subject_type": None, "object_type": None},
    ]
    n = ge.store_relations(rels, source="chat")
    assert n == 2
    assert graph_db.stats()["current_edges"] == 2


def test_store_single_valued_supersedes(graph_db) -> None:
    ge.store_relations(
        [{"subject": "Ollama", "predicate": "runs", "object": "Llama 3", "single_valued": True, "subject_type": None, "object_type": None}],
    )
    ge.store_relations(
        [{"subject": "Ollama", "predicate": "runs", "object": "Qwen", "single_valued": True, "subject_type": None, "object_type": None}],
    )
    current = [e for e in graph_db.walk("Ollama", hops=1) if e["valid_until"] is None]
    assert [e["object"] for e in current] == ["Qwen"]
    assert graph_db.stats()["edges"] == 2  # old retained


# ---------------------------------------------------------------------------
# extract_and_store — end to end (mocked LLM)
# ---------------------------------------------------------------------------


def test_extract_and_store_writes_graph(graph_db, monkeypatch) -> None:
    _stub_ollama(
        monkeypatch,
        {"relations": [{"subject": "Doruk", "predicate": "works on", "object": "Celestia"}]},
    )
    excerpt = "User: my main project is Celestia and I work on it daily.\nAssistant: nice."
    lines = ge.extract_and_store(excerpt, user_id="u1")
    assert any("Doruk" in ln for ln in lines)
    reached = {e["object"] for e in graph_db.walk("Doruk", hops=1)}
    assert reached == {"Celestia"}


def test_extract_short_excerpt_noop(graph_db, monkeypatch) -> None:
    _stub_ollama(monkeypatch, {"relations": []})
    assert ge.extract_and_store("hi", user_id="u1") == []
    assert graph_db.stats()["nodes"] == 0


def test_extract_llm_failure_is_caught(graph_db, monkeypatch) -> None:
    def _boom(*_a, **_k):
        raise RuntimeError("ollama down")

    monkeypatch.setattr(ge.ollama, "chat", _boom)
    monkeypatch.setattr(ge, "get", lambda key, default=None: default)
    out = ge.extract_and_store("User: a long enough excerpt about projects and tools here.", user_id="u1")
    assert out and "skipped" in out[0]
    assert graph_db.stats()["nodes"] == 0


def test_extract_no_relations_no_writes(graph_db, monkeypatch) -> None:
    _stub_ollama(monkeypatch, {"relations": []})
    out = ge.extract_and_store("User: just chatting about the weather today, nothing to store.", user_id="u1")
    assert out == []
    assert graph_db.stats()["edges"] == 0


def test_extract_defers_when_gpu_busy(graph_db, monkeypatch) -> None:
    import threading
    import celestia_core.gpu as gpu

    _stub_ollama(monkeypatch, {"relations": [{"subject": "A", "predicate": "uses", "object": "B"}]})
    held = threading.Event()
    release = threading.Event()

    def _holder():
        with gpu.gpu_task("vision"):
            held.set()
            release.wait(timeout=5)

    t = threading.Thread(target=_holder, daemon=True)
    t.start()
    assert held.wait(timeout=5)

    # Another thread holds the GPU → the background extraction must skip.
    out = ge.extract_and_store("User: a long enough excerpt about projects and tools here.", user_id="u1")
    release.set()
    t.join(timeout=5)

    assert out == ["graph extract deferred: gpu busy"]
    assert graph_db.stats()["edges"] == 0
