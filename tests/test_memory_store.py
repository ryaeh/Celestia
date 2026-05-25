"""Tests for skills/memory/store.py — add_json(), search_json(), clear_all().

The mem0 Memory object is mocked so no Ollama embedding calls or Chroma disk
operations are performed.  We test only the Python-level logic in store.py.
"""

import pytest
from unittest.mock import MagicMock

import skills.memory.store as store_module
from skills.memory.store import add_json, search_json, clear_all, get_all_entries


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def mock_mem(monkeypatch):
    """Replace the mem0 Memory singleton with a controllable mock."""
    m = MagicMock()

    # Default return values that match the shape store.py expects
    m.add.return_value = {
        "results": [{"id": "abc123", "memory": "test content", "metadata": {"kind": "fact"}}]
    }
    m.search.return_value = {
        "results": [{"id": "abc123", "memory": "test content", "metadata": {"kind": "fact"}}]
    }
    m.get_all.return_value = {
        "results": [{"id": "abc123", "memory": "test content", "metadata": {"kind": "fact"}}]
    }
    m.delete_all.return_value = None

    # Inject the mock directly into the module
    monkeypatch.setattr(store_module, "_memory", m)
    return m


# ---------------------------------------------------------------------------
# add_json()
# ---------------------------------------------------------------------------

def test_add_json_returns_saved_string(mock_mem):
    result = add_json("I prefer dark mode", "test_user", kind="fact")
    assert isinstance(result, str)
    assert "Saved" in result


def test_add_json_calls_underlying_add(mock_mem):
    add_json("My name is Alice", "test_user", kind="instruction")
    mock_mem.add.assert_called_once()
    call_args = mock_mem.add.call_args
    assert "My name is Alice" in call_args.args[0]


def test_add_json_includes_kind_in_metadata(mock_mem):
    add_json("Run daily at 9am", "test_user", kind="task")
    call_kwargs = mock_mem.add.call_args.kwargs
    assert call_kwargs["metadata"]["kind"] == "task"


def test_add_json_handles_exception(mock_mem):
    """If the underlying add() raises, add_json must return an error string."""
    mock_mem.add.side_effect = RuntimeError("Chroma connection failed")
    result = add_json("something", "test_user")
    assert "failed" in result.lower() or "error" in result.lower()


# ---------------------------------------------------------------------------
# search_json()
# ---------------------------------------------------------------------------

def test_search_json_returns_string(mock_mem):
    result = search_json("dark mode preference", "test_user")
    assert isinstance(result, str)


def test_search_json_empty_results(mock_mem):
    mock_mem.search.return_value = {"results": []}
    result = search_json("something not stored", "test_user")
    assert isinstance(result, str)


# ---------------------------------------------------------------------------
# get_all_entries()
# ---------------------------------------------------------------------------

def test_get_all_entries_returns_list(mock_mem):
    entries = get_all_entries("test_user")
    assert isinstance(entries, list)


def test_get_all_entries_shape(mock_mem):
    entries = get_all_entries("test_user")
    assert len(entries) == 1
    entry = entries[0]
    assert "id" in entry
    assert "text" in entry
    assert "kind" in entry


def test_get_all_entries_empty_on_exception(mock_mem):
    mock_mem.get_all.side_effect = RuntimeError("DB offline")
    entries = get_all_entries("test_user")
    assert entries == []


# ---------------------------------------------------------------------------
# clear_all()
# ---------------------------------------------------------------------------

def test_clear_all_returns_string(mock_mem):
    result = clear_all("test_user")
    assert isinstance(result, str)


def test_clear_all_calls_delete(mock_mem):
    clear_all("test_user")
    # Either delete_all or delete_users — check that *something* was called
    assert mock_mem.delete_all.called or mock_mem.delete.called or mock_mem.reset.called
