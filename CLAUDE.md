# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

Celestia is a local Windows AI companion — chat, memory, voice, screen reading, and PC control. It runs entirely on-device via Ollama (no cloud LLM). The main entry point is `run_celestia.py`.

Required service: **Ollama must be running** (`ollama serve`) before any Celestia commands work.

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

# T15 eval — score the memory writer (think on/off) against today's consolidation on the same cases
.\venv\Scripts\python.exe -m evals.consolidation_eval --model qwen3.5:4b

# T15 eval — does the running chat summary keep early facts and exact details? (structured vs prose)
.\venv\Scripts\python.exe -m evals.summary_eval --model qwen3.5:4b

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
  memory/graph_backfill.py # T15: links pre-writer memories to the graph in idle batches (source memory:<id>, done-set sidecar)
  memory/writer.py        # T15 memory writer (prompt + parser): chat + summary + existing memories → add/update/supersede/forget ops, each with text + triples
  memory/writer_pass.py   # T15: runs the writer over a chat window and applies ops to text memory + graph together; consolidate() dispatches writer|legacy (memory.pipeline)
  memory/session_summary.py # T15 working memory: structured running summary of one chat (prompt/schema/parse/merge/render)
  memory/links.py         # T15 sidecars: memory id → graph edge ids (data/memory/graph_links.json) + superseded-memory history.jsonl
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
  src/api.ts              # All fetch calls to shell_server.py; reads token from /token endpoint
personalities/*.yaml      # Personality packs — name, traits, extra prompt lines
tests/                    # pytest; all heavy deps (Ollama, Chroma, mem0, Whisper) are mocked
evals/                    # Gate A eval harness — extraction + tool-call gold-sets + scoring runners (hits live Ollama; see evals/README.md)
```

## Key design patterns

**Turn loop** (`agent.py`): `_memory_context()` → inject last-session note → build message list → `ollama.chat()` → if tool_calls: `execute_tool()` → loop back → final text response. Tool schemas are filtered by security mode in `registry.tool_schemas()`.

**Security modes**: `safe` (blocks all PC tools except always-ok list) → `scoped` (PC tools gated to workspace paths) → `armed` (full PC control). State is persisted to `data/security_state.json` and shared across tray/shell/CLI processes. Always call `security.gate_pc_tool()` before executing any PC tool.

**Session storage**: Chat sessions live in `data/shell_chat/sessions/<uuid>.json` with the active session pointer in `data/shell_chat/active`. The full `_file_lock()` mechanism in `shell_chat.py` handles concurrent access from tray, shell API, and CLI simultaneously.

**Memory pass (T15)**: `skills/memory/writer_pass.consolidate()` runs at the end of a chat (new/delete/quit, or `memory.writer.idle_minutes` idle via `shell_chat.idle_sweep` on the shell's idle daemon) and at mid-chat checkpoints (`shell_chat._checkpoint_reason`: unsaved messages about to be trimmed out of `chat.session_max_messages`, or `memory.writer.checkpoint_minutes`). The session cursor is absolute (`seq_base` + `consolidated_seq`) because the agent trims history from the front; never index history with a stored integer. Each applied op moves text memory and its linked graph edges together; `store.delete_by_id` cascades to linked edges. The same checkpoint updates the session's structured `summary` (`skills/memory/session_summary.py`: goal/now/facts/decisions/open/details with code-side carry-over; own model call in `writer_pass.summarize`). Trimmed messages go to the session `archive` (`_record_turn`), shown in the UI and keyword-recalled per turn (`_recall_note`). Summary + recall ride along each turn as one ephemeral system note (`shell_chat._turn_notes` → `agent._prepare_messages(session_note=…)`, stripped before storage). The graph is on by default (`memory.graph.enabled`). A running pass shows as `memory_saving` on `/ws/state` (`shell_chat.memory_saving()`); the notes are readable via `GET /chat/notes`.

**Config**: `get("key.subkey", default)` from `celestia_core/config.py` everywhere. After editing `config.yaml`, run `--trust-config` to update the integrity hash. Secrets go in `.env` only — never `config.yaml`.

**Skills / tools**: To add a new LLM-callable tool: (1) define schema + function in `skills/<name>/tools.py`, (2) import and add to `registry.py` in both `tool_schemas()` and `execute_tool()`. The security gate in `execute_tool()` calls `security.gate_pc_tool()` before running any PC-touching tool.

**MCP tools** (`skills/mcp/`): third-party servers from `mcp.servers` become `mcp__<server>__<tool>` tools. Each tool has a `min_mode` (server `min_mode` / per-tool `tool_modes`, default `armed`): filtered out of `tool_schemas()` below it *and* re-checked by `security.gate_mcp_tool()` at call time; every result is wrapped untrusted. Off by default (`mcp.enabled`). Guide: `docs/guide/mcp.md`.

**Heavy deps are lazy**: `mcp`, `mem0`, `chromadb`, `faster-whisper`, `llama-cpp`, `torch`, `pystray`, `pynput` are all imported inside functions — never at module top-level. This keeps startup fast and lets tests run without installing them.

**Memory lifecycle** (`skills/memory/ranking.py` + `decay.py`): memories are *saved* freely (auto-consolidation), then **ranked and decayed** so one-offs don't crowd recall. Each entry gets a write-time `importance` (by kind: instruction 1.0 > fact 0.7 > task 0.4 > summary 0.3); `recall_count`/`last_recalled`/`keep` live in a JSON **sidecar** (`data/memory/recall_stats.json`) keyed by memory id, so a recall never rewrites a vector. `build_context` blends similarity with importance+recall+recency (`rank_order`) and bumps recall on injected entries. `decay.sweep_decay()` deletes only unprotected, low-importance, **never-recalled**, old entries (ever-recalled or pinned = exempt) — off by default (`memory.decay.enabled`), throttled, run on session-finalize + `POST /memory/decay`. The two GPU model tiers split here: cheap 3B heuristics on the hot path, a bigger model on a future GPU-idle pass for smarter re-scoring + graph entity-resolution.

**Memory provenance** (`skills/memory/store.py`): `build_context` records the entries it injected (memory + graph) into a `ContextVar`; the chat layer drains it with `take_last_provenance()` and attaches `provenance` to the chat response / stream done event. The shell renders an expandable "what I was remembering" row under the latest reply (`MemoryProvenance.tsx`). Live-reply only — not persisted across reload.

**Memory origin + quarantine** (T04, `skills/memory/types.py` `trust_policy`): every `store.add()` takes an `origin` (`user`/`assistant`/`consolidation`/`screen`/`tool:<name>`) and `untrusted=`; untrusted writes are stored as quarantined facts (`requested_kind` kept) and are excluded from `search()`, `format_list()`, cached instructions and `build_context` until approved (`update_entry(approve=True)`, `POST /memory/{id}/approve`). `agent.py` passes `untrusted.turn_tainted(messages)` into `execute_tool(untrusted_context=...)`: in a tainted turn `memory_add` is quarantined and `memory_edit`/`memory_delete` are refused. Consolidation keeps an item live in a tainted window only if `untrusted.supported_by(item, user_text)`; graph relations are grounded the same way.

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
