"""Tests for skills/memory/ranking.py — importance, access stats, blended score.

The recall-stat sidecar is redirected to tmp_path so no real data/ file is
touched; scoring functions are pure and need no fixtures.
"""

from __future__ import annotations

import pytest

import skills.memory.ranking as ranking


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def stats_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(ranking, "_stats_path", lambda: tmp_path / "recall_stats.json")
    monkeypatch.setattr(ranking, "_lock_path", lambda: tmp_path / "recall_stats.lock")
    return tmp_path


_WEIGHTS = {"similarity": 0.5, "importance": 0.25, "recall": 0.15, "recency": 0.10}


# ---------------------------------------------------------------------------
# default_importance
# ---------------------------------------------------------------------------


def test_importance_order_by_kind() -> None:
    assert ranking.default_importance("instruction") == 1.0
    assert (
        ranking.default_importance("instruction")
        > ranking.default_importance("fact")
        > ranking.default_importance("task")
        > ranking.default_importance("summary")
    )


def test_importance_unknown_kind_is_neutral() -> None:
    # normalize_kind maps unknown → "fact", so an unknown kind scores as a fact.
    assert ranking.default_importance("banana") == ranking.default_importance("fact")


# ---------------------------------------------------------------------------
# rank_score — each signal moves the score the right way
# ---------------------------------------------------------------------------


def _score(**over):
    base = dict(
        idx=0,
        total=4,
        importance=0.5,
        recall_count=0,
        last_recalled=0.0,
        created_at=0.0,
        now=1_000_000.0,
        weights=_WEIGHTS,
    )
    base.update(over)
    return ranking.rank_score(**base)


def test_higher_importance_scores_higher() -> None:
    assert _score(importance=0.9) > _score(importance=0.2)


def test_more_recall_scores_higher() -> None:
    assert _score(recall_count=5) > _score(recall_count=0)


def test_fresher_scores_higher() -> None:
    now = 1_000_000.0
    fresh = _score(created_at=now, now=now)
    stale = _score(created_at=now - 90 * 86400, now=now)
    assert fresh > stale


def test_better_similarity_position_scores_higher() -> None:
    assert _score(idx=0, total=4) > _score(idx=3, total=4)


# ---------------------------------------------------------------------------
# rank_order — reorders similarity-ranked entries
# ---------------------------------------------------------------------------


def test_rank_order_promotes_important_recalled_entry(stats_tmp) -> None:
    now = 1_000_000.0
    # Entry B sits second by similarity but is high-importance and freshly made;
    # it should overtake the low-importance top-similarity entry A.
    entries = [
        {"id": "A", "text": "one-off", "kind": "summary", "importance": 0.2, "created_at": 0.0},
        {"id": "B", "text": "keeper", "kind": "fact", "importance": 0.95, "created_at": now},
    ]
    ranking.bump_recall(["B", "B", "B"], now=now)
    ordered = ranking.rank_order(entries, now=now)
    assert ordered[0]["id"] == "B"


def test_rank_order_stable_when_signals_equal(stats_tmp) -> None:
    entries = [
        {"id": "A", "kind": "fact", "importance": 0.7, "created_at": 0.0},
        {"id": "B", "kind": "fact", "importance": 0.7, "created_at": 0.0},
    ]
    ordered = ranking.rank_order(entries)
    # Equal signals → original similarity order preserved.
    assert [e["id"] for e in ordered] == ["A", "B"]


def test_rank_order_noop_for_single_entry(stats_tmp) -> None:
    entries = [{"id": "A", "kind": "fact", "importance": 0.7, "created_at": 0.0}]
    assert ranking.rank_order(entries) is entries


# ---------------------------------------------------------------------------
# Access-stat sidecar
# ---------------------------------------------------------------------------


def test_bump_recall_increments_and_timestamps(stats_tmp) -> None:
    ranking.bump_recall(["m1"], now=123.0)
    stats = ranking.load_stats()
    count, last = ranking.recall_for(stats, "m1")
    assert count == 1
    assert last == 123.0


def test_bump_recall_accumulates(stats_tmp) -> None:
    ranking.bump_recall(["m1"], now=1.0)
    ranking.bump_recall(["m1"], now=2.0)
    count, last = ranking.recall_for(ranking.load_stats(), "m1")
    assert count == 2
    assert last == 2.0


def test_recall_for_missing_is_zero(stats_tmp) -> None:
    assert ranking.recall_for({}, "nope") == (0, 0.0)


def test_bump_recall_ignores_empty_ids(stats_tmp) -> None:
    ranking.bump_recall(["", None])  # type: ignore[list-item]
    assert ranking.load_stats() == {}


def test_prune_stats_drops_unknown_ids(stats_tmp) -> None:
    ranking.bump_recall(["keep", "drop"], now=1.0)
    ranking.prune_stats({"keep"})
    stats = ranking.load_stats()
    assert "keep" in stats
    assert "drop" not in stats
