"""Tests for the companion overlay bubble's server side (celestia_core/shell_overlay.py)
and the live-state keys it relies on (busy, overlay_seq)."""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

import celestia_core.config as _cfg
from celestia_core import shell_overlay, shell_server, stream_cancel


@pytest.fixture(autouse=True)
def _clean():
    yield
    stream_cancel.end("s-overlay")


def test_request_toggle_bumps_sequence() -> None:
    start = shell_overlay.toggle_seq()
    assert shell_overlay.request_toggle() == start + 1
    assert shell_overlay.toggle_seq() == start + 1


def test_any_active_tracks_streams() -> None:
    assert not stream_cancel.any_active()
    stream_cancel.begin("s-overlay")
    assert stream_cancel.any_active()
    stream_cancel.end("s-overlay")
    assert not stream_cancel.any_active()


def test_collect_state_publishes_busy_and_overlay_seq() -> None:
    stream_cancel.begin("s-overlay")
    state = shell_server._collect_state()
    assert state["busy"] is True
    assert state["overlay_seq"] == shell_overlay.toggle_seq()


def test_toggle_endpoint_requires_token_and_bumps_seq() -> None:
    client = TestClient(shell_server.app, client=("127.0.0.1", 50000))
    assert client.post("/overlay/toggle").status_code in (401, 403)
    before = shell_overlay.toggle_seq()
    r = client.post("/overlay/toggle", headers={"X-Celestia-Token": shell_server._API_TOKEN})
    assert r.status_code == 200 and r.json()["seq"] == before + 1


@pytest.mark.parametrize(
    "ui,expected",
    [
        ({}, "ctrl+alt+o"),
        ({"overlay_hotkey": "ctrl+shift+b"}, "ctrl+shift+b"),
        ({"overlay_hotkey": ""}, None),
        ({"overlay_enabled": False}, None),
    ],
)
def test_hotkey_spec(monkeypatch, ui, expected) -> None:
    monkeypatch.setattr(_cfg, "_config", {"ui": ui})
    assert shell_overlay._hotkey_spec() == expected


def test_listener_not_started_without_hotkey(monkeypatch) -> None:
    monkeypatch.setattr(_cfg, "_config", {"ui": {"overlay_hotkey": ""}})
    monkeypatch.setattr(_cfg, "load_config", lambda reload=False: _cfg._config)
    monkeypatch.setattr(shell_overlay, "_listener_started", False)
    shell_overlay.start_overlay_hotkey_listener()
    assert shell_overlay._listener_started is False
