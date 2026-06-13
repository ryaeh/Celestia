"""Tests for the incognito / pause-learning toggle.

Covers the state-file roundtrip (celestia_core/incognito.py) and the single
consolidation choke point that incognito gates.
"""

import pytest

from celestia_core import incognito
from skills.memory.session_consolidate import should_run_consolidation


@pytest.fixture
def tmp_state(tmp_path, monkeypatch):
    """Redirect the incognito state + lock files into a tmp dir, mtime-cache reset."""
    state = tmp_path / "incognito_state.json"
    lock = tmp_path / ".incognito_state.lock"
    monkeypatch.setattr(incognito, "_state_path", lambda: state)
    monkeypatch.setattr(incognito, "_state_lock_path", lambda: lock)
    monkeypatch.setattr(incognito, "_state_cache", None, raising=False)
    return state


def test_defaults_off_when_no_state_file(tmp_state):
    assert incognito.is_on() is False


def test_set_and_read_roundtrip(tmp_state):
    assert incognito.set_on(True) is True
    assert incognito.is_on() is True
    assert incognito.set_on(False) is False
    assert incognito.is_on() is False


def test_toggle_flips_state(tmp_state):
    assert incognito.toggle() is True
    assert incognito.toggle() is False


def test_status_label(tmp_state):
    incognito.set_on(True)
    assert "paused" in incognito.status_label()
    incognito.set_on(False)
    assert incognito.status_label() == "learning on"


def _make_config(**overrides):
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
    return [{"role": r, "content": "x"} for r in roles]


def test_consolidation_blocked_when_incognito(monkeypatch):
    """The gate short-circuits consolidation even when everything else says go."""
    monkeypatch.setattr(
        "skills.memory.session_consolidate.get", _make_config()
    )
    monkeypatch.setattr("celestia_core.incognito.is_on", lambda: True)
    msgs = _msgs("system", "user", "assistant", "user", "assistant")
    assert should_run_consolidation(msgs, start_index=0) is False


def test_consolidation_runs_when_not_incognito(monkeypatch):
    monkeypatch.setattr(
        "skills.memory.session_consolidate.get", _make_config()
    )
    monkeypatch.setattr("celestia_core.incognito.is_on", lambda: False)
    msgs = _msgs("system", "user", "assistant", "user", "assistant")
    assert should_run_consolidation(msgs, start_index=0) is True
