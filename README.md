# Celestia

A local AI companion for Windows — chat, voice, memory, screen reading, and PC control. Runs entirely on-device via [Ollama](https://ollama.com). No cloud, no API keys, no subscription.

> **Personal project.** Not accepting pull requests or issues from external contributors.  
> Built with the help of [Claude](https://claude.ai) (Anthropic). Made with AI.

---

## What it does

- **Chat** — conversational AI with full session history and memory that persists across restarts
- **Voice** — push-to-talk with local STT (faster-whisper) and TTS (Orpheus or Edge TTS)
- **Memory** — remembers facts, instructions, preferences, and tasks; auto-extracts summaries from conversations
- **Screen / Vision** — capture a region, window, or full screen and ask questions about it
- **PC Control** — open apps, read/write files, clipboard access, run PowerShell — all gated by a security mode system
- **Desktop Shell** — native Tauri + React window with streaming chat, memory management, and settings
- **System Tray** — global hotkeys, mode switching, screen capture, push-to-talk from anywhere

---

## Stack

| Layer | Technology |
|-------|-----------|
| LLM / Vision | Ollama — `qwen2.5:7b`, `qwen2.5vl:7b` |
| Embeddings | Ollama — `nomic-embed-text` |
| Vector memory | mem0 + ChromaDB (on disk, no Docker) |
| STT | faster-whisper (CUDA) |
| TTS | Orpheus (llama-cpp, local GPU) or Edge TTS fallback |
| Desktop shell | Tauri v2 + React 19 + Vite + Tailwind |
| Shell API | FastAPI + uvicorn (`127.0.0.1:8765`) |
| Tray | pystray + pynput |

---

## Security model

PC control is off by default. Three modes, shared across all interfaces (shell, tray, CLI):

| Mode | What's allowed |
|------|---------------|
| `safe` | Chat, voice, screen, memory, web search — no PC tools |
| `scoped` | Allowlisted apps, file read/write inside your chosen folders, clipboard, URL allowlist |
| `armed` | Full PC control — open anything, write anywhere, run PowerShell |

Every tool call is logged to `logs/tool_audit.jsonl`.

---

## Quick start

**Requirements:** Python 3.11+, [Ollama](https://ollama.com) running (`ollama serve`), an NVIDIA GPU for Orpheus TTS (Edge TTS works without one).

```powershell
# 1. Clone and set up
cd C:\celestia
python -m venv venv
.\venv\Scripts\pip install -r requirements.txt

# 2. Pull models
ollama pull qwen2.5:7b
ollama pull qwen2.5vl:7b
ollama pull nomic-embed-text

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

Type `help` once you're in.

**Or double-click** `start_shell.bat` to launch the desktop shell directly.

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
| [docs/reference/architecture.md](docs/reference/architecture.md) | Folder map, data flows, API overview |
| [docs/reference/api.md](docs/reference/api.md) | Full shell API reference |
| [docs/testing/checklist.md](docs/testing/checklist.md) | Manual test pass |
| [CHANGELOG.md](CHANGELOG.md) | What shipped in each phase |

---

## Project status

Active development. Currently in **Phase 4 — Product UI** (Tauri shell, streaming chat, memory page, PTT).

Roadmap: [docs/project/roadmap.md](docs/project/roadmap.md)  
Companion track (voice feel, habit memory): [docs/project/companion-roadmap.md](docs/project/companion-roadmap.md)
