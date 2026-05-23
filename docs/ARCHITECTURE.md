# Atlas architecture (current)

## Single entry

`run_atlas.py` → `celestia_core/` + `skills/`

## Stack

| Role | Technology |
|------|------------|
| Chat + tools | Ollama `llama3.2:3b` |
| Memory | mem0 + **Chroma** (no Docker) |
| STT | faster-whisper (lazy, CUDA) |
| TTS | Orpheus via **llama-cpp-python** in-process + SNAC |
| TTS fallback | edge-tts |
| Vision | Ollama; **qwen2.5vl:7b** for text OCR mode |
| Secrets | `.env` → `HF_TOKEN` |

## TTS (no LM Studio)

Orpheus GGUF loaded in-process; unloads after idle. `Orpheus-FastAPI/` used only as Python library for SNAC decode.

## Vision flow

1. Capture (mss) → 2. Confirm (edge audio + tk preview) → 3. Unload voice models → 4. Vision (text mode = transcribe first) → 5. TTS answer

## PC tools safety

`open_path` / `open_url` only offered when user message contains open/launch/visit/http.

## Config

One file: `config.yaml`. Secrets: `.env` only.

## Legacy

`legacy/` — old Flask servers; do not run for normal use.
