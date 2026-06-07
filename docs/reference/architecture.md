# Architecture

**Entry point:** `run_celestia.py` → `celestia_core/` + `skills/`

---

## Stack

| Layer | Technology | Config key |
|-------|-----------|------------|
| LLM inference | Ollama (`ollama.chat`) | `llm.chat_model` |
| Vision | Ollama (`qwen2.5vl:7b`) | `vision.text_model` |
| Embeddings | Ollama (`nomic-embed-text`) | `llm.embed_model` |
| Vector memory | mem0 + ChromaDB on disk | `memory.vector_store: chroma` |
| STT | faster-whisper, CUDA | `voice.stt.*` |
| TTS | Orpheus (llama-cpp + SNAC) or Edge TTS | `voice.tts.provider` |
| Desktop shell | Tauri v2 + React 19 + Vite | `shell/` |
| Shell API | FastAPI + uvicorn on `127.0.0.1` | `ui.shell_port` |
| System tray | pystray + pynput | `ui.tray` |

Optional backends (not required): Qdrant (instead of Chroma), n8n, LiveKit — see [optional-docker/README.md](../optional-docker/README.md).

---

## Folder map

```
run_celestia.py           # CLI entry: --shell, --tray, -i, --check, flags
celestia_core/
  agent.py                # LLM turn loop: memory inject → ollama.chat → tools → response
  personality.py          # Builds system prompt from personalities/*.yaml (cached per active personality)
  shell_server.py         # FastAPI app on 127.0.0.1:8765 — REST + SSE streaming
  shell_chat.py           # Session store: per-session files in data/shell_chat/sessions/<uuid>.json
  shell_launch.py         # Starts shell_server + Tauri process
  shell_ptt.py            # Shell PTT state machine, global hotkey listener
  config.py               # Reads config.yaml; get() accessor
  security.py             # Mode state, gate_pc_tool(), audit_tool()
  scope.py                # Workspace paths, app allowlist, protected paths
  open_dispatch.py        # Routes "open X" to open_path or open_url
  url_policy.py           # URL allowlist check
  preflight.py            # --check health tests
  faillog.py              # Startup error capture
  ui/
    tray.py               # CelestiaTray: hotkeys, menus, shell chat launch
    settings_app.py       # Legacy tk settings window (ui.shell_settings: false)
  platform/
    windows.py            # Windows-specific paths, protected prefixes
    linux.py              # Stub for Phase 3.5 Linux port

skills/
  registry.py             # tool_schemas() and execute_tool() — add new skills here
  memory/
    store.py              # mem0 + Chroma CRUD: add, search, get_all_entries, delete
    types.py              # MemoryKind literal type; kinds_enabled()
    session_consolidate.py  # LLM extracts facts/tasks/summaries from session history
    activity_feed.py      # JSONL ring buffer of consolidation events
    last_session.py       # Per-session plain-text note (not in Chroma)
  pc_control/tools.py     # open_path, open_url, powershell; PC_TOOL_SCHEMAS
  files/tools.py          # file_read, file_write; workspace-scoped
  clipboard/tools.py      # clipboard_read, clipboard_write
  web/tools.py            # web_search, fetch_page
  briefing/tools.py       # morning_briefing
  vision/
    flow.py               # Orchestrates capture → confirm → analyze → TTS
    capture.py            # mss screenshot (region / fullscreen / window)
    history.py            # Ring buffer of captured screenshots
    confirm.py            # User confirm before sending image to model
    analyze.py            # Ollama vision model call
    preprocess.py         # Image resize, contrast boost for text OCR
  stt/engine.py           # faster-whisper load/unload, record_ptt_until()
  tts/
    manager.py            # Routes to orpheus_backend or edge_backend
    orpheus_backend.py    # llama-cpp + SNAC in-process TTS
    edge_backend.py       # edge-tts async fallback
  integrations/n8n.py     # Webhook on mode change (optional)

personalities/
  default.yaml
  companion_warm.yaml

data/                     # gitignored, created at runtime
  chroma/                 # ChromaDB vector store
  shell_chat/
    sessions/<uuid>.json  # One file per chat session
    active               # Pointer to active session UUID
  memory/
    last_session.json
    activity_feed.jsonl
  security_state.json
  config.trust
  .api_token              # Session-scoped API auth token (written at server start)

logs/                     # gitignored
  tool_audit.jsonl
  vision_audit.jsonl
  security_events.jsonl
```

---

## Data flow — one chat turn

```
User types message in shell (Home.tsx)
  │
  ▼
POST /chat/stream  →  shell_server.py  →  shell_chat.send_message_stream()
  │
  ▼
agent.py run_turn_stream(user_message, history=session_history)
  │
  ├── preflight_chat_pc()  →  early block/dispatch for obvious open/URL requests
  │
  ├── _memory_context()
  │     └── store.py build_context()
  │           └── nomic-embed-text (Ollama HTTP) → Chroma similarity search
  │           └── last_session.py context_block() (if greeting)
  │
  ├── _pc_control_hints()  →  1-2 system messages about current mode
  │
  ├── ollama.chat(model, messages, tools=tool_schemas(msg), stream=True)
  │     └── yields tokens via SSE → Home.tsx accumulates live in chat bubble
  │
  ├── if tool_calls (synchronous fallback rounds):
  │     └── registry.execute_tool(name, args)
  │           ├── security.gate_pc_tool()  →  Blocked? return early
  │           ├── call skill function
  │           └── security.audit_tool()  →  logs/tool_audit.jsonl
  │
  └── yield {done, reply, messages}
  │
  ▼
shell_chat.py saves updated history to sessions/<uuid>.json
  │
  ▼ (background thread, every N turns)
session_consolidate.py
  └── LLM extracts facts/tasks/summaries
  └── store.py add() → Chroma
  └── activity_feed.py append_event()
  └── last_session.py update_from_messages()
```

---

## Data flow — voice PTT (shell)

```
User holds mic button (ChatInput.tsx)
  │
POST /chat/ptt/start  →  shell_ptt.ptt_start()
  └── stt/engine.py: start recording in background thread

User releases mic button
  │
POST /chat/ptt/stop  →  shell_ptt.ptt_finish()
  └── stt/engine.py: stop recording, transcribe with faster-whisper
  └── agent.run_turn(transcribed_text)
  └── optional: tts/manager.speak(reply)
  └── return {reply, messages}
  │
  ▼
Home.tsx updates chat thread (same session as typed chat)
```

---

## Data flow — vision

```
User triggers screen capture (hotkey / tray / `screen` command / shell button)
  │
vision/flow.py
  └── vision/capture.py: mss screenshot (region / fullscreen / window)
  └── vision/confirm.py: sound + preview, wait for user yes/no
        [shell: POST /vision/capture → modal confirm → POST /vision/analyze]
  └── optional: unload TTS to free VRAM
  └── vision/preprocess.py: resize, contrast for text-heavy screens
  └── vision/analyze.py: ollama.chat(vision_model, image=..., question=...)
  └── optional: tts/manager.speak(result)
```

---

## Security model

Three modes share state via `data/security_state.json` (when `security.shared_armed_state: true`):

| Mode | Tools available |
|------|----------------|
| `safe` | Memory + web tools only; no PC, no files, no clipboard |
| `scoped` | Allowlisted apps, file read/write in workspaces, clipboard, URL allowlist |
| `armed` | All tools; denylist and destructive-action confirms still apply |

All tool calls pass through `security.gate_pc_tool()` and write to `logs/tool_audit.jsonl`.  
Allowlists and workspaces live in `security.policy.yaml`.  
Mode and audit settings live in `config.yaml`.

See [security.md](../guide/security.md) for user-facing docs.

---

## Shell API overview

The Tauri shell communicates exclusively with the local Python server at `127.0.0.1:8765`. Auth token is bootstrapped via `GET /token` (localhost-only, no header required) and stored in `data/.api_token`. All other endpoints require `X-Celestia-Token` header.

```
Tauri shell (React)
  └── api.ts
        └── GET  /token               → session auth token
        └── GET  /status              → build_status() — no token required
        └── POST /chat/stream         → SSE streaming (primary chat path)
        └── POST /chat                → non-streaming fallback
        └── GET  /chat/sessions       → list_sessions()
        └── POST /chat/new            → create_session()
        └── POST /chat/select         → set_active_session()
        └── POST /chat/ptt/*          → shell_ptt.*
        └── POST /vision/capture      → capture_fullscreen()
        └── POST /vision/analyze      → analyze_image() + append to session
        └── GET  /vision/history      → screenshot ring buffer
        └── GET/POST/PATCH/DELETE /memory/*  → store.py CRUD
        └── GET/PATCH /prefs          → mutable config keys
        └── GET/POST/DELETE /workspaces → scope.py workspace management
        └── GET /audit/tail           → recent tool_audit.jsonl entries
```

Full API reference: [api.md](api.md)

---

## What to ignore

- `Orpheus-FastAPI/` — SNAC helpers and a standalone FastAPI wrapper. Celestia uses Orpheus in-process via `skills/tts/orpheus_local.py`; the FastAPI server is not required.
