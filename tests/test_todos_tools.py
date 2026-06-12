"""Tests for the to-do tools + registry dispatch."""

from __future__ import annotations

import pytest

import skills.todos.store as store
import skills.todos.tools as tools
import skills.registry as reg
from celestia_core import security as sec
import celestia_core.config as _cfg


@pytest.fixture()
def todos_tmp(tmp_path, monkeypatch):
    path = tmp_path / "todos.json"
    monkeypatch.setattr(store, "_todos_path", lambda: path)
    yield path


def test_todo_add_and_list(todos_tmp):
    assert "Added to-do" in tools.todo_add("Buy milk", "u1", priority="high")
    listing = tools.todo_list("u1")
    assert "Buy milk" in listing
    assert "(high)" in listing
    assert "1 open" in listing


def test_todo_list_empty(todos_tmp):
    assert tools.todo_list("u1") == "Your to-do list is empty."


def test_todo_complete_by_match_text(todos_tmp):
    tools.todo_add("Write report", "u1")
    msg = tools.todo_complete("u1", match_text="report")
    assert "Completed" in msg
    # default list hides done items
    assert tools.todo_list("u1") == "Your to-do list is empty."
    assert "Write report" in tools.todo_list("u1", include_done=True)


def test_todo_complete_ambiguous(todos_tmp):
    tools.todo_add("call mom", "u1")
    tools.todo_add("call dad", "u1")
    msg = tools.todo_complete("u1", match_text="call")
    assert "Ambiguous" in msg


def test_todo_complete_no_match(todos_tmp):
    assert "No to-do matching" in tools.todo_complete("u1", match_text="ghost")


def test_todo_complete_requires_selector(todos_tmp):
    assert "Provide todo_id or match_text" in tools.todo_complete("u1")


def test_todo_update_changes_priority(todos_tmp):
    tools.todo_add("task", "u1")
    msg = tools.todo_update("u1", match_text="task", priority="high")
    assert "Updated" in msg and "(high)" in msg


def test_todo_remove(todos_tmp):
    tools.todo_add("temp", "u1")
    assert "Removed" in tools.todo_remove("u1", match_text="temp")
    assert tools.todo_list("u1") == "Your to-do list is empty."


def test_todo_user_isolation(todos_tmp):
    tools.todo_add("mine", "u1")
    assert tools.todo_list("u2") == "Your to-do list is empty."


# --- registry dispatch ------------------------------------------------------

@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    monkeypatch.setattr(sec, "audit_tool", lambda *a, **kw: None)
    monkeypatch.setattr(_cfg, "load_config", lambda: None)


def test_execute_tool_todo_add(todos_tmp):
    result = reg.execute_tool("todo_add", {"text": "from registry"}, "u1")
    assert "Added to-do" in result
    assert any(t["text"] == "from registry" for t in store.list_todos("u1"))


def test_execute_tool_todo_list(todos_tmp):
    store.add_todo("listed", "u1")
    result = reg.execute_tool("todo_list", {}, "u1")
    assert "listed" in result


def test_todo_schemas_present_in_armed(monkeypatch):
    monkeypatch.setattr(sec, "get_mode", lambda: "armed")
    monkeypatch.setattr(_cfg, "get", lambda key, default=None: default)
    names = {s["function"]["name"] for s in reg.tool_schemas()}
    assert {"todo_add", "todo_list", "todo_complete", "todo_update", "todo_remove"} <= names


def test_todo_schemas_present_in_safe(monkeypatch):
    monkeypatch.setattr(sec, "get_mode", lambda: "safe")
    monkeypatch.setattr(_cfg, "get", lambda key, default=None: default)
    names = {s["function"]["name"] for s in reg.tool_schemas()}
    assert "todo_add" in names
