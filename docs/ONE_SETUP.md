# Atlas — one app, minimal extras

## Required

| Piece | Role |
|--------|------|
| **Ollama** | Chat, memory embeddings, vision |
| **`run_atlas.py`** | Everything else in one process |

## Not required

- Docker (memory uses **Chroma** on disk)
- LM Studio
- Separate `mem0_server` / `whisper_server` / `orpheus_server`
- Orpheus-FastAPI as a running server (only SNAC code is imported from that folder)

## Optional files

| File | Purpose |
|------|---------|
| `.env` | `HF_TOKEN` for faster SNAC download |
| `models/*.gguf` | Orpheus voice |
| `data/chroma/` | Long-term memory |

## New PC checklist

```powershell
.\scripts\setup.ps1
copy .env.example .env
# edit .env → HF_TOKEN=...
copy config.example.yaml config.yaml
ollama pull llama3.2:3b
ollama pull nomic-embed-text
ollama pull qwen2.5vl:7b
ollama pull llama3.2-vision:11b
.\venv\Scripts\python.exe run_atlas.py --check
```

Full guide: [SETUP.md](SETUP.md)
