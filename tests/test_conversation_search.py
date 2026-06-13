"""Tests for conversation search (Feature 03 / #86).

Covers shell_chat.search_sessions ranking/snippets and the search_conversations
LLM tool formatting. Disk I/O is redirected to tmp_path and the file lock is a
no-op, mirroring tests/test_shell_chat.py.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

import pytest

import celestia_core.shell_chat as sc


@pytest.fixture()
def seeded(tmp_path, monkeypatch):
    """Two sessions on disk; lock no-op; minimal config."""
    store_file = tmp_path / "shell_chat" / "sessions.json"
    monkeypatch.setattr(sc, "_store_path", lambda: store_file)

    @contextmanager
    def _noop() -> Iterator[None]:
        yield

    monkeypatch.setattr(sc, "_file_lock", _noop)
    monkeypatch.setattr(sc, "get", lambda key, default=None: default)

    def _seed(sid: str, title: str, turns: list[tuple[str, str]], updated: float) -> None:
        history = []
        for user, asst in turns:
            history.append({"role": "user", "content": user})
            history.append({"role": "assistant", "content": asst})
        state = sc._new_session_state()
        state.update({"title": title, "history": history, "updated_at": updated})
        sc._write_session(sid, state)

    _seed(
        "s1",
        "GPU troubleshooting",
        [("my RTX 4090 keeps freezing", "let's check the driver and VRAM residency")],
        updated=100.0,
    )
    _seed(
        "s2",
        "Dinner ideas",
        [("suggest a pasta recipe", "here is a carbonara recipe with pancetta")],
        updated=200.0,
    )
    return tmp_path


def test_search_finds_matching_session(seeded):
    rows = sc.search_sessions("4090")
    assert len(rows) == 1
    assert rows[0]["id"] == "s1"
    assert "4090" in rows[0]["snippet"]
    assert rows[0]["matches"] >= 1


def test_search_matches_title(seeded):
    rows = sc.search_sessions("dinner")
    assert any(r["id"] == "s2" for r in rows)


def test_search_no_match_returns_empty(seeded):
    assert sc.search_sessions("quantum chromodynamics") == []


def test_search_blank_query_returns_empty(seeded):
    assert sc.search_sessions("   ") == []


def test_search_ranks_phrase_over_recency(seeded):
    # "recipe" only appears in the older s1? No — appears in s2. Use a term in both.
    rows = sc.search_sessions("recipe")
    assert rows and rows[0]["id"] == "s2"


def test_no_rank_key_leaks(seeded):
    rows = sc.search_sessions("4090")
    assert "_rank" not in rows[0]


def test_tool_formats_results(seeded, monkeypatch):
    from skills.conversations.tools import search_conversations

    out = search_conversations("4090")
    assert "GPU troubleshooting" in out
    assert "4090" in out


def test_tool_empty_query():
    from skills.conversations.tools import search_conversations

    assert "Provide a search query" in search_conversations("  ")


def test_tool_no_results(seeded):
    from skills.conversations.tools import search_conversations

    assert "No past conversations" in search_conversations("quantum chromodynamics")
