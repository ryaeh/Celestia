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
  security.py             # Mode state (safe/scoped/armed), gate_pc_tool(), audit log
  scope.py                # Workspace path allowlist, protected path checks
  config.py               # Reads config.yaml; get(key, default) accessor — always use this, never read config directly
  open_dispatch.py        # Routes "open X" text to open_path or open_url
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
shell/                    # Tauri v2 + React 19 + Vite + Tailwind + shadcn/ui desktop app
  src/pages/Home.tsx      # Main chat page with SSE streaming
  src/pages/Todos.tsx     # To-do page — add/complete/edit/delete; talks to /todos API
  src/api.ts              # All fetch calls to shell_server.py; reads token from /token endpoint
personalities/*.yaml      # Personality packs — name, traits, extra prompt lines
tests/                    # pytest; all heavy deps (Ollama, Chroma, mem0, Whisper) are mocked
```

## Key design patterns

**Turn loop** (`agent.py`): `_memory_context()` → inject last-session note → build message list → `ollama.chat()` → if tool_calls: `execute_tool()` → loop back → final text response. Tool schemas are filtered by security mode in `registry.tool_schemas()`.

**Security modes**: `safe` (blocks all PC tools except always-ok list) → `scoped` (PC tools gated to workspace paths) → `armed` (full PC control). State is persisted to `data/security_state.json` and shared across tray/shell/CLI processes. Always call `security.gate_pc_tool()` before executing any PC tool.

**Session storage**: Chat sessions live in `data/shell_chat/sessions/<uuid>.json` with the active session pointer in `data/shell_chat/active`. The full `_file_lock()` mechanism in `shell_chat.py` handles concurrent access from tray, shell API, and CLI simultaneously.

**Config**: `get("key.subkey", default)` from `celestia_core/config.py` everywhere. After editing `config.yaml`, run `--trust-config` to update the integrity hash. Secrets go in `.env` only — never `config.yaml`.

**Skills / tools**: To add a new LLM-callable tool: (1) define schema + function in `skills/<name>/tools.py`, (2) import and add to `registry.py` in both `tool_schemas()` and `execute_tool()`. The security gate in `execute_tool()` calls `security.gate_pc_tool()` before running any PC-touching tool.

**Heavy deps are lazy**: `mem0`, `chromadb`, `faster-whisper`, `llama-cpp`, `torch`, `pystray`, `pynput` are all imported inside functions — never at module top-level. This keeps startup fast and lets tests run without installing them.

**Memory lifecycle** (`skills/memory/ranking.py` + `decay.py`): memories are *saved* freely (auto-consolidation), then **ranked and decayed** so one-offs don't crowd recall. Each entry gets a write-time `importance` (by kind: instruction 1.0 > fact 0.7 > task 0.4 > summary 0.3); `recall_count`/`last_recalled`/`keep` live in a JSON **sidecar** (`data/memory/recall_stats.json`) keyed by memory id, so a recall never rewrites a vector. `build_context` blends similarity with importance+recall+recency (`rank_order`) and bumps recall on injected entries. `decay.sweep_decay()` deletes only unprotected, low-importance, **never-recalled**, old entries (ever-recalled or pinned = exempt) — off by default (`memory.decay.enabled`), throttled, run on session-finalize + `POST /memory/decay`. The two GPU model tiers split here: cheap 3B heuristics on the hot path, a bigger model on a future GPU-idle pass for smarter re-scoring + graph entity-resolution.

## Configuration files

| File | Purpose |
|------|---------|
| `config.yaml` | Personal config (gitignored — copy from `config.example.yaml`) |
| `security.policy.yaml` | URL/app allowlists (gitignored — copy from `security.policy.example.yaml`) |
| `.env` | Secrets: `HF_TOKEN` etc. |

## Commit convention

Every commit that closes a GitHub issue must include `Closes #N` in the footer. The `commit-msg` hook warns if missing. Issue tracker: GitHub Issues only (Linear is no longer used).
