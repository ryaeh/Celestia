# What you actually run

**Need:** Ollama + `run_celestia.py` (everything else is inside that process).

**Don’t need:** Docker for memory, LM Studio, separate whisper/orpheus/mem0 servers, Orpheus-FastAPI running as HTTP.

**Nice to have on disk:**

- `.env` with `HF_TOKEN`
- `models/*.gguf` for Orpheus
- `data/chroma/` after you’ve chatted
- `data/config.trust` after `--trust-config`

**Fresh PC:**

```powershell
cd C:\celestia
.\scripts\setup.ps1
copy .env.example .env
copy config.example.yaml config.yaml
ollama pull qwen2.5:7b
ollama pull qwen2.5vl:7b
ollama pull nomic-embed-text
.\venv\Scripts\python.exe run_celestia.py --trust-config
.\venv\Scripts\python.exe run_celestia.py --check
```

Longer version: [getting-started.md](../getting-started.md)
