"""Tests for the to-do store (skills/todos/store.py)."""

from __future__ import annotations

import json

import pytest

import skills.todos.store as store


@pytest.fixture()
def todos_tmp(tmp_path, monkeypatch):
    path = tmp_path / "todos.json"
    monkeypatch.setattr(store, "_todos_path", lambda: path)
    yield path


def _read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_add_todo_writes_item(todos_tmp):
    item = store.add_todo("Buy milk", "u1", priority="high", due="2026-06-20")
    data = _read(todos_tmp)
    assert len(data) == 1
    assert data[0]["text"] == "Buy milk"
    assert data[0]["priority"] == "high"
    assert data[0]["due"] == "2026-06-20"
    assert data[0]["done"] is False
    assert data[0]["user_id"] == "u1"
    assert item["id"] == data[0]["id"]


def test_add_todo_rejects_empty(todos_tmp):
    with pytest.raises(ValueError):
        store.add_todo("   ", "u1")


def test_add_todo_normalizes_bad_priority(todos_tmp):
    item = store.add_todo("x", "u1", priority="urgent")
    assert item["priority"] == "normal"


def test_list_todos_filters_by_user(todos_tmp):
    store.add_todo("a", "u1")
    store.add_todo("b", "u2")
    assert [t["text"] for t in store.list_todos("u1")] == ["a"]


def test_list_todos_include_done_toggle(todos_tmp):
    t = store.add_todo("a", "u1")
    store.add_todo("b", "u1")
    store.update_todo(t["id"], done=True, user_id="u1")
    assert len(store.list_todos("u1", include_done=True)) == 2
    assert len(store.list_todos("u1", include_done=False)) == 1


def test_list_sorted_open_and_priority_first(todos_tmp):
    low = store.add_todo("low", "u1", priority="low")
    high = store.add_todo("high", "u1", priority="high")
    store.update_todo(low["id"], done=True, user_id="u1")  # done sinks
    order = [t["text"] for t in store.list_todos("u1")]
    assert order[0] == "high"
    assert order[-1] == "low"


def test_update_todo_sets_completed_at(todos_tmp):
    t = store.add_todo("a", "u1")
    updated = store.update_todo(t["id"], done=True, user_id="u1")
    assert updated["done"] is True
    assert updated["completed_at"] is not None
    reopened = store.update_todo(t["id"], done=False, user_id="u1")
    assert reopened["completed_at"] is None


def test_update_todo_missing_returns_none(todos_tmp):
    assert store.update_todo("nope", text="x", user_id="u1") is None


def test_update_todo_clears_due_with_empty_string(todos_tmp):
    t = store.add_todo("a", "u1", due="2026-01-01")
    updated = store.update_todo(t["id"], due="", user_id="u1")
    assert updated["due"] is None


def test_update_respects_user_scope(todos_tmp):
    t = store.add_todo("a", "u1")
    assert store.update_todo(t["id"], text="x", user_id="u2") is None


def test_delete_todo(todos_tmp):
    t = store.add_todo("a", "u1")
    assert store.delete_todo(t["id"], "u1") is True
    assert store.list_todos("u1") == []
    assert store.delete_todo(t["id"], "u1") is False


def test_clear_done(todos_tmp):
    a = store.add_todo("a", "u1")
    store.add_todo("b", "u1")
    store.update_todo(a["id"], done=True, user_id="u1")
    assert store.clear_done("u1") == 1
    assert [t["text"] for t in store.list_todos("u1")] == ["b"]


def test_load_handles_missing_and_corrupt(todos_tmp, monkeypatch):
    assert store._load() == []  # missing file
    todos_tmp.write_text("not json", encoding="utf-8")
    assert store._load() == []  # corrupt file
