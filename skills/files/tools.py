"""Sandboxed file read/write (Phase 3b)."""

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
    {
        "type": "function",
        "function": {
            "name": "file_write",
            "description": (
                "Write UTF-8 text to a file. Scoped: workspace folders only. "
                "Set confirm_overwrite=true if replacing an existing file."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path to write"},
                    "content": {"type": "string", "description": "Full file content (UTF-8 text)"},
                    "confirm_overwrite": {
                        "type": "boolean",
                        "description": "Required true when overwriting an existing file",
                    },
                },
                "required": ["path", "content"],
            },
        },
    },
]


def _resolve_path(path: str) -> Path:
    p = Path(path.strip().strip('"'))
    if not p.is_absolute():
        p = Path.cwd() / p
    return p.resolve()


def file_read(path: str) -> str:
    from celestia_core.scope import check_file_read

    err = check_file_read(path)
    if err:
        return err

    max_bytes = int(get("security.file_read_max_bytes", 262144))
    p = _resolve_path(path)

    if not p.is_file():
        return f"Blocked: not a file: {p}"

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


def file_write(path: str, content: str, *, confirm_overwrite: bool = False) -> str:
    from celestia_core.scope import check_file_write

    err = check_file_write(path)
    if err:
        return err

    p = _resolve_path(path)
    max_bytes = int(get("security.file_write_max_bytes", 524288))
    encoded = content.encode("utf-8")
    if len(encoded) > max_bytes:
        return f"Blocked: content too large ({len(encoded)} bytes, max {max_bytes})."

    existed = p.is_file()
    if existed and get("pc_control.require_confirm_destructive", True) and not confirm_overwrite:
        return (
            f"Blocked: {p} already exists. Ask the user to confirm overwrite, "
            "then call file_write again with confirm_overwrite=true."
        )

    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8", newline="\n")
    action = "Updated" if existed else "Wrote"
    return f"{action}: {p} ({len(encoded)} bytes)"
