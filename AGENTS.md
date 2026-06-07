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

- **Test suite:** `pytest tests/ -v` (mocks all heavy deps — no Ollama needed). Use `python3 -m py_compile <file>` for quick syntax checks on individual files.
- **`data/` and `logs/`** are gitignored and created at runtime.
- **Orpheus TTS** needs GPU locally; cloud uses `edge` TTS.
- **PC control** (open app, PowerShell) is Windows-specific in practice.
- **Memory default:** Chroma on disk — no Docker. Optional Qdrant: [docs/optional-docker/README.md](docs/optional-docker/README.md).
- After editing `config.yaml` or `security.policy.yaml`, run `python3 run_celestia.py --trust-config`.
- **Desktop shell:** `shell/` is Tauri + React. Local API in `celestia_core/shell_server.py` on `127.0.0.1`. Dev: `--shell-server` then `cd shell && npm run tauri dev`. No secrets in the frontend bundle.

### Commit convention

Every commit that closes a GitHub issue must include a footer line:

```
Closes #<issue-number>
```

GitHub closes the issue automatically on merge to `main`. The commit template (`.gitmessage`) and the `commit-msg` hook both remind you if you forget. To open the issue list: `gh issue list --repo ryaeh/celestia`.

### Running tests

```
pip install -r requirements-dev.txt
pytest tests/ -v
```

CI runs on every push/PR via `.github/workflows/ci.yml` (Ubuntu, Python 3.11). Heavy runtime deps (torch, faster-whisper, mem0, chromadb, etc.) are not installed in CI — they're mocked in all tests.

### Backlog / issues

Tracked in [GitHub Issues](https://github.com/ryaeh/celestia/issues). Roadmap: [docs/project/roadmap.md](docs/project/roadmap.md).
