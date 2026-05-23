# Optional Docker services

Celestia’s **default** memory backend is **Chroma on disk** — you do not need Docker for normal use.

Use these compose files only when you explicitly want:

| File | Services | When |
|------|----------|------|
| `docker-compose.yml` | Qdrant (port 6333) | `memory.vector_store: qdrant` in `config.yaml` |
| `docker-compose.extra.yml` | n8n, LiveKit | Self-hosted workflows / realtime experiments |

## Commands

From this directory (`docs/optional-docker/`):

```powershell
# Qdrant only
docker compose up -d qdrant

# Qdrant + n8n + LiveKit
docker compose -f docker-compose.yml -f docker-compose.extra.yml up -d
```

Then set `memory.vector_store: qdrant` and run `run_celestia.py --check`.

**Security:** change the default n8n password in `docker-compose.extra.yml` before exposing ports.

Orpheus-FastAPI has its own compose files under `Orpheus-FastAPI/` — unrelated to Celestia’s default TTS path.
