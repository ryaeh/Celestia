"""Tests for the ui_prefs runtime override system in celestia_core.config."""
from __future__ import annotations

import json
import pytest


@pytest.fixture()
def prefs_path(tmp_path, monkeypatch):
    """Redirect UI_PREFS_PATH to a temp file so tests don't touch data/."""
    import celestia_core.config as cfg
    fake = tmp_path / "ui_prefs.json"
    monkeypatch.setattr(cfg, "_UI_PREFS_PATH", fake)
    return fake


def test_set_pref_writes_json(prefs_path):
    from celestia_core.config import set_pref
    result = set_pref("voice.stt.vad_filter", True)
    assert result == "ok"
    data = json.loads(prefs_path.read_text())
    assert data["voice.stt.vad_filter"] is True


def test_set_pref_rejects_unknown_key(prefs_path):
    from celestia_core.config import set_pref
    result = set_pref("some.random.key", "evil")
    assert result.startswith("not allowed")
    assert not prefs_path.exists() or "some.random.key" not in json.loads(prefs_path.read_text())


def test_get_returns_pref_over_config(prefs_path, monkeypatch):
    from celestia_core.config import set_pref, get
    set_pref("voice.stt.vad_filter", True)
    # get() should return the pref value, not whatever config.yaml says
    val = get("voice.stt.vad_filter")
    assert val is True


def test_get_falls_back_to_config_when_no_pref(prefs_path, monkeypatch):
    """When no pref is set, get() should still return the config.yaml value."""
    from celestia_core.config import get
    # vad_filter defaults to False in config.example.yaml
    val = get("voice.stt.vad_filter", False)
    assert val is False


def test_get_all_prefs_empty(prefs_path):
    from celestia_core.config import get_all_prefs
    prefs_path.unlink(missing_ok=True)
    assert get_all_prefs() == {}


def test_prefs_update_existing_key(prefs_path):
    from celestia_core.config import set_pref
    set_pref("voice.stt.model", "base.en")
    set_pref("voice.stt.model", "large-v3")
    data = json.loads(prefs_path.read_text())
    assert data["voice.stt.model"] == "large-v3"
