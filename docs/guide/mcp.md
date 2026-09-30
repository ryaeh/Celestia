# MCP servers (plug-in tools)

Celestia is an **MCP client**: any [Model Context Protocol](https://modelcontextprotocol.io)
server — filesystem, GitHub, calendar, Home Assistant, Spotify, time, fetch, … — can give
her new tools without writing a skill. Each server runs as a local stdio subprocess;
nothing is exposed to the network by Celestia.

## Setup

```powershell
.\venv\Scripts\pip install mcp          # already in requirements.txt
```

In `config.yaml`:

```yaml
mcp:
  enabled: true
  servers:
    time:
      command: uvx
      args: [mcp-server-time]
      min_mode: safe             # read-only, harmless → available in every mode
    github:
      command: npx
      args: ["-y", "@modelcontextprotocol/server-github"]
      env: {GITHUB_PERSONAL_ACCESS_TOKEN: "${GITHUB_TOKEN}"}   # value lives in .env
      tools: [search_repositories, get_file_contents]         # allowlist (optional)
      tool_modes: {get_file_contents: scoped}                 # per-tool override (optional)
```

Then `run_celestia.py --trust-config`, and check the connection:

```powershell
.\venv\Scripts\python.exe run_celestia.py --mcp     # status + every tool and the mode it needs
.\venv\Scripts\python.exe run_celestia.py --check   # includes an MCP line when enabled
```

The shell API exposes the same: `GET /mcp` (status) and `POST /mcp/reload` (reconnect after
editing config — no restart needed).

| Key | Default | Meaning |
|-----|---------|---------|
| `mcp.enabled` | `false` | Master switch — off means no subprocess, thread, or schema is ever created |
| `mcp.startup_wait_seconds` | `10` | The first turn waits this long for servers to connect (the shell connects at startup) |
| `mcp.call_timeout_seconds` | `30` | Per tool call |
| `mcp.max_result_chars` | `4000` | Longer output is truncated before it enters the context |
| `servers.<name>.command` / `args` / `cwd` | — | How to launch the server |
| `servers.<name>.env` | — | Extra env vars; `${VAR}` is expanded from the environment / `.env` |
| `servers.<name>.min_mode` | `armed` | Lowest security mode in which its tools are offered and may run |
| `servers.<name>.tool_modes` | — | Per-tool `min_mode` override |
| `servers.<name>.tools` / `deny_tools` | — | Allowlist / denylist of tool names |
| `servers.<name>.enabled` | `true` | Keep the entry but don't start it |

## How it's kept safe

MCP servers are third-party code, so they sit behind the same guard rails as PC control:

1. **Default `armed`.** A server's tools are only offered in armed mode unless you
   deliberately lower `min_mode` (or a single tool's `tool_modes`). Lower it only for
   servers you know are read-only.
2. **Offered *and* checked.** Tools below the current mode are left out of the model's tool
   list, and `security.gate_mcp_tool` re-checks at call time (the mode may have dropped
   mid-turn).
3. **Audited.** Every call — allowed or blocked — goes to `logs/tool_audit.jsonl`.
4. **Untrusted output.** Every MCP result is wrapped as `⟦UNTRUSTED DATA — source: MCP
   server '<name>'⟧`, so injected instructions in a web page / issue / email are data,
   not commands (see `celestia_core/untrusted.py`).
5. **Namespaced.** Tools appear as `mcp__<server>__<tool>`, so they can never shadow a
   built-in tool.

Server stderr goes to `logs/mcp/<server>.log`. A server that fails to start is shown as
`error` with the reason and retried at most once a minute.

**Small-model tip:** every offered tool costs prompt tokens on every turn, and a 7B model
picks worse from a long list. Use `tools:` allowlists to expose only what you use, and run
`python -m evals.toolcall_eval` before/after adding servers.
