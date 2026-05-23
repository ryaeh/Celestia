from __future__ import annotations

import json
from typing import Any

from celestia_core.config import get
from celestia_core import security
from skills.memory import store as memory
from skills.files.tools import FILE_TOOL_SCHEMAS, file_read
from skills.pc_control.tools import (
    MEMORY_TOOL_SCHEMAS,
    PC_TOOL_SCHEMAS,
    execute_pc,
)

_OPEN_TRIGGERS = (
    "open ",
    "launch ",
    "start ",
    "go to ",
    "browse ",
    "visit ",
    "http://",
    "https://",
)


def tool_schemas(user_message: str = "") -> list:
    from celestia_core.config import load_config

    load_config()
    msg = (user_message or "").lower()
    pc = list(PC_TOOL_SCHEMAS)
    if not any(t in msg for t in _OPEN_TRIGGERS):
        pc = [t for t in pc if t["function"]["name"] not in ("open_path", "open_url")]

    tools = list(pc) + list(FILE_TOOL_SCHEMAS)
    if get("memory.enabled", True):
        tools += MEMORY_TOOL_SCHEMAS
    return tools


def execute_tool(
    name: str,
    arguments: dict[str, Any],
    user_id: str,
    *,
    source: str = "cli",
) -> str:
    try:
        if name == "file_read":
            result = file_read(arguments["path"])
            security.audit_tool(name, arguments, result, source=source)
            return result

        if name in ("memory_search", "memory_add", "memory_list", "memory_delete"):
            if name == "memory_search":
                result = memory.search_json(arguments["query"], user_id)
            elif name == "memory_add":
                result = memory.add_json(arguments["content"], user_id)
            elif name == "memory_list":
                result = memory.format_list(user_id)
            elif name == "memory_delete":
                mid = (arguments.get("memory_id") or "").strip()
                match = (arguments.get("match_text") or "").strip()
                if mid:
                    result = memory.delete_by_id(mid)
                elif match:
                    result = memory.delete_matching(user_id, match)
                else:
                    result = "Provide memory_id or match_text"
            security.audit_tool(name, arguments, result, source=source)
            return result

        blocked = security.gate_pc_tool(name, arguments)
        if blocked:
            security.audit_tool(name, arguments, blocked, source=source)
            return blocked

        result = execute_pc(name, arguments)
        security.audit_tool(name, arguments, result, source=source)
        return result
    except Exception as e:
        result = f"Tool error ({name}): {e}"
        security.audit_tool(name, arguments, result, source=source)
        return result
