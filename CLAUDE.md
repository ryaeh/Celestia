# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

Celestia is a local Windows AI companion — chat, memory, voice, screen reading, and PC control. It runs entirely on-device via Ollama (no cloud LLM). The main entry point is `run_celestia.py`.

Required service: **Ollama** must be running for chat and memory (`ollama serve`). If it isn't, the shell asks (start / run without / quit) and terminal modes prompt — see the Ollama launch gate pattern below; the pytest suite never needs it.

## Commands

```powershell
# Run tests (no Ollama needed — all heavy deps are mocked)
pip install -r requirements-dev.txt
pytest tests/ -v

# Run a single test file
pytest tests/test_security.py -v

# Run a single test by name
pytest tests/test_agent.py::test_run_turn_reply_matches_mock -v

# Syntax-check a file without running it
python -m py_compile celestia_core/shell_chat.py

# Gate A eval — score graph extraction against the hand-labeled gold set (needs Ollama)
.\venv\Scripts\python.exe -m evals.extraction_eval --model qwen2.5:7b

# Gate A eval — score tool-calling (right tool / no tool / red flags); comma-separate models to compare
.\venv\Scripts\python.exe -m evals.toolcall_eval --model llama3.2:3b,qwen2.5:7b --out-dir evals/results

# Start interactive chat
.\venv\Scripts\python.exe run_celestia.py -i

# Preflight check (verifies Ollama, memory, voice)
.\venv\Scripts\python.exe run_celestia.py --check

# Start desktop shell (Tauri + Python API)
.\venv\Scripts\python.exe run_celestia.py --shell

# Dev shell (two terminals: API server + hot-reload frontend)
.\venv\Scripts\python.exe run_celestia.py --shell-server
cd shell && npm run tauri dev

# After editing config.yaml or security.policy.yaml
.\venv\Scripts\python.exe run_celestia.py --trust-config
```

## Architecture

```
run_celestia.py           # CLI entry — _build_parser() then dispatches to _run_*() handlers
celestia_core/
  agent.py                # Core turn loop: build context → ollama.chat → tool calls → response
  personality.py          # Builds system prompt from personalities/*.yaml (cached per active personality)
  shell_server.py         # FastAPI app on 127.0.0.1:8765 — REST + SSE streaming for Tauri shell
  shell_chat.py           # Session store: per-session files in data/shell_chat/sessions/<uuid>.json
  shell_launch.py         # Starts shell_server + Tauri process
  shell_ptt.py            # Shell push-to-talk state machine + global hotkey
  shell_overlay.py        # Companion bubble server side: overlay_seq toggle counter (hotkey ui.overlay_hotkey / POST /overlay/toggle)
  security.py             # Mode state (safe/scoped/armed), gate_pc_tool(), audit log
  scope.py                # Workspace path allowlist, protected path checks
  config.py               # Reads config.yaml; get(key, default) accessor — always use this, never read config directly
  open_dispatch.py        # Routes "open X" text to open_path or open_url
  ollama_service.py       # Ollama lifecycle: status() probe (running/down/starting/not_installed/missing_models), start() detached `ollama serve`, start_pull()/cancel_pull(), cli_gate() terminal prompt; user-only, never an LLM tool
  incognito.py            # Pause-learning toggle: shared mtime-cached state (data/incognito_state.json); is_on() gates consolidation/graph/activity
  untrusted.py            # Prompt-injection defense: wrap_tool_result() delimits external content (file/web/clipboard) as untrusted data
skills/
  registry.py             # tool_schemas() + execute_tool() — the single dispatch layer for all LLM tool calls
  memory/store.py         # mem0 + ChromaDB wrapper; _memory is lazily initialized (None at import)
  memory/session_consolidate.py  # Background LLM pass that distills chat history into long-term memory
  memory/ranking.py       # Memory lifecycle: importance-by-kind, recall-stats sidecar, blended recall ranking, keeper pins
  memory/decay.py         # Memory lifecycle: TTL decay-delete of low-importance, never-recalled, old entries (off by default)
  memory/graph_store.py   # Temporal knowledge graph (Feature 10): SQLite nodes/edges with versioned-supersede + multi-hop walk
  memory/graph_extract.py # Background LLM pass: chat excerpt → (subject,predicate,object) triples into graph_store
  tts/                    # Orpheus (llama-cpp local) or Edge TTS; queue.py handles sentence streaming
  stt/engine.py           # faster-whisper; model lazily loaded, idle-unloaded after N minutes
  vision/                 # Capture → preprocess → Ollama vision model → optional confirm flow
  pc_control/tools.py     # open_path, open_url, run_powershell — all gated through security.gate_pc_tool()
  todos/                  # To-do list: store.py (locked JSON in data/todos.json) + tools.py (todo_add/list/complete/update/remove)
  mcp/manager.py          # MCP client: stdio servers from mcp.servers on a background asyncio loop; mcp__<server>__<tool> naming
  mcp/tools.py            # MCP tools → schemas filtered by min_mode (default armed) + gated executor (security.gate_mcp_tool)
  conversations/tools.py  # Conversation search (Feature 03 / #86): search_conversations tool over past sessions (shell_chat.search_sessions)
shell/                    # Tauri v2 + React 19 + Vite + Tailwind + shadcn/ui desktop app
  src/pages/Home.tsx      # Main chat page with SSE streaming
  src/pages/Todos.tsx     # To-do page — add/complete/edit/delete; talks to /todos API
  src/pages/Overlay.tsx   # Companion bubble (Tauri window "overlay", ?view=overlay): Aura orb → mini chat + PTT
  src/lib/overlayWindow.ts # All Tauri window calls for the bubble (show/hide/position/expand); no-op outside Tauri
  src/hooks/useOllama.tsx # OllamaProvider (one poller per window) + useOllama(): status, chatReady, start/pull/cancelPull, setOnLaunch
  src/components/OllamaGate.tsx # Launch dialog (Start Ollama and Run / Run Without Ollama / Quit) + the banner shown afterwards or when Ollama drops
  src/api.ts              # All fetch calls to shell_server.py; reads token from /token endpoint
personalities/*.yaml      # Personality packs — name, traits, extra prompt lines
tests/                    # pytest; all heavy deps (Ollama, Chroma, mem0, Whisper) are mocked
evals/                    # Gate A eval harness — extraction + tool-call gold-sets + scoring runners (hits live Ollama; see evals/README.md)
```

## Key design patterns

**Turn loop** (`agent.py`): `_memory_context()` → inject last-session note → build message list → `ollama.chat()` → if tool_calls: `execute_tool()` → loop back → final text response. Tool schemas are filtered by security mode in `registry.tool_schemas()`.

**Security modes**: `safe` (blocks all PC tools except always-ok list) → `scoped` (PC tools gated to workspace paths) → `armed` (full PC control). State is persisted to `data/security_state.json` and shared across tray/shell/CLI processes. Always call `security.gate_pc_tool()` before executing any PC tool.

**Session storage**: Chat sessions live in `data/shell_chat/sessions/<uuid>.json` with the active session pointer in `data/shell_chat/active`. The full `_file_lock()` mechanism in `shell_chat.py` handles concurrent access from tray, shell API, and CLI simultaneously.

**Config**: `get("key.subkey", default)` from `celestia_core/config.py` everywhere. After editing `config.yaml`, run `--trust-config` to update the integrity hash. Secrets go in `.env` only — never `config.yaml`.

**Skills / tools**: To add a new LLM-callable tool: (1) define schema + function in `skills/<name>/tools.py`, (2) import and add to `registry.py` in both `tool_schemas()` and `execute_tool()`. The security gate in `execute_tool()` calls `security.gate_pc_tool()` before running any PC-touching tool.

**MCP tools** (`skills/mcp/`): third-party servers from `mcp.servers` become `mcp__<server>__<tool>` tools. Each tool has a `min_mode` (server `min_mode` / per-tool `tool_modes`, default `armed`): filtered out of `tool_schemas()` below it *and* re-checked by `security.gate_mcp_tool()` at call time; every result is wrapped untrusted. Off by default (`mcp.enabled`). Guide: `docs/guide/mcp.md`.

**Heavy deps are lazy**: `mcp`, `mem0`, `chromadb`, `faster-whisper`, `llama-cpp`, `torch`, `pystray`, `pynput` are all imported inside functions — never at module top-level. This keeps startup fast and lets tests run without installing them.

**Memory lifecycle** (`skills/memory/ranking.py` + `decay.py`): memories are *saved* freely (auto-consolidation), then **ranked and decayed** so one-offs don't crowd recall. Each entry gets a write-time `importance` (by kind: instruction 1.0 > fact 0.7 > task 0.4 > summary 0.3); `recall_count`/`last_recalled`/`keep` live in a JSON **sidecar** (`data/memory/recall_stats.json`) keyed by memory id, so a recall never rewrites a vector. `build_context` blends similarity with importance+recall+recency (`rank_order`) and bumps recall on injected entries. `decay.sweep_decay()` deletes only unprotected, low-importance, **never-recalled**, old entries (ever-recalled or pinned = exempt) — off by default (`memory.decay.enabled`), throttled, run on session-finalize + `POST /memory/decay`. The two GPU model tiers split here: cheap 3B heuristics on the hot path, a bigger model on a future GPU-idle pass for smarter re-scoring + graph entity-resolution.

**Memory provenance** (`skills/memory/store.py`): `build_context` records the entries it injected (memory + graph) into a `ContextVar`; the chat layer drains it with `take_last_provenance()` and attaches `provenance` to the chat response / stream done event. The shell renders an expandable "what I was remembering" row under the latest reply (`MemoryProvenance.tsx`). Live-reply only — not persisted across reload.

**Memory origin + quarantine** (T04, `skills/memory/types.py` `trust_policy`): every `store.add()` takes an `origin` (`user`/`assistant`/`consolidation`/`screen`/`tool:<name>`) and `untrusted=`; untrusted writes are stored as quarantined facts (`requested_kind` kept) and are excluded from `search()`, `format_list()`, cached instructions and `build_context` until approved (`update_entry(approve=True)`, `POST /memory/{id}/approve`). `agent.py` passes `untrusted.turn_tainted(messages)` into `execute_tool(untrusted_context=...)`: in a tainted turn `memory_add` is quarantined and `memory_edit`/`memory_delete` are refused. Consolidation keeps an item live in a tainted window only if `untrusted.supported_by(item, user_text)`; graph relations are grounded the same way.

**Message time** (`shell_chat._stamp_turn` + `agent._time_note`): shell sessions stamp every stored message with `ts` (epoch seconds; older transcripts have none). `_message_to_dict` keeps `ts`, `_model_messages()` strips it before every `ollama.chat`. Each turn adds a `[Time] It is …` system note (local time, plus "previous message was N ago" after `chat.time_gap_hours` idle) right before the user message; `_strip_ephemeral` always drops it, so it is never stored. The shell shows a name + time over each turn and day dividers.

**Ollama launch gate** (`celestia_core/ollama_service.py` + `shell/src/components/OllamaGate.tsx`): `status()` is the one probe everything shares (`/ollama/status`, `/status`'s `ollama_state`, `preflight.check_ollama`). Model names match exactly, tag included (bare name = `:latest`), so `qwen2.5:7b` doesn't satisfy `qwen2.5:3b`. `start()` spawns a **detached** `ollama serve` (no window, outlives Celestia, `OLLAMA_HOST` from `llm.host`) on a worker thread and is idempotent; it refuses unless `llm.host` is local. `start_pull()` only pulls the configured chat/embed models, with aggregated progress and `cancel_pull()`. These are user actions on token-guarded `POST /ollama/{start,pull,pull/cancel}` — **never register them as LLM tools**. The remembered launch choice (`llm.ollama_on_launch`: `ask`/`start`/`skip`) is a UI pref in `data/ui_prefs.json`, so it needs no `--trust-config`. Chat failures carry `code` (`ollama_down`/`model_missing`) on the stream error event so the shell raises the banner at once; `shell_server` turns stray connection errors into a friendly 503 only when Ollama really is down. On Windows a refused localhost connect hangs for the whole connect timeout, so the probe uses a short connect + generous read timeout — keep it that way, and don't add a second prober while a start is in flight.

**Privacy & untrusted input** (Gate B / prompt-injection): `incognito.is_on()` pauses *all* recording (consolidation, graph extraction, activity feed) at the single `should_run_consolidation()` choke point while chat keeps working — toggled from tray, shell sidebar, or `POST /incognito`. Separately, `untrusted.wrap_tool_result()` delimits any external text (`file_read`/`clipboard_read`/`fetch_page`/`web_search`) as `⟦UNTRUSTED DATA … ⟧` before it re-enters the model context; the system prompt (`personality._BASE`) carries the matching "data, not instructions" clause. Keep the two halves in sync.

## Configuration files

| File | Purpose |
|------|---------|
| `config.yaml` | Personal config (gitignored — copy from `config.example.yaml`) |
| `security.policy.yaml` | URL/app allowlists (gitignored — copy from `security.policy.example.yaml`) |
| `.env` | Secrets: `HF_TOKEN` etc. |

## Work plan

The current plan is `docs/project/landscape-2026-09.md` (tasks T01–T14, decisions D1–D9); `docs/project/roadmap.md` follows its build order. Work one task ID per branch/PR, and don't change a locked stance (model choice, no cloud by default, mem0 + SQLite graph) without an eval result.

## Commit convention

Every commit that closes a GitHub issue must include `Closes #N` in the footer. The `commit-msg` hook warns if missing. Issue tracker: GitHub Issues only (Linear is no longer used).
