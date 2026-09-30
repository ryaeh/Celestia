"""MCP tools as LLM-callable tools — schemas filtered by security mode, and the
executor the registry routes ``mcp__*`` calls to.

Security (three layers, all required):

1. **Offer-time** — :func:`mcp_tool_schemas` only lists a tool when the current
   mode meets its ``min_mode`` (default ``armed``), so the model never sees tools
   it may not use.
2. **Run-time** — :func:`execute_mcp_tool` re-checks via
   ``security.gate_mcp_tool`` (mode may change between listing and calling),
   and the registry audits every call.
3. **Result** — MCP output is third-party content, so the registry wraps it as
   untrusted data (``untrusted.wrap_tool_result``) before it re-enters context.
"""

from __future__ import annotations

from typing import Any

from skills.mcp import manager

# Descriptions from third-party servers can be long; a 7B model pays for every
# token of every schema on every turn.
_DESC_MAX = 300


def _schema(server: str, tool: dict[str, Any]) -> dict[str, Any]:
    params = dict(tool["input_schema"] or {})
    params.pop("$schema", None)
    params.setdefault("type", "object")
    params.setdefault("properties", {})
    desc = " ".join(tool["description"].split())
    if len(desc) > _DESC_MAX:
        desc = desc[: _DESC_MAX - 1] + "…"
    return {
        "type": "function",
        "function": {
            "name": manager.qualify(server, tool["name"]),
            "description": f"[{server}] {desc}".strip(),
            "parameters": params,
        },
    }


def mcp_tool_schemas(mode: str) -> list[dict[str, Any]]:
    """Schemas for every connected MCP tool allowed in *mode*."""
    from celestia_core.security import mode_allows

    out = []
    for server, cfg, tool in manager.list_tools():
        if mode_allows(mode, manager.required_mode(cfg, tool["name"])):
            out.append(_schema(server, tool))
    return out


def is_mcp_tool(name: str) -> bool:
    return name.startswith(manager.PREFIX)


def execute_mcp_tool(name: str, arguments: dict[str, Any]) -> tuple[str, bool]:
    """Gate, then run. Returns ``(result_text, blocked)``."""
    from celestia_core import security

    hit = manager.resolve(name)
    if hit is None:
        return f"Unknown MCP tool: {name}", True
    server, tool = hit
    cfg = manager.server_config(server)
    if not manager.tool_allowed(cfg, tool):
        return f"Blocked: MCP tool '{tool}' is not allowed for server '{server}'.", True
    blocked = security.gate_mcp_tool(name, manager.required_mode(cfg, tool))
    if blocked:
        return blocked, True
    return manager.call_tool(server, tool, arguments), False
