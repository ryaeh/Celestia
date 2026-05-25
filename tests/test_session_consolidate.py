"""Tests for skills/memory/session_consolidate.py — should_run_consolidation().

All tests control the config via monkeypatch so we don't need config.yaml at
runtime and can flip individual settings without side effects.
"""

import pytest

from skills.memory.session_consolidate import should_run_consolidation


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config(**overrides):
    """Return a simple get() stub that returns True for memory flags by default."""
    defaults = {
        "memory.enabled": True,
        "memory.session_consolidate": True,
        "memory.session_consolidate_mode": "auto",
        "memory.session_consolidate_on_end": True,
        "memory.session_consolidate_min_user_turns": 2,
    }
    merged = {**defaults, **overrides}
    return lambda key, default=None: merged.get(key, default)


def _msgs(*roles):
    """Quickly build a message list from a sequence of role names."""
    return [{"role": r, "content": "x"} for r in roles]


# ---------------------------------------------------------------------------
# Feature disabled
# ---------------------------------------------------------------------------

def test_returns_false_when_memory_disabled(monkeypatch):
    monkeypatch.setattr(
        "skills.memory.session_consolidate.get",
        _make_config(**{"memory.enabled": False}),
    )
    msgs = _msgs("system", "user", "assistant", "user", "assistant")
    assert should_run_consolidation(msgs, start_index=0) is False


def test_returns_false_when_consolidate_disabled(monkeypatch):
    monkeypatch.setattr(
        "skills.memory.session_consolidate.get",
        _make_config(**{"memory.session_consolidate": False}),
    )
    msgs = _msgs("system", "user", "assistant", "user", "assistant")
    assert should_run_consolidation(msgs, start_index=0) is False


def test_returns_false_when_mode_off(monkeypatch):
    monkeypatch.setattr(
        "skills.memory.session_consolidate.get",
        _make_config(**{"memory.session_consolidate_mode": "off"}),
    )
    msgs = _msgs("system", "user", "assistant", "user", "assistant")
    assert should_run_consolidation(msgs, start_index=0) is False


# ---------------------------------------------------------------------------
# Auto mode — threshold checks
# ---------------------------------------------------------------------------

def test_returns_false_when_not_enough_user_turns(monkeypatch):
    monkeypatch.setattr(
        "skills.memory.session_consolidate.get",
        _make_config(**{"memory.session_consolidate_min_user_turns": 3}),
    )
    # Only 2 user turns — below the min of 3
    msgs = _msgs("system", "user", "assistant", "user", "assistant")
    assert should_run_consolidation(msgs, start_index=0) is False


def test_returns_true_when_threshold_met(monkeypatch):
    monkeypatch.setattr(
        "skills.memory.session_consolidate.get",
        _make_config(**{"memory.session_consolidate_min_user_turns": 2}),
    )
    msgs = _msgs("system", "user", "assistant", "user", "assistant")
    assert should_run_consolidation(msgs, start_index=0) is True


def test_start_index_offsets_count(monkeypatch):
    """start_index must exclude earlier turns from the count."""
    monkeypatch.setattr(
        "skills.memory.session_consolidate.get",
        _make_config(**{"memory.session_consolidate_min_user_turns": 2}),
    )
    # 4 user turns total, but start_index=4 means only the last 2 are in scope
    msgs = _msgs("user", "assistant", "user", "assistant", "user", "assistant", "user", "assistant")
    # from start_index=4: user, assistant, user, assistant → 2 user turns → True
    assert should_run_consolidation(msgs, start_index=4) is True
    # from start_index=6: user, assistant → 1 user turn → False
    assert should_run_consolidation(msgs, start_index=6) is False


# ---------------------------------------------------------------------------
# end=True path
# ---------------------------------------------------------------------------

def test_end_returns_true_when_on_end_enabled(monkeypatch):
    monkeypatch.setattr(
        "skills.memory.session_consolidate.get",
        _make_config(**{"memory.session_consolidate_on_end": True}),
    )
    # Even with 0 turns, end=True should trigger if on_end is enabled
    assert should_run_consolidation([], start_index=0, end=True) is True


def test_end_returns_false_when_on_end_disabled(monkeypatch):
    monkeypatch.setattr(
        "skills.memory.session_consolidate.get",
        _make_config(**{"memory.session_consolidate_on_end": False}),
    )
    msgs = _msgs("user", "assistant", "user", "assistant")
    assert should_run_consolidation(msgs, start_index=0, end=True) is False
