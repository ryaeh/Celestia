"""Tests for skills/memory/decay.py — decay candidate logic + sweep behaviour.

decay_candidates is pure. sweep_decay's config + store access are stubbed so no
real Chroma/config is touched and nothing on disk is deleted.
"""

from __future__ import annotations

import time

import pytest

import skills.memory.decay as decay
import skills.memory.store as store


NOW = 1_000_000_000.0
DAY = 86400.0
PROTECT = {"instruction"}


def _entry(mid, kind="summary", importance=0.3, age_days=60.0):
    return {
        "id": mid,
        "kind": kind,
        "importance": importance,
        "created_at": NOW - age_days * DAY,
    }


# ---------------------------------------------------------------------------
# decay_candidates — pure logic
# ---------------------------------------------------------------------------


def _candidates(entries, stats=None):
    return decay.decay_candidates(
        entries,
        stats or {},
        now=NOW,
        ttl_days=30.0,
        min_importance=0.5,
        protect_kinds=PROTECT,
    )


def test_decays_old_low_importance_unrecalled() -> None:
    assert _candidates([_entry("a")]) == ["a"]


def test_keeps_protected_kind() -> None:
    assert _candidates([_entry("a", kind="instruction", importance=0.1)]) == []


def test_keeps_high_importance() -> None:
    assert _candidates([_entry("a", importance=0.8)]) == []


def test_keeps_ever_recalled() -> None:
    stats = {"a": {"count": 1, "last": NOW - 50 * DAY}}
    assert _candidates([_entry("a")], stats) == []


def test_keeps_pinned_entry() -> None:
    # A user-pinned keeper never decays, even when otherwise eligible.
    assert _candidates([_entry("a")], {"a": {"keep": True}}) == []


def test_keeps_too_young() -> None:
    assert _candidates([_entry("a", age_days=5.0)]) == []


def test_keeps_unknown_age() -> None:
    e = _entry("a")
    e["created_at"] = 0.0
    assert _candidates([e]) == []


def test_mixed_batch_only_eligible() -> None:
    entries = [
        _entry("old_summary"),                       # decays
        _entry("instr", kind="instruction", importance=0.1),  # protected
        _entry("fact", kind="fact", importance=0.7),  # important
        _entry("young", age_days=2.0),                # too young
    ]
    assert _candidates(entries) == ["old_summary"]


# ---------------------------------------------------------------------------
# sweep_decay — orchestration (config + store stubbed)
# ---------------------------------------------------------------------------


@pytest.fixture()
def sweep_env(tmp_path, monkeypatch):
    """Enable decay, stub the store, isolate the throttle marker + stats."""
    cfg = {
        "memory.decay.enabled": True,
        "memory.decay.ttl_days": 30,
        "memory.decay.min_importance": 0.5,
        "memory.decay.protect_kinds": ["instruction"],
        "memory.decay.min_interval_hours": 24,
        "memory.decay.scan_limit": 500,
        "app.user_id": "test_user",
    }
    monkeypatch.setattr(decay, "get", lambda key, default=None: cfg.get(key, default))
    monkeypatch.setattr(decay, "load_stats", lambda: {})
    monkeypatch.setattr(decay, "_last_sweep_path", lambda: tmp_path / "decay_last.txt")

    deleted: list[str] = []
    monkeypatch.setattr(decay, "drop_stats", lambda ids: deleted.extend(("drop", *ids)))
    monkeypatch.setattr(store, "delete_by_id", lambda mid: deleted.append(mid) or "Deleted.")
    return {"cfg": cfg, "deleted": deleted, "monkeypatch": monkeypatch}


def test_sweep_disabled_is_noop(sweep_env) -> None:
    sweep_env["cfg"]["memory.decay.enabled"] = False
    result = decay.sweep_decay(force=True)
    assert result == {"enabled": False, "deleted": 0, "ids": []}


def test_sweep_deletes_candidates(sweep_env, monkeypatch) -> None:
    entries = [_entry("old"), _entry("instr", kind="instruction", importance=0.1)]
    monkeypatch.setattr(store, "get_all_entries", lambda uid, limit=500: entries)
    result = decay.sweep_decay(force=True)
    assert result["deleted"] == 1
    assert result["ids"] == ["old"]
    assert "old" in sweep_env["deleted"]
    assert "instr" not in sweep_env["deleted"]


def test_sweep_dry_run_deletes_nothing(sweep_env, monkeypatch) -> None:
    entries = [_entry("old")]
    monkeypatch.setattr(store, "get_all_entries", lambda uid, limit=500: entries)
    result = decay.sweep_decay(dry_run=True)
    assert result["dry_run"] is True
    assert result["ids"] == ["old"]
    assert result["deleted"] == 0
    assert sweep_env["deleted"] == []  # delete_by_id never called


def test_sweep_throttled_when_recent(sweep_env, monkeypatch) -> None:
    monkeypatch.setattr(decay, "should_sweep_now", lambda: False)
    called = {"hit": False}

    def _boom(*a, **k):
        called["hit"] = True
        return []

    monkeypatch.setattr(store, "get_all_entries", _boom)
    result = decay.sweep_decay()  # no force, no dry_run
    assert result.get("throttled") is True
    assert called["hit"] is False  # never scanned the store


# ---------------------------------------------------------------------------
# should_sweep_now
# ---------------------------------------------------------------------------


def test_should_sweep_false_when_disabled(monkeypatch) -> None:
    monkeypatch.setattr(decay, "get", lambda key, default=None: False if "enabled" in key else default)
    assert decay.should_sweep_now() is False


def test_should_sweep_true_when_enabled_and_no_marker(tmp_path, monkeypatch) -> None:
    cfg = {"memory.decay.enabled": True, "memory.decay.min_interval_hours": 24}
    monkeypatch.setattr(decay, "get", lambda key, default=None: cfg.get(key, default))
    monkeypatch.setattr(decay, "_last_sweep_path", lambda: tmp_path / "nope.txt")
    assert decay.should_sweep_now() is True
