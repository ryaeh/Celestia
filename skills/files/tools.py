"""Sandboxed file read (Phase 3b — write later)."""

from __future__ import annotations

from pathlib import Path

from celestia_core.config import get

FILE_TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "file_read",
            "description": (
                "Read a text file. In scoped mode only under workspace folders. "
                "Use for logs, config, code the user asked about."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Absolute or relative file path"},
                },
                "required": ["path"],
            },
        },
    },
]


def file_read(path: str) -> str:
    from celestia_core.scope import check_file_read

    err = check_file_read(path)
    if err:
        return err

    max_bytes = int(get("security.file_read_max_bytes", 262144))
    p = Path(path.strip().strip('"'))
    if not p.is_absolute():
        p = Path.cwd() / p
    try:
        p = p.resolve()
    except OSError:
        return f"Blocked: invalid path: {path}"

    size = p.stat().st_size
    if size > max_bytes:
        return (
            f"Blocked: file too large ({size} bytes, max {max_bytes}). "
            "Ask user to open a smaller file or use arm."
        )

    data = p.read_bytes()
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = data.decode("utf-8", errors="replace")
        except Exception:
            return "Blocked: binary file (not UTF-8 text)."

    if len(text) > 12000:
        text = text[:12000] + "\n… [truncated for chat]"
    return f"### {p.name}\n```\n{text}\n```"
