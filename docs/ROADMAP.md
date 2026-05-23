# Celestia — Roadmap

## Done

| Phase | Status |
|-------|--------|
| 0 Foundation | Chat, memory (Chroma), PC tools |
| 1 Voice | STT, Orpheus TTS, tray, hotkeys |
| 2 Screen | Vision + confirm + text two-pass |
| 2.5 Security | Safe / scoped / armed, audit, integrity, rename |
| 3a Scoped | Allowlist apps, protected paths, shared mode |
| 3b read | `file_read` + REPL `read` |

## Phase 3 — remaining

See [PHASE3_SCOPED_ACCESS.md](PHASE3_SCOPED_ACCESS.md).

- [ ] **file_write** under workspaces (with confirm)
- [ ] Clipboard (scoped)
- [ ] n8n + briefings (optional)

## Phase 3.5 / summer — Linux

- [ ] `platform/linux.py` full port
- [ ] Tray/hotkeys on target distro

## Phase 4 — Product UI

- [ ] Tauri (or similar) — settings, scope picker, Activity log
- [ ] Armed / Scoped / Safe toggle
- [ ] Autostart / installer

## Models (4090)

```powershell
ollama pull qwen2.5:7b
ollama pull qwen2.5vl:7b
ollama pull nomic-embed-text
ollama pull llama3.2-vision:11b
```

Orpheus: `models/Orpheus-3b-FT-Q8_0.gguf`  
HF token: `C:\celestia\.env` → `HF_TOKEN=...`

## Resume tomorrow

[RESUME.md](RESUME.md)
