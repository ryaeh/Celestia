# Celestia

> **Active development — Sep 2026: security & model sprint** (evals, model re-baseline, prompt-injection and memory-poisoning defenses, fully local Turkish + English voice). See the [roadmap](docs/project/roadmap.md).

A local AI companion for Windows — chat, voice, memory, screen reading, and PC control. Runs on-device via [Ollama](https://ollama.com). No API keys, no subscription.

**What makes it different:** a free, offline companion for an 8–12 GB NVIDIA GPU that **sees your screen**, keeps an **inspectable, time-aware memory**, **acts only through audited, gated permissions**, and is being built to work end-to-end in **Turkish and English**.

> **Personal project.** Not accepting pull requests or issues from external contributors.  
> Built with the help of [Claude](https://claude.ai) (Anthropic). Made with AI.

---

## What it does

- **Chat** — conversational AI with full session history and memory that persists across restarts
- **Voice** — push-to-talk with local STT (faster-whisper) and TTS (Orpheus). *Default STT model is English-only; Turkish voice is in progress (T05).*
- **Memory** — remembers facts, instructions, preferences, and tasks; distills conversations into long-term memory and a temporal knowledge graph; shows *what it was remembering* under each reply
- **Privacy** — incognito (pause all learning), secrets scrubbed before storage, web/file/clipboard content treated as untrusted data
- **Screen / Vision** — capture a region, window, or full screen and ask questions about it
- **PC Control** — open apps, read/write files, clipboard access, run PowerShell — all gated by a security mode system
- **Desktop Shell** — native Tauri + React window with streaming chat, memory management, and settings
- **System Tray** — global hotkeys, mode switching, screen capture, push-to-talk from anywhere

**In preview** (off by default or not yet verified on Windows):
- **MCP tools** — plug in Model Context Protocol servers, gated by security mode (default: armed only). Keep it off until the injection/poisoning defenses land (T03/T04). See [docs/guide/mcp.md](docs/guide/mcp.md).
- **Companion bubble** — a small always-on-top Aura orb on your desktop; click for a mini chat with push-to-talk, `Ctrl+Alt+O` to show/hide.

---

## Stack

| Layer | Technology |
|-------|-----------|
| Chat model | Ollama — `llama3.2:3b` (the `config.example.yaml` default). **Being re-baselined (T02):** first evals favor `qwen2.5:3b`; `qwen2.5:7b` is a common upgrade. |
| Vision | Ollama — `qwen2.5vl:7b` (general + text), `llama3.2-vision:11b` for hard cases, `moondream` fast path |
| Embeddings | Ollama — `nomic-embed-text` |
| Vector memory | mem0 + ChromaDB (on disk, no Docker) |
| STT | faster-whisper — default `base.en` on CPU (**English only**); use a multilingual model (e.g. `large-v3`) on CUDA for Turkish |
| TTS | Orpheus (llama-cpp, local GPU). Edge TTS (cloud) is currently a silent fallback — becoming explicit opt-in (T05) |
| Desktop shell | Tauri v2 + React 19 + Vite + Tailwind |
| Shell API | FastAPI + uvicorn (`127.0.0.1:8765`) |
| Tray | pystray + pynput |
| Evals | Gate A: extraction + tool-calling gold sets, run on real models in CI ([evals/README.md](evals/README.md)) |

---

## Security model

PC control is off by default. Three modes, shared across all interfaces (shell, tray, CLI):

| Mode | What's allowed |
|------|---------------|
| `safe` | Chat, voice, screen, memory, web search — no PC tools |
| `scoped` | Allowlisted apps, file read/write inside your chosen folders, clipboard, URL allowlist |
| `armed` | Full PC control — open anything, write anywhere, run PowerShell |

Every tool call is logged to `logs/tool_audit.jsonl`. Results from files, web pages and the clipboard are wrapped as untrusted data so injected instructions aren't obeyed.

> **Known gap:** `armed` doesn't expire yet — disarm when you're done. Auto-expiry plus per-command confirmation for state-changing PowerShell is planned (T08).

---

## Quick start

**Requirements:** Python 3.11+, [Ollama](https://ollama.com) running (`ollama serve`), an NVIDIA GPU for Orpheus TTS (Edge TTS works without one).

```powershell
# 1. Clone and set up
cd C:\celestia
python -m venv venv
.\venv\Scripts\pip install -r requirements.txt

# 2. Pull the models config.example.yaml uses
ollama pull llama3.2:3b          # chat (llm.chat_model)
ollama pull qwen2.5vl:7b         # screen reading (vision.general_model / text_model)
ollama pull nomic-embed-text     # memory embeddings
# optional: llama3.2-vision:11b (hard screenshots), moondream (fast vision)

# 3. Configure
copy config.example.yaml config.yaml
copy security.policy.example.yaml security.policy.yaml
.\venv\Scripts\python.exe run_celestia.py --trust-config

# 4. Verify everything is working
.\venv\Scripts\python.exe run_celestia.py --check
```

**Desktop shell (recommended):**
```powershell
.\venv\Scripts\python.exe run_celestia.py --shell
```

**Interactive CLI:**
```powershell
.\venv\Scripts\python.exe run_celestia.py -i
```

Type `help` once you're in. Or double-click `start.bat` to launch the desktop shell directly.

---

## Docs

| Doc | What's in it |
|-----|-------------|
| [docs/getting-started.md](docs/getting-started.md) | Full install, config, shell setup |
| [docs/guide/commands.md](docs/guide/commands.md) | Every command and flag |
| [docs/guide/security.md](docs/guide/security.md) | Safe / scoped / armed explained |
| [docs/guide/memory.md](docs/guide/memory.md) | How memory works, how to clean it |
| [docs/guide/vision.md](docs/guide/vision.md) | Screen capture and OCR |
| [docs/guide/skills.md](docs/guide/skills.md) | How to add a new tool |
| [docs/guide/mcp.md](docs/guide/mcp.md) | Plug in MCP servers as tools (preview — gated, audited) |
| [evals/README.md](evals/README.md) | Gate A evals — how to score models, latest results |
| [docs/reference/architecture.md](docs/reference/architecture.md) | Folder map, data flows, API overview |
| [docs/reference/api.md](docs/reference/api.md) | Full shell API reference |
| [docs/testing/checklist.md](docs/testing/checklist.md) | Manual test pass |

Roadmap: [docs/project/roadmap.md](docs/project/roadmap.md) · Current plan: [docs/project/landscape-2026-09.md](docs/project/landscape-2026-09.md) · Planned features: [docs/planned-features/](docs/planned-features/) · Ideas: [docs/project/ideas-backlog.md](docs/project/ideas-backlog.md)
