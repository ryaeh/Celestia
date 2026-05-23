# Roadmap — phases

High-level delivery phases. **Planned work and ideas** live in [backlog.md](backlog.md), not here.

---

## Completed

| Phase | Delivered |
|-------|-----------|
| **0 — Foundation** | Chat, mem0 + Chroma, PC tool scaffolding |
| **1 — Voice** | faster-whisper STT, Orpheus TTS, tray, hotkeys |
| **2 — Screen** | Vision capture, confirm, two-pass text OCR |
| **2.5 — Security** | Safe / scoped / armed, audit log, config integrity |
| **3a — Scoped** | Workspaces, app allowlist, protected paths, `open` gating |
| **3b read** | `file_read`, REPL `read`, direct `open <app>` |
| **3b write** | `file_write`, REPL `write`, overwrite confirm |
| **3c** | Clipboard read/write (scoped), URL allowlist + smart opens, `security.policy.yaml`, `--pick-workspace` |
| **3 polish** | `memory_edit`, tray screen menu, voice confirm option, performance doc |
| **4 spike** | tk settings UI, `--logs`, n8n webhook on mode change |

---

## In progress

| Phase | Focus |
|-------|--------|
| **4 — Product UI** | Tauri shell, folder picker, activity log; quiet chat (system lines → UI or verbose only) |

---

## Later phases

| Phase | Target |
|-------|--------|
| **3.5** | Linux port (`platform/linux.py`), tray on target distro |
| **5+** | Morning briefing, autostart, installer |

Detail for each planned item: [backlog.md](backlog.md)

---

## Models (RTX 4090 reference)

```powershell
ollama pull qwen2.5:7b
ollama pull qwen2.5vl:7b
ollama pull nomic-embed-text
```

Orpheus: `models/Orpheus-3b-FT-Q8_0.gguf`  
HF token: `C:\celestia\.env` → `HF_TOKEN=...`

---

## Session pickup

[resume.md](resume.md)
