"""Tests for celestia_core/security.py — gate_pc_tool() and mode logic.

All tests that touch gate_pc_tool() mock get_mode() to avoid reading or
writing the security_state.json file on disk.
"""

import pytest

import celestia_core.security as sec
from celestia_core.security import (
    gate_pc_tool,
    next_mode_cycled,
    armed_status_label,
    PC_TOOLS_ALWAYS_OK,
    PC_TOOLS_SAFE_BLOCK,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture()
def safe_mode(monkeypatch):
    monkeypatch.setattr(sec, "get_mode", lambda: "safe")


@pytest.fixture()
def armed_mode(monkeypatch):
    monkeypatch.setattr(sec, "get_mode", lambda: "armed")


# ---------------------------------------------------------------------------
# Safe mode — PC tools blocked
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("tool", sorted(PC_TOOLS_SAFE_BLOCK))
def test_safe_blocks_pc_tools(safe_mode, tool):
    result = gate_pc_tool(tool, {"path": "notepad", "url": "https://example.com"})
    assert result is not None, f"{tool} should be blocked in safe mode"
    assert "Blocked" in result


def test_safe_allows_always_ok_tools(safe_mode):
    for tool in PC_TOOLS_ALWAYS_OK:
        assert gate_pc_tool(tool, {}) is None, f"{tool} must pass in safe mode"


def test_safe_allows_unknown_tool(safe_mode):
    """Tools not in any blocklist should pass through regardless of mode."""
    assert gate_pc_tool("some_unknown_tool", {}) is None


# ---------------------------------------------------------------------------
# Armed mode — PC tools allowed (except file path checks)
# ---------------------------------------------------------------------------

def test_armed_allows_open_path(armed_mode):
    assert gate_pc_tool("open_path", {"path": "notepad"}) is None


def test_armed_allows_open_url(armed_mode):
    assert gate_pc_tool("open_url", {"url": "https://example.com"}) is None


def test_armed_allows_clipboard(armed_mode):
    assert gate_pc_tool("clipboard_read", {}) is None
    assert gate_pc_tool("clipboard_write", {"text": "hello"}) is None


def test_armed_allows_always_ok(armed_mode):
    for tool in PC_TOOLS_ALWAYS_OK:
        assert gate_pc_tool(tool, {}) is None


# ---------------------------------------------------------------------------
# Mode cycling logic — no I/O
# ---------------------------------------------------------------------------

def test_cycle_safe_to_scoped():
    assert next_mode_cycled("safe") == "scoped"


def test_cycle_scoped_to_armed():
    assert next_mode_cycled("scoped") == "armed"


def test_cycle_armed_wraps_to_safe():
    assert next_mode_cycled("armed") == "safe"


def test_cycle_capped_at_scoped():
    """When tray_max_mode=scoped, cycling armed should wrap to safe, not armed."""
    assert next_mode_cycled("scoped", max_mode="scoped") == "safe"
    assert next_mode_cycled("safe", max_mode="scoped") == "scoped"


# ---------------------------------------------------------------------------
# Status label — no I/O
# ---------------------------------------------------------------------------

def test_status_label_safe(monkeypatch):
    monkeypatch.setattr(sec, "get_mode", lambda: "safe")
    monkeypatch.setattr(sec, "get_tray_max_mode", lambda: None)
    assert "safe" in armed_status_label().lower()


def test_status_label_armed(monkeypatch):
    monkeypatch.setattr(sec, "get_mode", lambda: "armed")
    monkeypatch.setattr(sec, "get_tray_max_mode", lambda: None)
    assert "ARMED" in armed_status_label()
