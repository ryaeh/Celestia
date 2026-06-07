"""Tests for skills/files/tools.py — file_read() and file_write() happy paths and gates."""

from __future__ import annotations

import pytest

import celestia_core.config as _cfg
import celestia_core.scope as scope_mod
from skills.files.tools import file_read, file_write


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _config(monkeypatch):
    """Inject config defaults and skip disk I/O."""
    monkeypatch.setattr(_cfg, "load_config", lambda: None)
    monkeypatch.setattr(
        _cfg,
        "get",
        lambda key, default=None: {
            "security.file_read_max_bytes": 262144,
            "security.file_write_max_bytes": 524288,
            "pc_control.require_confirm_destructive": True,
        }.get(key, default),
    )


# ---------------------------------------------------------------------------
# file_read
# ---------------------------------------------------------------------------


def test_file_read_blocked_by_scope(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(scope_mod, "check_file_read", lambda p: "Blocked: not in workspace")
    f = tmp_path / "secret.txt"
    f.write_text("secret")
    result = file_read(str(f))
    assert "Blocked" in result


def test_file_read_returns_content(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(scope_mod, "check_file_read", lambda p: None)
    f = tmp_path / "hello.txt"
    f.write_text("world content")
    result = file_read(str(f))
    assert "world content" in result
    assert "hello.txt" in result


def test_file_read_wraps_content_in_code_block(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(scope_mod, "check_file_read", lambda p: None)
    f = tmp_path / "code.py"
    f.write_text("print('hi')")
    result = file_read(str(f))
    assert "```" in result


def test_file_read_file_too_large(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(scope_mod, "check_file_read", lambda p: None)
    f = tmp_path / "huge.bin"
    f.write_bytes(b"X" * (262144 + 1))
    result = file_read(str(f))
    assert "Blocked" in result
    assert "too large" in result.lower()


def test_file_read_long_content_truncated_for_chat(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(scope_mod, "check_file_read", lambda p: None)
    f = tmp_path / "long.txt"
    f.write_text("A" * 15000)  # > 12000 char truncation limit
    result = file_read(str(f))
    assert "truncated" in result


def test_file_read_nonexistent_file(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(scope_mod, "check_file_read", lambda p: None)
    result = file_read(str(tmp_path / "missing.txt"))
    assert "Blocked" in result
    assert "not a file" in result.lower()


# ---------------------------------------------------------------------------
# file_write
# ---------------------------------------------------------------------------


def test_file_write_blocked_by_scope(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(scope_mod, "check_file_write", lambda p: "Blocked: safe mode")
    result = file_write(str(tmp_path / "out.txt"), "content")
    assert "Blocked" in result


def test_file_write_creates_new_file(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(scope_mod, "check_file_write", lambda p: None)
    f = tmp_path / "out.txt"
    result = file_write(str(f), "hello!")
    assert "Wrote" in result
    assert f.read_text(encoding="utf-8") == "hello!"


def test_file_write_overwrites_with_confirm(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(scope_mod, "check_file_write", lambda p: None)
    f = tmp_path / "existing.txt"
    f.write_text("old content")
    result = file_write(str(f), "new content", confirm_overwrite=True)
    assert "Updated" in result
    assert f.read_text(encoding="utf-8") == "new content"


def test_file_write_overwrite_requires_confirm(monkeypatch, tmp_path) -> None:
    """When require_confirm_destructive=True and file exists, must block without confirm."""
    monkeypatch.setattr(scope_mod, "check_file_write", lambda p: None)
    f = tmp_path / "existing.txt"
    f.write_text("old")
    result = file_write(str(f), "new")  # confirm_overwrite defaults to False
    assert "Blocked" in result
    # File must be unchanged
    assert f.read_text(encoding="utf-8") == "old"


def test_file_write_content_too_large(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(scope_mod, "check_file_write", lambda p: None)
    f = tmp_path / "out.txt"
    big = "X" * (524288 + 1)
    result = file_write(str(f), big)
    assert "Blocked" in result
    assert "too large" in result.lower()


def test_file_write_creates_parent_directories(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(scope_mod, "check_file_write", lambda p: None)
    f = tmp_path / "deep" / "nested" / "file.txt"
    result = file_write(str(f), "data")
    assert "Wrote" in result
    assert f.read_text(encoding="utf-8") == "data"


def test_file_write_reports_byte_count(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(scope_mod, "check_file_write", lambda p: None)
    f = tmp_path / "counted.txt"
    result = file_write(str(f), "hello")
    assert "5" in result  # "hello" = 5 bytes
