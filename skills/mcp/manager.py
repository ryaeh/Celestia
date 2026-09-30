"""MCP client manager — connects to configured MCP servers and exposes their tools.

Each server in ``mcp.servers`` (config.yaml) is launched as a stdio subprocess and
held open by one long-lived task on a private asyncio loop running in a daemon
thread. The sync agent loop talks to it through :func:`list_tools` /
:func:`call_tool`, which hop onto that loop with ``run_coroutine_threadsafe``.

Nothing here decides *whether* a tool may run — that is ``security.gate_mcp_tool``
(called from ``registry.execute_tool``) and the per-mode filter in
``skills.mcp.tools``. The ``mcp`` SDK is imported lazily, so Celestia starts (and
tests run) without it; with ``mcp.enabled: false`` (the default) no thread,
loop, or subprocess is ever created.

Works with both the 1.x and 2.x ``mcp`` SDKs (field names differ in case).
"""

from __future__ import annotations

import asyncio
import atexit
import os
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from celestia_core.config import get

# Qualified tool names look like ``mcp__<server>__<tool>`` — namespaced so an MCP
# tool can never shadow a built-in, and so the registry can route by prefix.
PREFIX = "mcp__"
_SEP = "__"
_NAME_MAX = 64  # OpenAI-style function-name limit most models were trained on
_RETRY_AFTER_SECONDS = 60.0

_VALID_MODES = ("safe", "scoped", "armed")


@dataclass
class ServerState:
    name: str
    cfg: dict[str, Any]
    status: str = "stopped"  # stopped | starting | ready | error
    error: str = ""
    tools: list[dict[str, Any]] = field(default_factory=list)  # raw: name, description, input_schema, read_only
    session: Any = None
    ready: threading.Event = field(default_factory=threading.Event)
    stop: asyncio.Event | None = None
    last_attempt: float = 0.0


_lock = threading.Lock()
_loop: asyncio.AbstractEventLoop | None = None
_thread: threading.Thread | None = None
_servers: dict[str, ServerState] = {}
_qualified: dict[str, tuple[str, str]] = {}  # qualified name -> (server, tool)
_first_wait_done = False


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


def enabled() -> bool:
    return bool(get("mcp.enabled", False))


def _safe_part(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", s).strip("_") or "x"


def qualify(server: str, tool: str) -> str:
    """``mcp__<server>__<tool>``, sanitized and capped at 64 chars."""
    name = f"{PREFIX}{_safe_part(server)}{_SEP}{_safe_part(tool)}"
    return name[:_NAME_MAX]


def server_configs() -> dict[str, dict[str, Any]]:
    """Enabled server configs from ``mcp.servers`` (a name → settings mapping)."""
    raw = get("mcp.servers", {}) or {}
    if not isinstance(raw, dict):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for name, cfg in raw.items():
        if not isinstance(cfg, dict) or not cfg.get("command"):
            continue
        if cfg.get("enabled", True) is False:
            continue
        out[str(name)] = cfg
    return out


def required_mode(server_cfg: dict[str, Any], tool: str) -> str:
    """Lowest security mode in which *tool* may be offered/run.

    Per-tool ``tool_modes`` beats the server's ``min_mode``; the default is
    ``armed`` — an MCP server is arbitrary third-party code, so it is opt-down,
    never opt-up.
    """
    per_tool = server_cfg.get("tool_modes") or {}
    mode = str(per_tool.get(tool) or server_cfg.get("min_mode") or "armed").lower()
    return mode if mode in _VALID_MODES else "armed"


def tool_allowed(server_cfg: dict[str, Any], tool: str) -> bool:
    """``tools`` is an optional allowlist, ``deny_tools`` a denylist."""
    allow = server_cfg.get("tools")
    if allow and tool not in allow:
        return False
    return tool not in (server_cfg.get("deny_tools") or [])


_ENV_REF = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def _expand_env(env: dict[str, Any] | None) -> dict[str, str] | None:
    """Expand ``${VAR}`` from the process environment (``.env`` is loaded at
    startup), so secrets stay in ``.env`` and never in config.yaml."""
    if not env:
        return None
    merged = dict(os.environ)
    for k, v in env.items():
        merged[str(k)] = _ENV_REF.sub(lambda m: os.environ.get(m.group(1), ""), str(v))
    return merged


# ---------------------------------------------------------------------------
# Background loop + per-server connection task
# ---------------------------------------------------------------------------


def _ensure_loop() -> asyncio.AbstractEventLoop:
    global _loop, _thread
    if _loop is not None and _thread is not None and _thread.is_alive():
        return _loop
    loop = asyncio.new_event_loop()
    t = threading.Thread(target=loop.run_forever, name="celestia-mcp", daemon=True)
    t.start()
    _loop, _thread = loop, t
    atexit.register(shutdown)
    return loop


def _field(obj: Any, *names: str) -> Any:
    for n in names:
        v = obj.get(n) if isinstance(obj, dict) else getattr(obj, n, None)
        if v is not None:
            return v
    return None


def _tool_record(tool: Any) -> dict[str, Any]:
    ann = _field(tool, "annotations")
    read_only = bool(_field(ann, "read_only_hint", "readOnlyHint")) if ann is not None else False
    schema = _field(tool, "input_schema", "inputSchema") or {"type": "object", "properties": {}}
    if hasattr(schema, "model_dump"):
        schema = schema.model_dump(exclude_none=True)
    return {
        "name": str(_field(tool, "name") or ""),
        "description": str(_field(tool, "description") or ""),
        "input_schema": dict(schema),
        "read_only": read_only,
    }


async def _serve(state: ServerState) -> None:
    """Own one server's stdio connection for its whole lifetime (anyio requires
    the context managers to be entered and exited in the same task)."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    cfg = state.cfg
    params = StdioServerParameters(
        command=str(cfg["command"]),
        args=[str(a) for a in (cfg.get("args") or [])],
        env=_expand_env(cfg.get("env")),
        cwd=cfg.get("cwd") or None,
    )
    state.stop = asyncio.Event()
    errlog = _open_errlog(state.name)
    try:
        async with stdio_client(params, errlog=errlog) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools: list[dict[str, Any]] = []
                cursor = None
                while True:
                    if cursor:
                        from mcp.types import PaginatedRequestParams

                        page = await session.list_tools(params=PaginatedRequestParams(cursor=cursor))
                    else:
                        page = await session.list_tools()
                    tools += [_tool_record(t) for t in (_field(page, "tools") or [])]
                    cursor = _field(page, "next_cursor", "nextCursor")
                    if not cursor:
                        break
                state.tools = [t for t in tools if t["name"]]
                state.session = session
                state.status = "ready"
                state.error = ""
                state.ready.set()
                await state.stop.wait()
    except BaseException as e:  # noqa: BLE001 — surface any launch/protocol failure as status
        if not isinstance(e, asyncio.CancelledError):
            state.status = "error"
            state.error = _describe(e)
    finally:
        errlog.close()
        state.session = None
        if state.status == "ready":
            state.status = "stopped"
        state.ready.set()


def _open_errlog(server: str):
    """Server stderr goes to logs/mcp/<server>.log, not Celestia's console."""
    from celestia_core.config import ROOT

    path = ROOT / "logs" / "mcp" / f"{_safe_part(server)}.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    return open(path, "a", encoding="utf-8", errors="replace")


def _describe(e: BaseException) -> str:
    # anyio wraps failures in ExceptionGroups; show the first real cause.
    inner = getattr(e, "exceptions", None)
    if inner:
        return _describe(inner[0])
    return f"{type(e).__name__}: {e}"[:300]


def _start_server(name: str, cfg: dict[str, Any]) -> None:
    loop = _ensure_loop()
    state = ServerState(name=name, cfg=cfg, status="starting", last_attempt=time.monotonic())
    _servers[name] = state
    asyncio.run_coroutine_threadsafe(_serve(state), loop)


def ensure_started() -> None:
    """Start any configured server that isn't running yet (non-blocking).

    Failed servers are retried at most once a minute, so a broken server
    doesn't respawn a subprocess on every chat turn.
    """
    if not enabled():
        return
    try:
        import mcp  # noqa: F401
    except ImportError:
        return
    now = time.monotonic()
    with _lock:
        for name, cfg in server_configs().items():
            st = _servers.get(name)
            if st is None:
                _start_server(name, cfg)
            elif st.status in ("error", "stopped") and now - st.last_attempt > _RETRY_AFTER_SECONDS:
                _start_server(name, cfg)


def wait_ready(timeout: float) -> None:
    """Block until every starting server is ready/failed, or *timeout* passes."""
    deadline = time.monotonic() + max(0.0, timeout)
    for st in list(_servers.values()):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        st.ready.wait(remaining)


def list_tools() -> list[tuple[str, dict[str, Any], dict[str, Any]]]:
    """``(server_name, server_cfg, tool_record)`` for every tool on a ready
    server that passes the server's allow/deny lists. Starts servers lazily;
    the first call waits up to ``mcp.startup_wait_seconds`` for them."""
    global _first_wait_done
    if not enabled():
        return []
    ensure_started()
    if not _first_wait_done:
        wait_ready(float(get("mcp.startup_wait_seconds", 10)))
        _first_wait_done = True

    out: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
    qualified: dict[str, tuple[str, str]] = {}
    for name, st in list(_servers.items()):
        if st.status != "ready":
            continue
        for tool in st.tools:
            if not tool_allowed(st.cfg, tool["name"]):
                continue
            qualified[qualify(name, tool["name"])] = (name, tool["name"])
            out.append((name, st.cfg, tool))
    _qualified.update(qualified)
    return out


def resolve(qualified_name: str) -> tuple[str, str] | None:
    """Qualified name → ``(server, tool)``, or None if unknown."""
    hit = _qualified.get(qualified_name)
    if hit is None and enabled():
        list_tools()  # refresh the map (e.g. a server came up since last turn)
        hit = _qualified.get(qualified_name)
    return hit


def server_config(name: str) -> dict[str, Any]:
    st = _servers.get(name)
    return st.cfg if st else server_configs().get(name, {})


def _result_text(result: Any) -> str:
    parts: list[str] = []
    for block in _field(result, "content") or []:
        kind = _field(block, "type")
        if kind == "text":
            parts.append(str(_field(block, "text") or ""))
        elif kind == "resource":
            res = _field(block, "resource")
            parts.append(str(_field(res, "text") or f"[resource {_field(res, 'uri')}]"))
        else:
            parts.append(f"[{kind} content omitted]")
    structured = _field(result, "structured_content", "structuredContent")
    if not parts and structured is not None:
        import json

        parts.append(json.dumps(structured, ensure_ascii=False))
    text = "\n".join(p for p in parts if p).strip() or "(no output)"
    if _field(result, "is_error", "isError"):
        text = f"MCP tool error: {text}"
    return text


def call_tool(server: str, tool: str, arguments: dict[str, Any]) -> str:
    """Run one tool call on *server* and return its text (truncated)."""
    st = _servers.get(server)
    if st is None or st.status != "ready" or st.session is None or _loop is None:
        reason = f" ({st.error})" if st and st.error else ""
        return f"MCP server '{server}' is not connected{reason}."
    timeout = float(get("mcp.call_timeout_seconds", 30))
    fut = asyncio.run_coroutine_threadsafe(st.session.call_tool(tool, arguments or {}), _loop)
    try:
        result = fut.result(timeout=timeout)
    except TimeoutError:
        fut.cancel()
        return f"MCP tool '{tool}' on '{server}' timed out after {timeout:.0f}s."
    text = _result_text(result)
    cap = int(get("mcp.max_result_chars", 4000))
    if len(text) > cap:
        text = text[:cap] + f"\n… [truncated, {len(text) - cap} more chars]"
    return text


def status() -> list[dict[str, Any]]:
    """Per-server status for the shell API / CLI (configured servers included
    even when not started)."""
    rows = []
    cfgs = server_configs() if enabled() else {}
    for name in sorted(set(cfgs) | set(_servers)):
        st = _servers.get(name)
        cfg = cfgs.get(name) or (st.cfg if st else {})
        tools = []
        for t in (st.tools if st else []):
            tools.append(
                {
                    "name": t["name"],
                    "qualified": qualify(name, t["name"]),
                    "min_mode": required_mode(cfg, t["name"]),
                    "allowed": tool_allowed(cfg, t["name"]),
                    "read_only_hint": t["read_only"],
                }
            )
        rows.append(
            {
                "name": name,
                "status": st.status if st else "stopped",
                "error": st.error if st else "",
                "command": " ".join([str(cfg.get("command", ""))] + [str(a) for a in cfg.get("args") or []]),
                "min_mode": required_mode(cfg, ""),
                "tools": tools,
            }
        )
    return rows


def shutdown() -> None:
    """Close every server connection (subprocesses exit with their stdio)."""
    global _first_wait_done
    loop = _loop
    for st in list(_servers.values()):
        if st.stop is not None and loop is not None and loop.is_running():
            loop.call_soon_threadsafe(st.stop.set)
    _servers.clear()
    _qualified.clear()
    _first_wait_done = False


def reload() -> list[dict[str, Any]]:
    """Drop all connections and reconnect from current config."""
    shutdown()
    time.sleep(0.2)  # let stop events propagate before respawning
    if enabled():
        ensure_started()
        wait_ready(float(get("mcp.startup_wait_seconds", 10)))
        list_tools()
    return status()
