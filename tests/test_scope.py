"""Tests for celestia_core/scope.py — workspace checks, file access gates, URL policy.

All disk I/O is redirected to tmp_path; real files are created where the function
checks existence (e.g. is_file()).  Platform calls are stubbed via _plat().
"""

from __future__ import annotations

from pathlib import Path

import pytest

import celestia_core.config as _cfg
import celestia_core.scope as scope_mod
import celestia_core.security as sec


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class _FakePlat:
    BLOCKED_APP_NAMES: frozenset = frozenset()

    def normalize(self, path: str) -> Path | None:
        p = Path(path)
        return p if p.is_absolute() else None

    def is_protected(self, path: Path) -> bool:
        return False

    def default_notepad_exe(self) -> Path:
        return Path("notepad.exe")

    def find_builtin_exe(self, names: list, rel: list) -> Path | None:
        return None


@pytest.fixture(autouse=True)
def _no_io(monkeypatch):
    """Prevent scope.py from loading config.yaml from disk.

    scope.py does `from celestia_core.config import get, load_config` at the
    module level, so patching _cfg.get alone would have no effect — we must
    patch the names in scope_mod's own namespace.
    """
    monkeypatch.setattr(scope_mod, "load_config", lambda: None)
    monkeypatch.setattr(scope_mod, "get", lambda key, default=None: default)
    monkeypatch.setattr(scope_mod, "_plat", lambda: _FakePlat())


# ---------------------------------------------------------------------------
# check_file_read
# ---------------------------------------------------------------------------


def test_check_file_read_safe_mode_blocked(monkeypatch) -> None:
    monkeypatch.setattr(sec, "get_mode", lambda: "safe")
    result = scope_mod.check_file_read("C:\\some\\file.txt")
    assert result is not None
    assert "Blocked" in result


def test_check_file_read_scoped_file_in_workspace(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(sec, "get_mode", lambda: "scoped")
    f = tmp_path / "notes.txt"
    f.write_text("hello")
    monkeypatch.setattr(scope_mod, "list_workspaces", lambda: [tmp_path])
    assert scope_mod.check_file_read(str(f)) is None


def test_check_file_read_scoped_file_outside_workspace(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(sec, "get_mode", lambda: "scoped")
    f = tmp_path / "file.txt"
    f.write_text("data")
    other = tmp_path / "workspace"
    other.mkdir()
    monkeypatch.setattr(scope_mod, "list_workspaces", lambda: [other])
    result = scope_mod.check_file_read(str(f))
    assert result is not None
    assert "Blocked" in result


def test_check_file_read_armed_allows_any_file(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(sec, "get_mode", lambda: "armed")
    f = tmp_path / "anywhere.txt"
    f.write_text("content")
    assert scope_mod.check_file_read(str(f)) is None


def test_check_file_read_nonexistent_file_blocked(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(sec, "get_mode", lambda: "scoped")
    monkeypatch.setattr(scope_mod, "list_workspaces", lambda: [tmp_path])
    result = scope_mod.check_file_read(str(tmp_path / "missing.txt"))
    assert result is not None
    assert "Blocked" in result


# ---------------------------------------------------------------------------
# check_file_write
# ---------------------------------------------------------------------------


def test_check_file_write_safe_mode_blocked(monkeypatch) -> None:
    monkeypatch.setattr(sec, "get_mode", lambda: "safe")
    result = scope_mod.check_file_write("C:\\foo.txt")
    assert result is not None
    assert "Blocked" in result


def test_check_file_write_scoped_inside_workspace(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(sec, "get_mode", lambda: "scoped")
    f = tmp_path / "out.txt"
    monkeypatch.setattr(scope_mod, "list_workspaces", lambda: [tmp_path])
    assert scope_mod.check_file_write(str(f)) is None


def test_check_file_write_scoped_outside_workspace_blocked(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(sec, "get_mode", lambda: "scoped")
    f = tmp_path / "out.txt"
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setattr(scope_mod, "list_workspaces", lambda: [ws])
    result = scope_mod.check_file_write(str(f))
    assert result is not None
    assert "Blocked" in result


def test_check_file_write_armed_allows_any_path(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(sec, "get_mode", lambda: "armed")
    f = tmp_path / "anywhere.txt"
    # File does not exist yet — that's fine for write
    assert scope_mod.check_file_write(str(f)) is None


def test_check_file_write_path_is_directory_blocked(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(sec, "get_mode", lambda: "scoped")
    monkeypatch.setattr(scope_mod, "list_workspaces", lambda: [tmp_path])
    # Pass an existing directory as the write target
    result = scope_mod.check_file_write(str(tmp_path))
    assert result is not None
    assert "directory" in result.lower()


# ---------------------------------------------------------------------------
# check_open_url
# ---------------------------------------------------------------------------


def test_check_open_url_armed_always_passes(monkeypatch) -> None:
    monkeypatch.setattr(sec, "get_mode", lambda: "armed")
    assert scope_mod.check_open_url("https://anything.com") is None


def test_check_open_url_safe_always_passes(monkeypatch) -> None:
    """check_open_url only restricts in scoped mode; safe/armed pass through."""
    monkeypatch.setattr(sec, "get_mode", lambda: "safe")
    assert scope_mod.check_open_url("https://anything.com") is None


def test_check_open_url_scoped_empty_allowlist_blocked(monkeypatch) -> None:
    monkeypatch.setattr(sec, "get_mode", lambda: "scoped")
    # get("security.url_allowlist") returns None → empty allowlist
    result = scope_mod.check_open_url("https://github.com")
    assert result is not None
    assert "Blocked" in result


def test_check_open_url_scoped_host_on_allowlist_passes(monkeypatch) -> None:
    monkeypatch.setattr(sec, "get_mode", lambda: "scoped")
    # Patch the 'get' name bound in scope_mod, not celestia_core.config.get,
    # because scope.py does `from celestia_core.config import get` at module level.
    monkeypatch.setattr(
        scope_mod,
        "get",
        lambda key, default=None: (
            ["github.com"] if key == "security.url_allowlist" else default
        ),
    )
    result = scope_mod.check_open_url("https://github.com/ryaeh/celestia")
    assert result is None


def test_check_open_url_scoped_host_not_on_allowlist_blocked(monkeypatch) -> None:
    monkeypatch.setattr(sec, "get_mode", lambda: "scoped")
    monkeypatch.setattr(
        scope_mod,
        "get",
        lambda key, default=None: (
            ["github.com"] if key == "security.url_allowlist" else default
        ),
    )
    result = scope_mod.check_open_url("https://evilsite.example.com")
    assert result is not None
    assert "Blocked" in result


# ---------------------------------------------------------------------------
# _is_under_workspace (via check_file_read integration)
# ---------------------------------------------------------------------------


def test_is_under_workspace_subdirectory(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(sec, "get_mode", lambda: "scoped")
    sub = tmp_path / "projects" / "myapp"
    sub.mkdir(parents=True)
    f = sub / "main.py"
    f.write_text("print('hello')")
    monkeypatch.setattr(scope_mod, "list_workspaces", lambda: [tmp_path])
    # File is nested two levels under workspace — should still pass
    assert scope_mod.check_file_read(str(f)) is None


def test_is_under_workspace_sibling_directory_blocked(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(sec, "get_mode", lambda: "scoped")
    ws = tmp_path / "workspace"
    ws.mkdir()
    sibling = tmp_path / "sibling"
    sibling.mkdir()
    f = sibling / "data.txt"
    f.write_text("secret")
    monkeypatch.setattr(scope_mod, "list_workspaces", lambda: [ws])
    result = scope_mod.check_file_read(str(f))
    assert result is not None
    assert "Blocked" in result
