"""Shared pytest configuration and utilities."""

import sys
from pathlib import Path

# Ensure the repo root is importable regardless of where pytest is invoked from.
ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


import pytest


@pytest.fixture(autouse=True)
def _isolated_memory_files(tmp_path, monkeypatch):
    """The knowledge graph is on by default (T15). Point every test at a temp
    graph DB and last-session note so no test writes data/memory/ in the repo;
    tests with their own fixtures override these again."""
    import skills.memory.graph_store as gs
    import skills.memory.last_session as ls

    monkeypatch.setattr(gs, "_db_path", lambda: tmp_path / "graph.db")
    monkeypatch.setattr(ls, "_path", lambda: tmp_path / "last_session.json")
    gs.reset_connection()
    yield
    gs.reset_connection()
