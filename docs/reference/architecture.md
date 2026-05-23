# Architecture (quick)

**Entry:** `run_celestia.py` → `celestia_core/` + `skills/`

**Stack:**

- Chat + tools — Ollama (`llm.chat_model` in config)
- Memory — mem0 + Chroma on disk
- STT — faster-whisper, loads CUDA when needed
- TTS — Orpheus in-process (llama-cpp + SNAC), edge-tts fallback
- Vision — Ollama, often qwen2.5vl for text-heavy screens
- Secrets — `.env` only (`HF_TOKEN`)

**Folders that matter:**

```
celestia_core/     agent, security, scope, config, platform/windows.py
skills/            pc_control, files, vision, stt, tts
ui/tray.py         hotkeys, menus
personalities/     YAML character packs
data/chroma/       memory
data/security_state.json
logs/              tool_audit.jsonl, vision_audit.jsonl
```

**Vision path:** capture → confirm (sound + preview) → maybe unload voice models → model → optional TTS.

**PC tools:** gated by mode + `scope.py`. Opens are often hidden unless your message sounds like “open this.” Tool calls can log to `tool_audit.jsonl`.

One `config.yaml`. `--trust-config` after you change it on purpose.

`legacy/` — old Flask stuff, ignore. `Orpheus-FastAPI/` — SNAC helpers, not a server you run.
