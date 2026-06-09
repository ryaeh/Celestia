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
| **Hardening** | Code-review optimization pass — agent hot path, atomic memory updates, mtime-cached state, seek-based audit tail, voice/PTT cleanup (PRs #92, #93) |
| **Design** | Planned-features design — 11 self-contained briefs incl. the temporal knowledge-graph memory + operating-modes substrates ([`planned-features/`](../planned-features/)) |

---

## In progress

| Phase | Focus |
|-------|--------|
| **4 — Product UI** | Tauri shell, Memory page, shell PTT, activity log, quiet UI |

<!-- UI NOTE (Jun 2026): shell got a design-system overhaul — the Aura presence
     (`shell/src/components/Aura.tsx`), a 6-theme engine (`shell/src/theme.ts`,
     Settings → Appearance), companion-voice chat layout, and all-lucide icons.
     This is the *substrate* for upcoming feature UIs, not the final polish.
     Strategy: features first → each lands its UI surface on this substrate →
     a dedicated "UI overhaul v2" pass after the planned-features cluster lands.
     Per-feature UI surfaces are mapped in planned-features/ROADMAP.md (UI surfaces). -->

> **UI strategy:** Build features first; each feature lands a small UI surface on the
> shell design system (Aura + themes + panels). A cohesive **UI overhaul v2** polish
> pass is deferred until after the planned-features cluster. Surface-per-feature map:
> [`planned-features/ROADMAP.md`](../planned-features/ROADMAP.md) → *UI surfaces*.

> **Performance & QoL backlog:** real-use findings (GPU/VRAM model orchestration, the
> screenshot Fullscreen/Area chooser, markdown rendering, etc.) are tracked in
> [`perf-and-qol-backlog.md`](perf-and-qol-backlog.md). The model-residency manager there
> is the substrate for **Feature 11 (operating modes)**.

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

## Planned features — the companion frontier

The forward roadmap beyond the M-track: 11 designed features that each only work because
Celestia is **local · sees · remembers · acts**. Full delivery plan + dependencies in
[`planned-features/ROADMAP.md`](../planned-features/ROADMAP.md); design briefs in
[`planned-features/`](../planned-features/). Tracking epics: [#94–#104](https://github.com/ryaeh/Celestia/issues?q=is%3Aissue+label%3AFeature+Planned).

Build spine: `07 → 10 → 02/03 → 11 → 04/05 → 01 → 06/08` (with `09` horizontal).

| Phase | Features | Epics |
|-------|----------|-------|
| **F1 — Perception foothold** | 07 Universal read hotkey | [#94](https://github.com/ryaeh/Celestia/issues/94) |
| **F2 — Memory substrate** | 10 Temporal knowledge graph → 02 Time machine, 03 Local RAG | [#95](https://github.com/ryaeh/Celestia/issues/95) · [#96](https://github.com/ryaeh/Celestia/issues/96) · [#97](https://github.com/ryaeh/Celestia/issues/97) |
| **F3 — Control + autonomy** | 11 Operating modes → 04 Scoped autonomy, 05 Macros | [#98](https://github.com/ryaeh/Celestia/issues/98) · [#99](https://github.com/ryaeh/Celestia/issues/99) · [#100](https://github.com/ryaeh/Celestia/issues/100) |
| **F4 — Ambient layer** | 01 Ambient proactivity | [#101](https://github.com/ryaeh/Celestia/issues/101) |
| **F5 — Specializations** | 06 Affective continuity, 08 Privacy guardian | [#102](https://github.com/ryaeh/Celestia/issues/102) · [#103](https://github.com/ryaeh/Celestia/issues/103) |
| **Horizontal** | 09 Adaptive test-time compute | [#104](https://github.com/ryaeh/Celestia/issues/104) |

The flagship is **10 — temporal knowledge-graph memory** (layered semantic/episodic/procedural
+ a time-aware entity graph with versioned-supersede edges). Most other features ride on it.

---

## Later phases

| Phase | Target |
|-------|--------|
| **3.5** | Linux port (`platform/linux.py`), tray on target distro |
| **5+** | Morning briefing, autostart, installer |

Planned work is tracked in [GitHub Issues](https://github.com/ryaeh/Celestia/issues).

---

## Models (RTX 4090 reference)

```powershell
ollama pull qwen2.5:7b
ollama pull qwen2.5vl:7b
ollama pull nomic-embed-text
```

Orpheus: `models/Orpheus-3b-FT-Q8_0.gguf`  
HF token: `C:\celestia\.env` → `HF_TOKEN=...`
