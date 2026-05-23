"""Clipboard read/write (Phase 3c) — Windows via tkinter."""

from __future__ import annotations

CLIPBOARD_TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "clipboard_read",
            "description": "Read plain text from the system clipboard.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "clipboard_write",
            "description": (
                "Write plain text to the clipboard. In scoped mode may require "
                "confirm_write=true when replacing non-empty clipboard."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text to copy"},
                    "confirm_write": {
                        "type": "boolean",
                        "description": "Set true after user confirms replacing clipboard",
                    },
                },
                "required": ["text"],
            },
        },
    },
]


def _tk_clipboard() -> tuple[object, object]:
    import tkinter as tk

    root = tk.Tk()
    root.withdraw()
    return root, root


def clipboard_read() -> str:
    root, _ = _tk_clipboard()
    try:
        text = root.clipboard_get()
    except Exception:
        text = ""
    finally:
        root.destroy()
    if not text:
        return "(clipboard empty or non-text)"
    if len(text) > 8000:
        return text[:8000] + "\n… [truncated]"
    return text


def clipboard_write(text: str, *, confirm_write: bool = False) -> str:
    from celestia_core.config import get
    from celestia_core.security import get_mode

    if get_mode() == "safe":
        return "Blocked: clipboard_write requires scoped or armed mode."

    current = ""
    try:
        current = clipboard_read()
        if current.startswith("(clipboard"):
            current = ""
    except Exception:
        pass

    if (
        get_mode() == "scoped"
        and get("pc_control.require_confirm_destructive", True)
        and current.strip()
        and not confirm_write
    ):
        return (
            "Blocked: clipboard has content. Ask user to confirm, then call "
            "clipboard_write with confirm_write=true."
        )

    root, _ = _tk_clipboard()
    try:
        root.clipboard_clear()
        root.clipboard_append(text)
        root.update()
    finally:
        root.destroy()
    return f"Copied {len(text)} characters to clipboard."
