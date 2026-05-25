# Writing a skill

Skills are the tools Celestia can call during a conversation. They live under `skills/` and are wired into the agent through `skills/registry.py`.

## How tools work

When the LLM decides to call a tool, `agent.py` passes the call to `execute_tool()` in `registry.py`. That function routes by tool name, calls the right Python function, and returns a string result that gets appended to the conversation as a `tool` message.

```
user message
  └─ agent.py run_turn()
       └─ ollama.chat(tools=tool_schemas())
            └─ model returns tool_call { name, arguments }
                 └─ registry.py execute_tool(name, arguments)
                      └─ skills/<name>/tools.py → returns string
                           └─ result injected as {"role": "tool", ...}
```

---

## Skill structure

A skill is a folder under `skills/` with a `tools.py` file:

```
skills/
  my_skill/
    __init__.py   # empty is fine
    tools.py      # schemas + implementation
```

### tools.py skeleton

```python
from __future__ import annotations
from celestia_core import security

# 1. Define the JSON schemas (OpenAI function-call format)
MY_TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "my_tool",
            "description": "What this tool does, in one sentence.",
            "parameters": {
                "type": "object",
                "properties": {
                    "input": {
                        "type": "string",
                        "description": "What this parameter is for.",
                    },
                },
                "required": ["input"],
            },
        },
    }
]


# 2. Implement the function — always returns a string
def my_tool(input: str) -> str:
    # Do the thing
    return f"Done: {input}"
```

---

## Registering the skill

Open `skills/registry.py` and add your skill in two places:

**1. Import the schemas and function:**

```python
from skills.my_skill.tools import MY_TOOL_SCHEMAS, my_tool
```

**2. Add the schemas to `tool_schemas()`:**

```python
def tool_schemas(user_message: str = "") -> list:
    ...
    tools = list(pc) + list(FILE_TOOL_SCHEMAS) + list(CLIPBOARD_TOOL_SCHEMAS)
    tools += MY_TOOL_SCHEMAS   # add here
    ...
    return tools
```

**3. Add the dispatch case in `execute_tool()`:**

```python
if name == "my_tool":
    result = my_tool(arguments["input"])
    security.audit_tool(name, arguments, result, source=source)
    return result
```

---

## Security gating

Tools that do anything beyond reading safe data should be gated by mode.

**For PC-control-level tools** — call `security.gate_pc_tool()` before executing:

```python
blocked = security.gate_pc_tool(name, arguments)
if blocked:
    security.audit_tool(name, arguments, blocked, source=source)
    return blocked
```

`gate_pc_tool()` returns a `"Blocked: ..."` string if the mode or allowlist rejects the call, or `None` if it is allowed.

**For tools that are always safe** (read-only, no PC side-effects) — no gate needed, but still call `security.audit_tool()` for the audit log.

**For tools that should only run in scoped or armed** — check the mode explicitly:

```python
from celestia_core import security
if security.get_mode() == "safe":
    return "Blocked: this tool requires scoped or armed mode."
```

---

## Tool schema tips

- `name` must be unique across all skills — collisions silently shadow the earlier tool.
- `description` is what the LLM reads to decide when to call the tool. Be specific.
- Keep `required` tight — optional parameters reduce reliability.
- Return plain strings. The LLM reads your return value directly, so write it for human readability: `"Opened Notepad."` not `{"status": "ok"}`.
- Tool errors should also return strings: `"Error: file not found."` — never raise an exception out of a tool function; wrap in try/except.

---

## Controlling when schemas are offered

`tool_schemas(user_message)` receives the current user message, so you can hide a tool when it is unlikely to be needed:

```python
if any(t in msg for t in ("weather", "forecast", "temperature")):
    tools += WEATHER_TOOL_SCHEMAS
```

This reduces context token usage and lowers the chance of false tool calls.

---

## Audit logging

Every tool call should produce an audit log entry:

```python
security.audit_tool(name, arguments, result, source=source)
```

This writes one line to `logs/tool_audit.jsonl`. The shell shell's audit tail endpoint (`GET /audit/tail`) reads this file. Always include it — even for safe tools.

---

## Example: a minimal read-only skill

```python
# skills/sysinfo/tools.py
from __future__ import annotations
import platform
from celestia_core import security

SYSINFO_TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "get_os_info",
            "description": "Returns basic OS information: platform, version, machine type.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    }
]


def get_os_info() -> str:
    return (
        f"OS: {platform.system()} {platform.release()} "
        f"({platform.version()}) — {platform.machine()}"
    )
```

In `registry.py`:

```python
from skills.sysinfo.tools import SYSINFO_TOOL_SCHEMAS, get_os_info

# in tool_schemas():
tools += SYSINFO_TOOL_SCHEMAS

# in execute_tool():
if name == "get_os_info":
    result = get_os_info()
    security.audit_tool(name, arguments, result, source=source)
    return result
```

---

## Related files

| File | Purpose |
|------|---------|
| `skills/registry.py` | Central dispatch — import schemas + route calls here |
| `skills/pc_control/tools.py` | Reference for gated PC tools |
| `skills/files/tools.py` | Reference for workspace-scoped file tools |
| `skills/memory/store.py` | Memory CRUD helpers |
| `celestia_core/security.py` | `gate_pc_tool()`, `audit_tool()`, `get_mode()` |
| `docs/guide/security.md` | Mode rules and allowlist behaviour |
| `docs/reference/api.md` | Shell API — useful if your skill needs to interact with the frontend |
