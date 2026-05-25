# Changelog

All notable changes by delivery phase. Most recent first.

---

## Phase 4 — Product UI (current)

**In progress:** Tauri shell, shell Memory page, shell PTT, session management.

### Shipped in Phase 4
- **CC-88** — `shell_server.py` migrated from `ThreadingHTTPServer` to FastAPI + uvicorn. All existing routes preserved. `start_server()`, `stop_server()`, `ping()`, `run_server_forever()` public interface unchanged.
- **CC-89** — `POST /chat/stream` SSE endpoint added to `shell_server.py`. `run_turn_stream()` added to `agent.py` (yields `{"token"}` chunks then `{"done"}`). `send_message_stream()` added to `shell_chat.py` (session management + streaming). Tool-call turns complete synchronously and yield a single done event.
- **CC-90** — Streaming frontend: `streamChatMessage()` async generator added to `api.ts`; `Home.tsx` `onSend` replaced with streaming loop — tokens accumulate live in the assistant bubble, "Thinking…" shows only until first token arrives.
- `start.bat` added — double-click to launch the Tauri shell without typing any commands.
- **CC-111** — pytest smoke suite added (`tests/`). 57 tests across 5 modules: `_strip_ephemeral`, `build_system_prompt` + cache, `gate_pc_tool` + mode cycling, `should_run_consolidation`, `run_turn` with mocked Ollama, and memory store CRUD. All pass with no real Ollama or Chroma dependency. Run: `python -m pytest tests/ -v`
- `ui/` moved to `celestia_core/ui/` — `tray.py` and `settings_app.py` are now under the core package. All imports updated in `run_celestia.py`. Old `ui/` directory deleted.
- `legacy/` deleted — empty directory with no active references.
- Linear backlog synced — CC-88 through CC-112 created; CC-91/92/93/94 and doc tickets CC-107–CC-110 marked Done. New `architecture` label added.
- **CC-91** — Strip ephemeral mode-hint and memory-context system messages from stored session history (`agent.py`). Prevents session context budget from being consumed by repeated injected system messages.
- **CC-92** — Ollama request timeout via `llm.request_timeout_seconds` (default 60s). Uses `ollama.Client` instead of module-level call; hung requests now raise an exception instead of blocking forever. (`agent.py`, `config.example.yaml`)
- **CC-93** — System prompt cached at the module level in `personality.py`. YAML is only read and parsed when `personality.active` changes, not on every message.
- **CC-94** — Session consolidation runs in a background `threading.Thread` during normal turns. End-of-session finalization (`newchat`, quit) still runs synchronously. Eliminates the response stutter on every Nth turn. (`shell_chat.py`)
- Activity feed trim optimized — `_trim_file` now skips the read+rewrite when the file is under ~20 KB, reducing I/O on every memory auto-save. (`activity_feed.py`)
- Desktop shell v1 — Tauri + React (`shell/`, `--shell`, `--settings`)
- Shell server API — `127.0.0.1:8765`, all `/chat`, `/memory`, `/status` routes
- Shell chat sessions — multi-session store, sidebar history, `+ New Chat`
- Shell Memory page — list, add, edit, delete entries; last-session note + refresh
- Shell PTT — in-shell hold-to-talk mic button; `shell_ptt.py`; global hotkey `ctrl+alt+shift+v`
- Memory v2 — typed entries (fact / instruction / summary / task), auto-save from chat, budgeted inject, activity feed, last-session note
- Session consolidation — LLM extracts facts/tasks/summaries every N turns and on `newchat`/quit

---

## Phase 3 — Security & Files

### Phase 3c
- `security.policy.yaml` — app and URL allowlists separated from `config.yaml`
- URL allowlist + smart `open github` dispatch
- Clipboard read/write (scoped)
- `--pick-workspace` CLI flag
- `tray_max_mode` config cap for tray/voice/screen hotkeys

### Phase 3b
- `file_read` — REPL `read` command + agent tool, workspace-scoped
- `file_write` — REPL `write` command + agent tool, overwrite confirm
- Direct `open <app>` command in REPL

### Phase 3a
- Safe / scoped / armed security modes
- Workspace folder scoping (`scope add <path>`)
- App allowlist (notepad, calc, paint, …) with aliases
- Protected-path denylist (System32, Program Files)

### Phase 3 polish
- `memory_edit` agent tool
- Tray screen submenu (region / fullscreen / window)
- Voice confirm option (`allow_voice_confirm`)
- `reference/performance.md` added

---

## Phase 2.5 — Security foundations
- Audit log — `logs/tool_audit.jsonl` and `logs/vision_audit.jsonl`
- Config integrity check — `--trust-config`, `data/config.trust`
- Shared security state (`data/security_state.json`)

---

## Phase 2 — Screen / Vision
- Vision capture — region, fullscreen, active window
- Confirm before send — sound + preview
- Two-pass text OCR for dense text screens
- `--screen` CLI flag and `screen` REPL command

---

## Phase 1 — Voice
- faster-whisper STT — CUDA, idle unload, `large-v3` default
- Orpheus TTS — in-process llama-cpp + SNAC, `idle_shutdown_minutes`
- Edge TTS fallback
- System tray — hotkeys, security menu, screen submenu
- Push-to-talk hotkey (`ctrl+alt+v`)
- `--tray` CLI flag

---

## Phase 0 — Foundation
- `run_celestia.py` entry point
- Ollama chat + tool call loop (`celestia_core/agent.py`)
- mem0 + ChromaDB vector memory
- PC tool scaffolding (`skills/pc_control/`)
- `-i` interactive REPL
- Personality YAML packs (`personalities/`)
- `config.yaml` + `config.example.yaml`

---

## Rename: Atlas → Celestia
- Project folder, package name, and entry point renamed.
- `app.user_id: atlas_user` kept to preserve existing Chroma memories — no migration needed.
- See [docs/archive/rename-to-celestia.md](docs/archive/rename-to-celestia.md).
