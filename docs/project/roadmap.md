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
| **4 — Product UI** | Tauri shell, Memory page, shell PTT, activity log, quiet UI |

---

## Next cycle (CC-88–CC-113)

From the May 2026 project review. Broken into 5 epics:

| Epic | Tickets | Focus |
|------|---------|-------|
| **Epic 1 — Latency & Streaming** | CC-88–CC-95 | FastAPI migration, SSE streaming, mode hint fix, Ollama timeout |
| **Epic 2 — Companion Voice (M1)** | CC-96–CC-99 | Early TTS, end-of-utterance PTT, reply cap, quiet UI |
| **Epic 3 — Habit Memory (M2)** | CC-100–CC-104 | Signal logger, habit rollup, habit kind, inject router |
| **Epic 4 — Shell UI Completion** | CC-49, CC-105–CC-107 | Vision confirm modal, Activity panel, personality switcher |
| **Epic 5 — Developer Health** | CC-108–CC-113 | API docs, skills guide, troubleshoot guide, pytest, CI |

Execution order: Epic 1 → Epic 2 → Epics 3–5 in parallel.

---

## Companion track (M phases)

Runs alongside the main phase roadmap. M phases focus on memory + conversation feel:

| M phase | Focus | Status |
|---------|-------|--------|
| **M0** | Memory v2 — typed entries, auto-save, budgeted inject, shell Memory page | **Done** |
| **M1** | Streaming voice — first audio in ~1–2s, end-of-utterance PTT, reply caps | Epic 2 above |
| **M2** | Habit memory — signal log, weekly rollup, inject router | Epic 3 above |
| **M3a** | Dialogue manager — listen / answer / brainstorm / vent states (text first) | Backlog |
| **M3b** | Duplex voice — barge-in, mic open while speaking | Backlog |
| **M4** | Proactive companion — speak first on high-confidence habits | Backlog |

Full companion track detail: [companion-roadmap.md](companion-roadmap.md)

---

## Later phases

| Phase | Target |
|-------|--------|
| **3.5** | Linux port (`platform/linux.py`), tray on target distro |
| **5+** | Morning briefing, autostart, installer |

Detail for each planned item: [backlog.md](backlog.md) · Dev workflow: [workflow.md](workflow.md)

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
