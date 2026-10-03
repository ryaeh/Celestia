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


def test_add_json_tags_importance_by_kind(mock_mem):
    """Each saved memory carries a write-time importance (high for instructions,
    low for summaries) so ranking/decay have a signal to work from."""
    add_json("Always greet me by name", "test_user", kind="instruction")
    inst_imp = mock_mem.add.call_args.kwargs["metadata"]["importance"]
    add_json("we chatted about pasta", "test_user", kind="summary")
    summ_imp = mock_mem.add.call_args.kwargs["metadata"]["importance"]
    assert inst_imp == 1.0
    assert inst_imp > summ_imp


def test_add_json_stamps_created_at(mock_mem):
    add_json("something durable", "test_user", kind="fact")
    assert "created_at" in mock_mem.add.call_args.kwargs["metadata"]


def test_add_json_created_at_is_iso_string(mock_mem):
    """mem0 parses payload created_at as ISO on every read — a float (time.time())
    there made get_all/search raise, so nothing was ever recalled."""
    from datetime import datetime

    add_json("something durable", "test_user", kind="fact")
    ts = mock_mem.add.call_args.kwargs["metadata"]["created_at"]
    assert isinstance(ts, str)
    assert datetime.fromisoformat(ts).tzinfo is not None


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


def test_get_all_entries_logs_failure(mock_mem, caplog):
    """A read failure must not be silent — it hid broken recall before."""
    mock_mem.get_all.side_effect = RuntimeError("DB offline")
    with caplog.at_level("ERROR", logger="celestia.memory"):
        get_all_entries("test_user")
    assert "DB offline" in caplog.text


def test_reads_scope_by_filters_not_top_level_user_id(mock_mem):
    """mem0 2.x rejects get_all/search(user_id=...); scope must go in filters."""
    get_all_entries("test_user")
    search_json("anything", "test_user")
    for call in (mock_mem.get_all.call_args, mock_mem.search.call_args):
        assert "user_id" not in call.kwargs
        assert call.kwargs["filters"] == {"user_id": "test_user"}


# ---------------------------------------------------------------------------
# _repair_float_timestamps()
# ---------------------------------------------------------------------------

def test_repair_rewrites_float_timestamps_as_iso():
    from datetime import datetime

    col = MagicMock()
    col.get.return_value = {
        "ids": ["old", "ok"],
        "metadatas": [
            {"data": "Location: Ankara", "created_at": 1791026685.9, "updated_at": 1791026685.9, "kind": "fact"},
            {"data": "fine", "created_at": "2026-10-03T11:00:00+00:00", "kind": "fact"},
        ],
    }
    mem = MagicMock()
    mem.vector_store.collection = col

    store_module._repair_float_timestamps(mem)

    col.update.assert_called_once()
    kwargs = col.update.call_args.kwargs
    assert kwargs["ids"] == ["old"]  # already-ISO rows are left alone
    fixed = kwargs["metadatas"][0]
    assert fixed["kind"] == "fact" and fixed["data"] == "Location: Ankara"
    for key in ("created_at", "updated_at"):
        assert abs(datetime.fromisoformat(fixed[key]).timestamp() - 1791026685.9) < 1e-3


def test_repair_is_noop_when_nothing_to_fix():
    col = MagicMock()
    col.get.return_value = {"ids": ["a"], "metadatas": [{"created_at": "2026-10-03T11:00:00+00:00"}]}
    mem = MagicMock()
    mem.vector_store.collection = col
    store_module._repair_float_timestamps(mem)
    col.update.assert_not_called()


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
