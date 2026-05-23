# AGENTS.md

## Cursor Cloud specific instructions

### Overview

Celestia is a local AI desktop companion (primarily Windows-targeted) built in Python. The main entry point is `run_celestia.py`. It uses Ollama for LLM inference, ChromaDB for vector memory, and has optional STT/TTS/vision features.

### Required services

| Service | Purpose | Start command |
|---------|---------|---------------|
| **Ollama** | LLM inference (chat + embeddings) | `ollama serve` (background) |

Ollama must be running before any Celestia commands. Pull models from `config.example.yaml` (e.g. `qwen2.5:7b`, `nomic-embed-text`).

### Running the application

- **Preflight check:** `python3 run_celestia.py --check`
- **Single message:** `python3 run_celestia.py "your message"`
- **Interactive REPL:** `python3 run_celestia.py -i`
- **Desktop shell:** `python3 run_celestia.py --shell` (needs Node + Rust; see [shell/README.md](shell/README.md))
- CLI flags and setup: [docs/getting-started.md](docs/getting-started.md), [docs/guide/commands.md](docs/guide/commands.md)

### Configuration

- **`config.yaml`** — mode, models, voice, vision (repo may include an example; copy from `config.example.yaml` if missing).
- **`security.policy.yaml`** — app/URL allowlists and workspaces (see `security.policy.example.yaml`).
- **`.env`** — secrets (gitignored); copy from `.env.example`.

For headless/cloud environments, set in `config.yaml`:

- `voice.stt.enabled: false`
- `voice.tts.provider: edge`
- `vision.enabled: false`
- `ui.tray: false`

### Gotchas

- **No formal test suite** yet. Use `python3 -m py_compile <file>` for syntax checks.
- **`data/` and `logs/`** are gitignored and created at runtime.
- **Orpheus TTS** needs GPU locally; cloud uses `edge` TTS.
- **PC control** (open app, PowerShell) is Windows-specific in practice.
- **Memory default:** Chroma on disk — no Docker. Optional Qdrant: [docs/optional-docker/README.md](docs/optional-docker/README.md).
- After editing `config.yaml` or `security.policy.yaml`, run `python3 run_celestia.py --trust-config`.
- **Desktop shell:** `shell/` is Tauri + React. Local API in `celestia_core/shell_server.py` on `127.0.0.1`. Dev: `--shell-server` then `cd shell && npm run tauri dev`. No secrets in the frontend bundle.

### Backlog / issues

Planned work: [docs/project/backlog.md](docs/project/backlog.md). Linear team **Celestia** mirrors backlog (labels: `short-term`, `long-term`, `optimization`).
