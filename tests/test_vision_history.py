"""Tests for skills/vision/history.py — the screenshot ring-buffer index.

Covers the B-11 hardening: the read-modify-write in push() is lock-guarded and
the index is written atomically (no .tmp residue). The index dir is redirected
to tmp_path so tests never touch real captures.
"""

from __future__ import annotations

import json
import sys
import types

import pytest

# skills/vision/__init__.py eagerly imports flow -> capture -> mss/PIL, which are
# not installed in the test env. Stub the flow module so importing the pure
# history submodule doesn't drag in the heavy capture chain.
_flow_stub = types.ModuleType("skills.vision.flow")
_flow_stub.run_screen_ask = lambda *a, **k: None  # type: ignore[attr-defined]
sys.modules.setdefault("skills.vision.flow", _flow_stub)

import skills.vision.history as vh  # noqa: E402


@pytest.fixture()
def hist_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(vh, "_HIST_DIR", tmp_path)
    monkeypatch.setattr(vh, "_HIST_JSON", tmp_path / "index.json")
    monkeypatch.setattr(vh, "_HIST_LOCK", tmp_path / ".index.lock")
    return tmp_path


def _make_png(path) -> None:
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 16)


def test_push_records_entry_and_copies_file(hist_tmp):
    src = hist_tmp / "shot.png"
    _make_png(src)
    eid = vh.push(src)
    assert eid
    index = json.loads((hist_tmp / "index.json").read_text(encoding="utf-8"))
    assert len(index) == 1 and index[0]["id"] == eid
    assert (hist_tmp / f"{eid}.png").exists()


def test_get_path_round_trips(hist_tmp):
    src = hist_tmp / "shot.png"
    _make_png(src)
    eid = vh.push(src)
    p = vh.get_path(eid)
    assert p is not None and p.exists()
    assert vh.get_path("missing") is None


def test_push_enforces_max_entries(hist_tmp, monkeypatch):
    monkeypatch.setattr(vh, "MAX_ENTRIES", 3)
    ids = []
    for i in range(5):
        src = hist_tmp / f"s{i}.png"
        _make_png(src)
        ids.append(vh.push(src))
    index = json.loads((hist_tmp / "index.json").read_text(encoding="utf-8"))
    assert len(index) == 3
    assert not (hist_tmp / f"{ids[0]}.png").exists()  # oldest pruned
    assert (hist_tmp / f"{ids[-1]}.png").exists()


def test_push_writes_index_atomically(hist_tmp):
    src = hist_tmp / "shot.png"
    _make_png(src)
    vh.push(src)
    residue = [p.name for p in hist_tmp.iterdir() if p.name.endswith(".tmp")]
    assert residue == []
