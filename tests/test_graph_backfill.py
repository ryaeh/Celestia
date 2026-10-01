"""T15 step 4 — linking memories saved before the writer to the knowledge graph."""

from __future__ import annotations

from typing import Any

import pytest

import skills.memory.graph_backfill as gb
import skills.memory.graph_store as gs
import skills.memory.links as links

CONFIG: dict[str, Any] = {}

ENTRIES = [
    {"id": "m1", "kind": "fact", "text": "The user's sister is Ana."},
    {"id": "m2", "kind": "instruction", "text": "Always answer briefly."},
    {"id": "m3", "kind": "task", "text": "Buy milk."},                      # not a graph kind
    {"id": "m4", "kind": "fact", "text": "Held for review.", "quarantined": True},
    {"id": "m5", "kind": "fact", "text": "Already linked."},
]


@pytest.fixture()
def env(tmp_path, monkeypatch):
    CONFIG.clear()
    monkeypatch.setattr(gb, "get", lambda key, default=None: CONFIG.get(key, default))
    monkeypatch.setattr(gb, "_state_path", lambda: tmp_path / "graph_backfill.json")
    monkeypatch.setattr(links, "_dir", lambda: tmp_path)
    monkeypatch.setattr("skills.memory.store.get_all_entries", lambda uid, limit=100: list(ENTRIES))
    monkeypatch.setattr("celestia_core.incognito.is_on", lambda: False)
    links.set_links("m5", ["e0"])
    calls: list[str] = []

    def fake_extract(text: str) -> list[dict[str, Any]]:
        calls.append(text)
        if "sister" in text:
            return [{"subject": "user", "predicate": "sister", "object": "Ana"}]
        return []

    monkeypatch.setattr(gb, "_extract", fake_extract)
    return calls


def test_pending_is_unlinked_live_graph_kinds(env) -> None:
    assert [e["id"] for e in gb.pending("u")] == ["m1", "m2"]


def test_step_links_edges_and_never_repeats(env) -> None:
    lines = gb.backfill_step("u")
    assert len(lines) == 2 and env == [ENTRIES[0]["text"], ENTRIES[1]["text"]]
    edge_ids = links.edges_for("m1")
    assert len(edge_ids) == 1
    edge = gs.get_edges(edge_ids)[0]
    assert edge["source"] == "memory:m1"
    # m2 yielded nothing but is marked done all the same.
    assert gb.pending("u") == [] and gb.backfill_step("u") == []
    assert len(env) == 2


def test_batch_limits_the_step(env) -> None:
    assert len(gb.backfill_step("u", batch=1)) == 1
    assert [e["id"] for e in gb.pending("u")] == ["m2"]


def test_model_down_leaves_the_rest_pending(env, monkeypatch) -> None:
    def boom(text):
        raise RuntimeError("ollama down")

    monkeypatch.setattr(gb, "_extract", boom)
    lines = gb.backfill_step("u")
    assert lines and "stopped" in lines[0]
    assert [e["id"] for e in gb.pending("u")] == ["m1", "m2"]


def test_off_switches(env, monkeypatch) -> None:
    CONFIG["memory.graph.backfill"] = False
    assert gb.backfill_step("u") == []
    CONFIG.clear()
    CONFIG["memory.graph.enabled"] = False
    assert gb.backfill_step("u") == []
    CONFIG.clear()
    monkeypatch.setattr("celestia_core.incognito.is_on", lambda: True)
    assert gb.backfill_step("u") == [] and env == []


def test_skips_while_the_gpu_is_busy(env) -> None:
    import threading

    from celestia_core.gpu import gpu_task

    held, release = threading.Event(), threading.Event()

    def hold() -> None:  # the lock is re-entrant, so hold it from another thread
        with gpu_task("vision"):
            held.set()
            release.wait(5)

    t = threading.Thread(target=hold)
    t.start()
    held.wait(5)
    try:
        assert gb.backfill_step("u") == []
    finally:
        release.set()
        t.join()
    assert len(gb.pending("u")) == 2
