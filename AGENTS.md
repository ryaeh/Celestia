# AGENTS.md

## Cursor Cloud specific instructions

### Overview

Celestia is a local AI desktop companion (primarily Windows-targeted) built in Python. The main entry point is `run_celestia.py`. It uses Ollama for LLM inference, ChromaDB for vector memory, and has optional STT/TTS/vision features.

### Required services

| Service | Purpose | Start command |
|---------|---------|---------------|
| **Ollama** | LLM inference (chat + embeddings) | `ollama serve` (background) |

Ollama must be running before any Celestia commands. Required models: `llama3.2:3b` and `nomic-embed-text` (pull with `ollama pull <model>`).

### Running the application

- **Preflight check:** `python3 run_celestia.py --check`
- **Single message:** `python3 run_celestia.py "your message"`
- **Interactive REPL:** `python3 run_celestia.py -i`
- See `docs/SETUP.md` for all CLI flags.

### Configuration

The app reads `config.yaml` (gitignored). If absent it falls back to `config.example.yaml`. For headless/cloud environments, create `config.yaml` from the example and set:
- `voice.stt.enabled: false` (no microphone available)
- `voice.tts.provider: edge` (no GPU/GGUF for Orpheus)
- `vision.enabled: false` (no display for screen capture)
- `ui.tray: false` (no GUI)

### Gotchas

- **No formal linter or test framework** is configured in this repo. Use `python3 -m py_compile <file>` for syntax checking. The `.gitignore` mentions ruff/mypy/pytest caches but no configs exist.
- The `config.yaml` file is gitignored — it must be created locally each session if needed.
- The `data/` and `logs/` directories are gitignored and created at runtime.
- `llama-cpp-python` is installed without CUDA in cloud environments (CPU-only). Orpheus TTS requires GPU; use `edge` TTS provider instead.
- The spaCy warning (`Failed to load spaCy lemma model`) is harmless — optional for mem0 NLP features.
- PC control features (open apps, PowerShell) are Windows-specific and won't work on Linux.
- Memory (ChromaDB) works on disk with no external service; Qdrant is optional (Docker).
