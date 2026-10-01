"""Text-memory ↔ graph links and the superseded-memory history (T15).

Each text memory written by the memory writer records the ids of the graph
edges derived from it, so a later update / supersede / forget can move the
graph in step with the text. Links live in a JSON **sidecar**
(``data/memory/graph_links.json``) keyed by memory id — like the recall-stats
sidecar, so linking never rewrites a vector.

Superseded memories are appended to ``data/memory/history.jsonl`` before the
live entry is removed: the text store stays clean for recall, the old fact is
still on disk, and the graph keeps the same history as ended edges.
Forgotten memories are *not* logged — the user asked for them to be gone.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from celestia_core.config import ROOT
from celestia_core.file_utils import atomic_write_text, file_lock


def _dir() -> Path:
    d = ROOT / "data" / "memory"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _links_path() -> Path:
    return _dir() / "graph_links.json"


def _lock_path() -> Path:
    return _dir() / "graph_links.lock"


def _history_path() -> Path:
    return _dir() / "history.jsonl"


def load_links() -> dict[str, list[str]]:
    path = _links_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return {str(k): [str(e) for e in v] for k, v in data.items() if isinstance(v, list)} if isinstance(data, dict) else {}


def edges_for(memory_id: str) -> list[str]:
    return list(load_links().get(memory_id, []))


def set_links(memory_id: str, edge_ids: list[str]) -> None:
    """Replace the edge list for ``memory_id`` (an empty list removes the key)."""
    with file_lock(_lock_path()):
        links = load_links()
        ids = [e for e in edge_ids if e]
        if ids:
            links[memory_id] = ids
        else:
            links.pop(memory_id, None)
        atomic_write_text(_links_path(), json.dumps(links, ensure_ascii=False, indent=2))


def pop_links(memory_id: str) -> list[str]:
    """Remove and return the edge list for ``memory_id``."""
    with file_lock(_lock_path()):
        links = load_links()
        ids = links.pop(memory_id, [])
        if ids:
            atomic_write_text(_links_path(), json.dumps(links, ensure_ascii=False, indent=2))
        return ids


def append_history(entry: dict[str, Any], *, superseded_by: str | None, reason: str = "superseded") -> None:
    """Record a memory that stopped being current (never called for forget)."""
    row = {
        "id": entry.get("id"),
        "text": entry.get("text"),
        "kind": entry.get("kind"),
        "origin": entry.get("origin"),
        "created_at": entry.get("created_at"),
        "ended_at": time.time(),
        "reason": reason,
        "superseded_by": superseded_by,
    }
    with file_lock(_lock_path()):
        with _history_path().open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def load_history(limit: int = 200) -> list[dict[str, Any]]:
    """Most recent first."""
    path = _history_path()
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows[::-1][:limit]
