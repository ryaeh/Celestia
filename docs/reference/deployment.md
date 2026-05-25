# What you actually run

**Required:** Ollama running in the background. Everything else is inside the `run_celestia.py` process.

**Not required:** Docker for memory (Chroma is the default), LM Studio, a separate Whisper server, Orpheus-FastAPI running as HTTP, or any other external server for normal use.

**Optional Docker:** Qdrant, n8n, LiveKit — see [optional-docker/README.md](../optional-docker/README.md).

---

## Startup modes

| Command | What starts |
|---------|-------------|
| `run_celestia.py -i` | Interactive REPL only |
| `run_celestia.py --tray` | System tray + global hotkeys |
| `run_celestia.py --shell` | Shell API server + Tauri window |
| `run_celestia.py --shell-server` | Shell API server only (for dev hot-reload) |
| `run_celestia.py --check` | Preflight health check, then exit |

Flags can be combined: `--tray --shell-server` starts both the tray and the API server without opening a window (useful if you want to open the Tauri dev build separately).

---

## Shell startup in detail

### Production (one command)

```powershell
cd C:\celestia
.\venv\Scripts\python.exe run_celestia.py --shell
```

This starts the Python API on `127.0.0.1:8765`, waits for it to be ready, then launches the Tauri window. The window talks to the API over localhost. Closing the window does not stop the Python process.

### Dev mode (hot-reload)

Open two terminals:

**Terminal 1 — Python API:**

```powershell
cd C:\celestia
.\venv\Scripts\python.exe run_celestia.py --shell-server
```

You should see: `[shell] API http://127.0.0.1:8765`

**Terminal 2 — Tauri + Vite dev server:**

```powershell
cd C:\celestia\shell
npm run tauri dev
```

Vite proxies `/api/*` to `127.0.0.1:8765` in dev mode (configured in `shell/vite.config.ts`). The Tauri window hot-reloads on frontend changes without restarting Python.

### Shell port

Default port: `8765`. Change via `ui.shell_port` in `config.yaml`, then run `--trust-config`.

If the port is in use:

```powershell
netstat -ano | findstr :8765
taskkill /PID <pid> /F
```

---

## Tauri build (production binary)

```powershell
cd C:\celestia\shell
npm run build          # TypeScript compile + Vite bundle
npm run tauri build    # Rust + WebView2 packaging
```

The output installer is in `shell/src-tauri/target/release/bundle/`.

**Prerequisites:** Node.js 20+, Rust (via [rustup.rs](https://rustup.rs/)), WebView2 (included on Windows 10/11).

---

## Fresh machine setup

```powershell
cd C:\celestia
.\scripts\setup.ps1
copy .env.example .env
copy config.example.yaml config.yaml

# Pull LLM models
ollama pull qwen2.5:7b
ollama pull qwen2.5vl:7b
ollama pull nomic-embed-text

# Trust the config files
.\venv\Scripts\python.exe run_celestia.py --trust-config
.\venv\Scripts\python.exe run_celestia.py --check

# Shell frontend dependencies (one-time)
cd shell && npm install && cd ..
```

Full walkthrough: [getting-started.md](../getting-started.md)

---

## What lives on disk (runtime data)

| Path | Created by | Safe to delete? |
|------|-----------|-----------------|
| `data/chroma/` | First chat | Yes — wipes all memories |
| `data/shell_chat/sessions.json` | First shell chat | Yes — loses chat history |
| `data/memory/last_session.json` | First `newchat` or quit | Yes — regenerates |
| `data/memory/activity_feed.jsonl` | First auto-save | Yes |
| `data/security_state.json` | First mode change | Yes — resets to `safe` |
| `data/config.trust` | `--trust-config` | Yes — run `--trust-config` to rebuild |
| `logs/tool_audit.jsonl` | First tool call | Yes — rotates fine |
| `logs/vision_audit.jsonl` | First screen capture | Yes |
| `temp/vision/` | Screen captures | Yes — cleaned up after each use |

---

## Nice to have on disk before first run

- `.env` with `HF_TOKEN` (speeds up faster-whisper SNAC download)
- `models/Orpheus-3b-FT-Q8_0.gguf` for local Orpheus TTS
- `security.policy.yaml` (copy from `security.policy.example.yaml` to set custom allowlists)
