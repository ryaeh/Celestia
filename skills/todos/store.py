"""To-do list store — a cross-process JSON list under ``data/``.

A to-do is structured, mutable, user-owned data, so it lives in its own store
rather than in memory/Chroma. Reads and writes go through the shared
``file_lock`` + ``atomic_write_text`` primitives so the tray, shell API, and CLI
can touch the list concurrently without corrupting it (same discipline as
``skills/memory/activity_feed.py`` and ``skills/vision/history.py``).

Item shape::

    {
        "id": "<uuid4 hex>",
        "user_id": "atlas_user",
        "text": "Buy milk",
        "done": false,
        "priority": "normal",       # low | normal | high
        "due": "2026-06-20" | null, # free-form date string, validated loosely
        "notes": "",
        "created_at": "2026-06-12T08:00:00Z",
        "completed_at": null,
    }
"""

from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from celestia_core.config import ROOT, get
from celestia_core.file_utils import atomic_write_text, file_lock

try:  # orjson is already a dep elsewhere; fall back to stdlib for tests.
    import json
except Exception:  # pragma: no cover
    json = None  # type: ignore

PRIORITIES = ("low", "normal", "high")
_PRIORITY_RANK = {"high": 0, "normal": 1, "low": 2}

# In-process lock; the file_lock handles the cross-process case.
_lock = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _todos_path() -> Path:
    rel = get("todos.data_path", "data/todos.json")
    path = Path(rel) if Path(rel).is_absolute() else ROOT / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _load() -> list[dict[str, Any]]:
    path = _todos_path()
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    return data if isinstance(data, list) else []


def _save(todos: list[dict[str, Any]]) -> None:
    path = _todos_path()
    atomic_write_text(path, json.dumps(todos, ensure_ascii=False, indent=2))


def _norm_priority(priority: str | None) -> str:
    p = (priority or "normal").strip().lower()
    return p if p in PRIORITIES else "normal"


def _sort_key(t: dict[str, Any]) -> tuple:
    # Open before done; then high→low priority; then nearest due; then oldest.
    due = t.get("due") or "9999-99-99"
    return (
        bool(t.get("done")),
        _PRIORITY_RANK.get(t.get("priority", "normal"), 1),
        due,
        t.get("created_at", ""),
    )


def add_todo(
    text: str,
    user_id: str,
    *,
    priority: str = "normal",
    due: str | None = None,
    notes: str = "",
) -> dict[str, Any]:
    """Create a to-do and return it."""
    text = (text or "").strip()
    if not text:
        raise ValueError("text required")
    item = {
        "id": uuid.uuid4().hex,
        "user_id": user_id,
        "text": text,
        "done": False,
        "priority": _norm_priority(priority),
        "due": (due or "").strip() or None,
        "notes": (notes or "").strip(),
        "created_at": _now(),
        "completed_at": None,
    }
    with _lock, file_lock(_todos_path().parent / ".todos.lock"):
        todos = _load()
        todos.append(item)
        _save(todos)
    return item


def list_todos(user_id: str, *, include_done: bool = True) -> list[dict[str, Any]]:
    """Return this user's to-dos, sorted (open + high priority first)."""
    todos = [t for t in _load() if t.get("user_id") == user_id]
    if not include_done:
        todos = [t for t in todos if not t.get("done")]
    todos.sort(key=_sort_key)
    return todos


def get_todo(todo_id: str, user_id: str | None = None) -> dict[str, Any] | None:
    for t in _load():
        if t.get("id") == todo_id and (user_id is None or t.get("user_id") == user_id):
            return t
    return None


def update_todo(
    todo_id: str,
    *,
    text: str | None = None,
    done: bool | None = None,
    priority: str | None = None,
    due: str | None = None,
    notes: str | None = None,
    user_id: str | None = None,
) -> dict[str, Any] | None:
    """Patch a to-do in place. Returns the updated item, or None if not found."""
    with _lock, file_lock(_todos_path().parent / ".todos.lock"):
        todos = _load()
        target: dict[str, Any] | None = None
        for t in todos:
            if t.get("id") == todo_id and (user_id is None or t.get("user_id") == user_id):
                target = t
                break
        if target is None:
            return None
        if text is not None:
            stripped = text.strip()
            if stripped:
                target["text"] = stripped
        if priority is not None:
            target["priority"] = _norm_priority(priority)
        if due is not None:
            target["due"] = due.strip() or None
        if notes is not None:
            target["notes"] = notes.strip()
        if done is not None:
            target["done"] = bool(done)
            target["completed_at"] = _now() if done else None
        _save(todos)
        return dict(target)


def delete_todo(todo_id: str, user_id: str | None = None) -> bool:
    with _lock, file_lock(_todos_path().parent / ".todos.lock"):
        todos = _load()
        kept = [
            t
            for t in todos
            if not (
                t.get("id") == todo_id
                and (user_id is None or t.get("user_id") == user_id)
            )
        ]
        if len(kept) == len(todos):
            return False
        _save(kept)
        return True


def clear_done(user_id: str) -> int:
    """Remove all completed to-dos for a user. Returns how many were removed."""
    with _lock, file_lock(_todos_path().parent / ".todos.lock"):
        todos = _load()
        kept = [t for t in todos if not (t.get("user_id") == user_id and t.get("done"))]
        removed = len(todos) - len(kept)
        if removed:
            _save(kept)
        return removed
