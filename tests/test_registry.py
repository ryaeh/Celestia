"""Tests for skills/registry.py — execute_tool() dispatch and tool_schemas() filtering."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

import celestia_core.config as _cfg
import celestia_core.security as sec
import skills.registry as reg


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    """Safe mode, no audit log, no disk config."""
    monkeypatch.setattr(sec, "get_mode", lambda: "safe")
    monkeypatch.setattr(sec, "audit_tool", lambda *a, **kw: None)
    monkeypatch.setattr(_cfg, "load_config", lambda: None)
    monkeypatch.setattr(_cfg, "get", lambda key, default=None: default)


# ---------------------------------------------------------------------------
# file_read / file_write dispatch
# ---------------------------------------------------------------------------


def test_execute_tool_file_read_calls_file_read(monkeypatch) -> None:
    monkeypatch.setattr(reg, "file_read", lambda path: "## file\n```\nhello\n```")
    result = reg.execute_tool("file_read", {"path": "C:\\foo.txt"}, "user1")
    assert "hello" in result


def test_execute_tool_file_write_calls_file_write(monkeypatch) -> None:
    monkeypatch.setattr(
        reg, "file_write", lambda path, content, confirm_overwrite=False: "Wrote: foo.txt (5 bytes)"
    )
    result = reg.execute_tool(
        "file_write", {"path": "C:\\foo.txt", "content": "hello"}, "user1"
    )
    assert "Wrote" in result


def test_execute_tool_file_write_passes_confirm_overwrite(monkeypatch) -> None:
    captured: dict = {}

    def _fake_write(path, content, *, confirm_overwrite=False):
        captured["confirm_overwrite"] = confirm_overwrite
        return "Updated: foo.txt"

    monkeypatch.setattr(reg, "file_write", _fake_write)
    reg.execute_tool(
        "file_write",
        {"path": "C:\\foo.txt", "content": "data", "confirm_overwrite": True},
        "user1",
    )
    assert captured["confirm_overwrite"] is True


# ---------------------------------------------------------------------------
# Memory dispatch
# ---------------------------------------------------------------------------


def test_execute_tool_memory_add(monkeypatch) -> None:
    mock_store = MagicMock()
    mock_store.add_json.return_value = "Stored."
    monkeypatch.setattr(reg, "memory", mock_store)
    result = reg.execute_tool("memory_add", {"content": "I like coffee"}, "user1")
    assert result == "Stored."
    mock_store.add_json.assert_called_once_with("I like coffee", "user1", kind="fact")


def test_execute_tool_memory_search(monkeypatch) -> None:
    mock_store = MagicMock()
    mock_store.search_json.return_value = "Result: coffee preference"
    monkeypatch.setattr(reg, "memory", mock_store)
    result = reg.execute_tool("memory_search", {"query": "coffee"}, "user1")
    assert "coffee" in result
    mock_store.search_json.assert_called_once_with("coffee", "user1")


def test_execute_tool_memory_list(monkeypatch) -> None:
    mock_store = MagicMock()
    mock_store.format_list.return_value = "1. I like coffee"
    monkeypatch.setattr(reg, "memory", mock_store)
    result = reg.execute_tool("memory_list", {}, "user1")
    assert "coffee" in result


def test_execute_tool_memory_delete_by_id(monkeypatch) -> None:
    mock_store = MagicMock()
    mock_store.delete_by_id.return_value = "Deleted."
    monkeypatch.setattr(reg, "memory", mock_store)
    result = reg.execute_tool("memory_delete", {"memory_id": "abc-123"}, "user1")
    assert result == "Deleted."
    mock_store.delete_by_id.assert_called_once_with("abc-123")


def test_execute_tool_memory_delete_no_args(monkeypatch) -> None:
    mock_store = MagicMock()
    monkeypatch.setattr(reg, "memory", mock_store)
    result = reg.execute_tool("memory_delete", {}, "user1")
    assert "memory_id" in result or "match_text" in result


# ---------------------------------------------------------------------------
# Web search dispatch
# ---------------------------------------------------------------------------


def test_execute_tool_web_search(monkeypatch) -> None:
    monkeypatch.setattr(reg, "web_search", lambda query, num_results=5: "search results here")
    result = reg.execute_tool("web_search", {"query": "python asyncio"}, "user1")
    assert result == "search results here"


def test_execute_tool_fetch_page(monkeypatch) -> None:
    monkeypatch.setattr(reg, "fetch_page", lambda url, max_chars=3000: "page content")
    result = reg.execute_tool("fetch_page", {"url": "https://example.com"}, "user1")
    assert result == "page content"


# ---------------------------------------------------------------------------
# PC tool gate — safe mode blocks
# ---------------------------------------------------------------------------


def test_execute_tool_run_powershell_blocked_in_safe_mode() -> None:
    result = reg.execute_tool("run_powershell", {"command": "Get-Date"}, "user1")
    assert "Blocked" in result


def test_execute_tool_open_path_blocked_in_safe_mode() -> None:
    result = reg.execute_tool("open_path", {"path": "notepad"}, "user1")
    assert "Blocked" in result


def test_execute_tool_open_url_blocked_in_safe_mode() -> None:
    result = reg.execute_tool("open_url", {"url": "https://github.com"}, "user1")
    assert "Blocked" in result


def test_execute_tool_get_system_status_allowed_in_safe_mode(monkeypatch) -> None:
    """get_system_status is in PC_TOOLS_ALWAYS_OK — must pass even in safe mode."""
    # Mock execute_pc so no real PowerShell runs
    monkeypatch.setattr(reg, "execute_pc", lambda name, args: "CPU: 5%")
    result = reg.execute_tool("get_system_status", {}, "user1")
    assert "CPU" in result


# ---------------------------------------------------------------------------
# Unknown tool
# ---------------------------------------------------------------------------


def test_execute_tool_unknown_in_armed_mode(monkeypatch) -> None:
    monkeypatch.setattr(sec, "get_mode", lambda: "armed")
    result = reg.execute_tool("totally_unknown_xyz", {}, "user1")
    assert "Unknown" in result or "error" in result.lower()


# ---------------------------------------------------------------------------
# tool_schemas — safe mode filtering
# ---------------------------------------------------------------------------


def test_tool_schemas_safe_mode_excludes_blocked_pc_tools() -> None:
    schemas = reg.tool_schemas("hello")
    names = {s["function"]["name"] for s in schemas}
    # Blocked in safe mode — must be absent
    assert "run_powershell" not in names
    assert "open_path" not in names
    assert "open_url" not in names
    assert "file_read" not in names
    assert "file_write" not in names


def test_tool_schemas_safe_mode_includes_always_ok_tools() -> None:
    schemas = reg.tool_schemas("hello")
    names = {s["function"]["name"] for s in schemas}
    assert "get_system_status" in names
    assert "list_processes" in names


def test_tool_schemas_armed_mode_includes_pc_tools(monkeypatch) -> None:
    monkeypatch.setattr(sec, "get_mode", lambda: "armed")
    # Trigger message contains open keyword so open_path/open_url are included
    schemas = reg.tool_schemas("open youtube please")
    names = {s["function"]["name"] for s in schemas}
    assert "run_powershell" in names
    assert "open_path" in names
    assert "open_url" in names


def test_tool_schemas_no_open_triggers_skips_open_tools(monkeypatch) -> None:
    """Without open/launch/etc. triggers, open_path and open_url are omitted."""
    monkeypatch.setattr(sec, "get_mode", lambda: "armed")
    schemas = reg.tool_schemas("what time is it")
    names = {s["function"]["name"] for s in schemas}
    assert "open_path" not in names
    assert "open_url" not in names
    # But run_powershell should still be present
    assert "run_powershell" in names
