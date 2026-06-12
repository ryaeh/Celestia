"""LLM-callable to-do tools.

These let Celestia read *and* organize the user's to-do list from chat
("add buy milk", "mark the report done", "what's left?"). They wrap
``skills.todos.store`` and return short human-readable strings, like the other
skills. They are not PC-touching, so they need no security gate (the registry
still audit-logs every call).
"""

from __future__ import annotations

from typing import Any

from skills.todos import store

TODO_TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "todo_add",
            "description": "Add an item to the user's to-do list.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "What to do"},
                    "priority": {
                        "type": "string",
                        "enum": ["low", "normal", "high"],
                        "description": "Priority (default normal)",
                    },
                    "due": {
                        "type": "string",
                        "description": "Optional due date, e.g. 2026-06-20 or 'Friday'",
                    },
                    "notes": {"type": "string", "description": "Optional extra detail"},
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "todo_list",
            "description": "List the user's to-do items (to discuss or summarize them).",
            "parameters": {
                "type": "object",
                "properties": {
                    "include_done": {
                        "type": "boolean",
                        "description": "Include completed items (default false)",
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "todo_complete",
            "description": "Mark a to-do as done (or not done). Identify it by id or matching text.",
            "parameters": {
                "type": "object",
                "properties": {
                    "todo_id": {"type": "string", "description": "Item id (preferred)"},
                    "match_text": {
                        "type": "string",
                        "description": "Text to match if id unknown",
                    },
                    "done": {
                        "type": "boolean",
                        "description": "true to complete (default), false to reopen",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "todo_update",
            "description": "Edit a to-do's text, priority, due date, or notes. Identify by id or matching text.",
            "parameters": {
                "type": "object",
                "properties": {
                    "todo_id": {"type": "string", "description": "Item id (preferred)"},
                    "match_text": {
                        "type": "string",
                        "description": "Text to match if id unknown",
                    },
                    "text": {"type": "string", "description": "New text"},
                    "priority": {"type": "string", "enum": ["low", "normal", "high"]},
                    "due": {"type": "string", "description": "New due date (empty string clears it)"},
                    "notes": {"type": "string", "description": "New notes"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "todo_remove",
            "description": "Delete a to-do entirely. Identify it by id or matching text.",
            "parameters": {
                "type": "object",
                "properties": {
                    "todo_id": {"type": "string", "description": "Item id (preferred)"},
                    "match_text": {
                        "type": "string",
                        "description": "Text to match if id unknown",
                    },
                },
            },
        },
    },
]


def _fmt(item: dict[str, Any]) -> str:
    box = "[x]" if item.get("done") else "[ ]"
    prio = item.get("priority", "normal")
    tag = "" if prio == "normal" else f" ({prio})"
    due = f" — due {item['due']}" if item.get("due") else ""
    return f"{box} {item.get('text', '')}{tag}{due}  ·#{str(item.get('id', ''))[:8]}"


def _resolve(
    uid: str, todo_id: str, match_text: str
) -> tuple[dict[str, Any] | None, str | None]:
    """Find one to-do by id or text. Returns (item, error_message)."""
    todo_id = (todo_id or "").strip()
    match_text = (match_text or "").strip()
    if todo_id:
        item = store.get_todo(todo_id, uid)
        return (item, None) if item else (None, f"No to-do with id {todo_id}.")
    if match_text:
        low = match_text.lower()
        matches = [t for t in store.list_todos(uid) if low in t.get("text", "").lower()]
        if not matches:
            return None, f"No to-do matching {match_text!r}."
        if len(matches) > 1:
            listing = "; ".join(_fmt(m) for m in matches[:5])
            return None, f"Ambiguous — {len(matches)} match {match_text!r}: {listing}"
        return matches[0], None
    return None, "Provide todo_id or match_text."


def todo_add(
    text: str,
    uid: str,
    *,
    priority: str = "normal",
    due: str = "",
    notes: str = "",
) -> str:
    try:
        item = store.add_todo(text, uid, priority=priority, due=due or None, notes=notes)
    except ValueError as e:
        return f"Could not add to-do: {e}"
    return f"Added to-do: {_fmt(item)}"


def todo_list(uid: str, *, include_done: bool = False) -> str:
    items = store.list_todos(uid, include_done=include_done)
    if not items:
        return "Your to-do list is empty."
    open_n = sum(1 for t in items if not t.get("done"))
    lines = [_fmt(t) for t in items]
    header = f"To-do list ({open_n} open):"
    return header + "\n" + "\n".join(lines)


def todo_complete(
    uid: str, *, todo_id: str = "", match_text: str = "", done: bool = True
) -> str:
    item, err = _resolve(uid, todo_id, match_text)
    if err:
        return err
    updated = store.update_todo(item["id"], done=done, user_id=uid)
    if updated is None:
        return "To-do not found."
    verb = "Completed" if done else "Reopened"
    return f"{verb}: {_fmt(updated)}"


def todo_update(
    uid: str,
    *,
    todo_id: str = "",
    match_text: str = "",
    text: str = "",
    priority: str = "",
    due: str | None = None,
    notes: str | None = None,
) -> str:
    item, err = _resolve(uid, todo_id, match_text)
    if err:
        return err
    updated = store.update_todo(
        item["id"],
        text=text or None,
        priority=priority or None,
        due=due,
        notes=notes,
        user_id=uid,
    )
    if updated is None:
        return "To-do not found."
    return f"Updated: {_fmt(updated)}"


def todo_remove(uid: str, *, todo_id: str = "", match_text: str = "") -> str:
    item, err = _resolve(uid, todo_id, match_text)
    if err:
        return err
    label = _fmt(item)
    return "Removed: " + label if store.delete_todo(item["id"], uid) else "To-do not found."
