from __future__ import annotations

from typing import Any, Callable

from celestia_core.config import get
from celestia_core import security
from skills.memory import store as memory
from skills.clipboard.tools import CLIPBOARD_TOOL_SCHEMAS, clipboard_read, clipboard_write
from skills.files.tools import FILE_TOOL_SCHEMAS, file_read, file_write
from skills.pc_control.tools import (
    MEMORY_TOOL_SCHEMAS,
    PC_TOOL_SCHEMAS,
    execute_pc,
)
from skills.web.tools import WEB_TOOL_SCHEMAS, fetch_page, web_search
from skills.briefing.tools import BRIEFING_TOOL_SCHEMA, morning_briefing
from skills.todos.tools import (
    TODO_TOOL_SCHEMAS,
    todo_add,
    todo_complete,
    todo_list,
    todo_remove,
    todo_update,
)

# Handler type: (arguments, user_id) -> result string
_Handler = Callable[[dict[str, Any], str], str]


def _h_file_read(args: dict[str, Any], uid: str) -> str:
    return file_read(args["path"])


def _h_file_write(args: dict[str, Any], uid: str) -> str:
    return file_write(
        args["path"],
        args.get("content", ""),
        confirm_overwrite=bool(args.get("confirm_overwrite")),
    )


def _h_clipboard_read(args: dict[str, Any], uid: str) -> str:
    return clipboard_read()


def _h_clipboard_write(args: dict[str, Any], uid: str) -> str:
    return clipboard_write(
        args.get("text", ""),
        confirm_write=bool(args.get("confirm_write")),
    )


def _h_memory_edit(args: dict[str, Any], uid: str) -> str:
    return memory.edit_json(args["memory_id"], args["new_text"], uid)


def _h_memory_search(args: dict[str, Any], uid: str) -> str:
    return memory.search_json(args["query"], uid)


def _h_memory_add(args: dict[str, Any], uid: str) -> str:
    return memory.add_json(args["content"], uid, kind=str(args.get("kind") or "fact"))


def _h_memory_list(args: dict[str, Any], uid: str) -> str:
    return memory.format_list(uid)


def _h_memory_delete(args: dict[str, Any], uid: str) -> str:
    mid = (args.get("memory_id") or "").strip()
    match_text = (args.get("match_text") or "").strip()
    if mid:
        return memory.delete_by_id(mid)
    if match_text:
        return memory.delete_matching(uid, match_text)
    return "Provide memory_id or match_text"


def _h_web_search(args: dict[str, Any], uid: str) -> str:
    return web_search(args["query"], num_results=int(args.get("num_results", 5)))


def _h_fetch_page(args: dict[str, Any], uid: str) -> str:
    return fetch_page(args["url"], max_chars=int(args.get("max_chars", 3000)))


def _h_morning_briefing(args: dict[str, Any], uid: str) -> str:
    return morning_briefing(city=args.get("city", ""))


def _h_todo_add(args: dict[str, Any], uid: str) -> str:
    return todo_add(
        args.get("text", ""),
        uid,
        priority=str(args.get("priority") or "normal"),
        due=str(args.get("due") or ""),
        notes=str(args.get("notes") or ""),
    )


def _h_todo_list(args: dict[str, Any], uid: str) -> str:
    return todo_list(uid, include_done=bool(args.get("include_done")))


def _h_todo_complete(args: dict[str, Any], uid: str) -> str:
    done = args.get("done")
    return todo_complete(
        uid,
        todo_id=str(args.get("todo_id") or ""),
        match_text=str(args.get("match_text") or ""),
        done=True if done is None else bool(done),
    )


def _h_todo_update(args: dict[str, Any], uid: str) -> str:
    return todo_update(
        uid,
        todo_id=str(args.get("todo_id") or ""),
        match_text=str(args.get("match_text") or ""),
        text=str(args.get("text") or ""),
        priority=str(args.get("priority") or ""),
        due=args.get("due"),
        notes=args.get("notes"),
    )


def _h_todo_remove(args: dict[str, Any], uid: str) -> str:
    return todo_remove(
        uid,
        todo_id=str(args.get("todo_id") or ""),
        match_text=str(args.get("match_text") or ""),
    )


_TOOL_DISPATCH: dict[str, _Handler] = {
    "file_read": _h_file_read,
    "file_write": _h_file_write,
    "clipboard_read": _h_clipboard_read,
    "clipboard_write": _h_clipboard_write,
    "memory_edit": _h_memory_edit,
    "memory_search": _h_memory_search,
    "memory_add": _h_memory_add,
    "memory_list": _h_memory_list,
    "memory_delete": _h_memory_delete,
    "web_search": _h_web_search,
    "fetch_page": _h_fetch_page,
    "morning_briefing": _h_morning_briefing,
    "todo_add": _h_todo_add,
    "todo_list": _h_todo_list,
    "todo_complete": _h_todo_complete,
    "todo_update": _h_todo_update,
    "todo_remove": _h_todo_remove,
}


def tool_schemas() -> list:
    from celestia_core.config import load_config

    load_config()
    mode = security.get_mode()

    if mode == "safe":
        pc = [
            t
            for t in PC_TOOL_SCHEMAS
            if t["function"]["name"] in security.PC_TOOLS_ALWAYS_OK
        ]
        tools = list(pc)
        if get("memory.enabled", True):
            tools += MEMORY_TOOL_SCHEMAS
        # Web search and briefing are read-only — safe in all modes.
        if get("skills.web.enabled", True):
            tools += WEB_TOOL_SCHEMAS
        tools += BRIEFING_TOOL_SCHEMA
        # To-dos are user-owned data, not PC actions — safe in all modes.
        if get("todos.enabled", True):
            tools += TODO_TOOL_SCHEMAS
        return tools

    tools = list(PC_TOOL_SCHEMAS) + list(FILE_TOOL_SCHEMAS) + list(CLIPBOARD_TOOL_SCHEMAS)
    if get("memory.enabled", True):
        tools += MEMORY_TOOL_SCHEMAS
    if get("skills.web.enabled", True):
        tools += WEB_TOOL_SCHEMAS
    tools += BRIEFING_TOOL_SCHEMA
    if get("todos.enabled", True):
        tools += TODO_TOOL_SCHEMAS
    return tools


def execute_tool(
    name: str,
    arguments: dict[str, Any],
    user_id: str,
    *,
    source: str = "cli",
) -> str:
    try:
        if name in _TOOL_DISPATCH:
            result = _TOOL_DISPATCH[name](arguments, user_id)
        else:
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
