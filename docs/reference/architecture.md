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
| Shell API | Python `ThreadingHTTPServer` on `127.0.0.1` | `ui.shell_port` |
| System tray | pystray + pynput | `ui.tray` |

Optional backends (not required): Qdrant (instead of Chroma), n8n, LiveKit — see [optional-docker/README.md](../optional-docker/README.md).

---

## Folder map

```
run_celestia.py           # CLI entry: --shell, --tray, -i, --check, flags
celestia_core/
  agent.py                # LLM turn loop: memory inject → ollama.chat → tools → response
  personality.py          # Builds system prompt from personalities/*.yaml
  shell_server.py         # HTTP API for the Tauri shell (127.0.0.1:8765)
  shell_chat.py           # Session store: sessions.json, send_message(), get_history()
  shell_launch.py         # Starts shell_server + npm run tauri dev
  shell_ptt.py            # Shell PTT state machine, global hotkey listener
  config.py               # Reads config.yaml; get() accessor
  security.py             # Mode state, gate_pc_tool(), audit_tool()
  scope.py                # Workspace paths, app allowlist, protected paths
  open_dispatch.py        # Routes "open X" to open_path or open_url
  url_policy.py           # URL allowlist check
  preflight.py            # --check health tests
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
  vision/
    flow.py               # Orchestrates capture → confirm → analyze → TTS
    capture.py            # mss screenshot (region / fullscreen / window)
    confirm.py            # User confirm before sending image to model
    analyze.py            # Ollama vision model call
    preprocess.py         # Image resize, contrast boost for text OCR
  stt/engine.py           # faster-whisper load/unload, record_ptt_until()
  tts/
    manager.py            # Routes to orpheus_backend or edge_backend
    orpheus_backend.py    # llama-cpp + SNAC in-process TTS
    edge_backend.py       # edge-tts async fallback
  integrations/n8n.py     # Webhook on mode change (optional)

ui/tray.py                # CelestiaTray: hotkeys, menus, shell chat launch

personalities/
  default.yaml
  companion_warm.yaml

data/                     # gitignored, created at runtime
  chroma/                 # ChromaDB vector store
  shell_chat/sessions.json
  memory/
    last_session.json
    activity_feed.jsonl
  security_state.json
  config.trust

logs/                     # gitignored
  tool_audit.jsonl
  vision_audit.jsonl
```

---

## Data flow — one chat turn

```
User types message in shell (Home.tsx)
  │
  ▼
POST /chat  →  shell_server.py  →  shell_chat.send_message()
  │
  ▼
agent.py run_turn(user_message, history=session_history)
  │
  ├── _memory_context()
  │     └── store.py build_context()
  │           └── nomic-embed-text (Ollama HTTP) → Chroma similarity search
  │           └── last_session.py context_block() (if greeting)
  │
  ├── _pc_control_hints()  →  1-2 system messages about current mode
  │
  ├── ollama.chat(model, messages, tools=tool_schemas(msg))
  │     └── [synchronous, no timeout, no streaming — known issue CC-88/89]
  │
  ├── if tool_calls:
  │     └── registry.execute_tool(name, args)
  │           ├── security.gate_pc_tool()  →  Blocked? return early
  │           ├── call skill function
  │           └── security.audit_tool()  →  logs/tool_audit.jsonl
  │
  └── return (reply_text, updated_messages)
  │
  ▼
shell_chat.py saves updated history to sessions.json
  │
  ▼
POST /chat response  →  Home.tsx updates chat thread
  │
  ▼ (background, every N turns)
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
User triggers screen capture (hotkey / tray / `screen` command)
  │
vision/flow.py
  └── vision/capture.py: mss screenshot (region / fullscreen / window)
  └── vision/confirm.py: sound + preview, wait for user yes/no
        [currently: console or tkinter dialog — shell modal planned CC-49]
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
| `safe` | Memory tools only; no PC, no files, no clipboard |
| `scoped` | Allowlisted apps, file read/write in workspaces, clipboard, URL allowlist |
| `armed` | All tools; denylist and destructive-action confirms still apply |

All tool calls pass through `security.gate_pc_tool()` and write to `logs/tool_audit.jsonl`.  
Allowlists and workspaces live in `security.policy.yaml`.  
Mode and audit settings live in `config.yaml`.

See [security.md](../guide/security.md) for user-facing docs.

---

## Shell API overview

The Tauri shell communicates exclusively with the local Python server at `127.0.0.1:8765`. The frontend never talks to Ollama directly.

```
Tauri shell (React)
  └── api.ts
        └── GET /status          → build_status()
        └── POST /chat           → shell_chat.send_message()
        └── GET /chat/sessions   → list_sessions()
        └── POST /chat/ptt/*     → shell_ptt.*
        └── GET/POST/PATCH/DELETE /memory/* → store.py CRUD
```

Full API reference: [api.md](api.md)

---

## Known architectural issues (next cycle)

| Issue | Ticket | Impact |
|-------|--------|--------|
| No LLM streaming — `ollama.chat()` blocks until full response | CC-88, CC-89 | 3–10s silence per message |
| No Ollama request timeout | CC-92 | Hangs forever if Ollama crashes mid-generation |
| PTT polls at 250ms against synchronous server | CC-88 | Status requests queue behind LLM calls |
| Per-turn mode hints appended to session history | CC-91 | Bloats context budget over time |
| Session consolidation blocks response thread | CC-94 | Stutter on every Nth turn |
| sessions.json fully rewritten each message | CC-95 | File grows unboundedly; lock latency |

See [roadmap.md](../project/roadmap.md) for the full ticket list.

---

## What to ignore

- `legacy/` — old Flask prototype. Not loaded by anything.
- `Orpheus-FastAPI/` — SNAC helpers and a standalone FastAPI wrapper. Celestia uses Orpheus in-process via `skills/tts/orpheus_local.py`; the FastAPI server is not required.
