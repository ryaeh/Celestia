"""Tests for celestia_core/file_utils.py — atomic_write_text + file_lock (F-01)."""

import os

from celestia_core.file_utils import atomic_write_text, file_lock


def test_atomic_write_creates_file(tmp_path):
    target = tmp_path / "state.json"
    atomic_write_text(target, '{"mode": "safe"}')
    assert target.read_text(encoding="utf-8") == '{"mode": "safe"}'


def test_atomic_write_overwrites_existing(tmp_path):
    target = tmp_path / "state.json"
    target.write_text("old", encoding="utf-8")
    atomic_write_text(target, "new")
    assert target.read_text(encoding="utf-8") == "new"


def test_atomic_write_creates_parent_dirs(tmp_path):
    target = tmp_path / "nested" / "deep" / "state.json"
    atomic_write_text(target, "x")
    assert target.read_text(encoding="utf-8") == "x"


def test_atomic_write_leaves_no_temp_residue(tmp_path):
    target = tmp_path / "state.json"
    atomic_write_text(target, "data")
    leftovers = [p.name for p in tmp_path.iterdir() if p.name != "state.json"]
    assert leftovers == [], f"unexpected temp files: {leftovers}"


def test_atomic_write_cleans_up_on_serialization_error(tmp_path):
    """A failure while producing the text must not leave a .tmp behind."""
    target = tmp_path / "state.json"

    class Boom:
        def __str__(self) -> str:  # pragma: no cover - defensive
            raise RuntimeError("boom")

    # The write itself is given a real string; simulate a mid-write failure by
    # passing a non-encodable surrogate that str.write rejects under utf-8.
    try:
        atomic_write_text(target, "\udc80")  # lone surrogate -> UnicodeEncodeError
    except UnicodeEncodeError:
        pass
    leftovers = list(tmp_path.iterdir())
    assert leftovers == [], f"temp file not cleaned up: {leftovers}"
    assert not target.exists()


def test_file_lock_acquires_and_releases(tmp_path):
    lock = tmp_path / ".lock"
    with file_lock(lock):
        assert lock.exists()
    # Re-acquiring after release must not block or raise.
    with file_lock(lock):
        pass


def test_file_lock_creates_parent(tmp_path):
    lock = tmp_path / "sub" / ".lock"
    with file_lock(lock):
        assert lock.parent.is_dir()
