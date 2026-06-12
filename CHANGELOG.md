# Changelog

Notable changes to Celestia, newest first. Reconstructed from git history
(the project predates formal releases — dates are commit dates, not tags).

Format loosely follows [Keep a Changelog](https://keepachangelog.com/).
Roadmap for upcoming work: [`docs/project/roadmap.md`](docs/project/roadmap.md).

---

## Unreleased

### Added
- **Temporal knowledge-graph memory (Feature 10 substrate).** Graph store
  (`skills/memory/graph_store.py`), relation extraction (`graph_extract.py`),
  hybrid graph-walk recall in `build_context`, and a `--graph` CLI to inspect it.
- **Universal read-screen hotkey** (`celestia_core/shell_read_hotkey.py`) + an
  **Activity feed** (`skills/memory/activity_feed.py`).
- **Model-residency manager** (`celestia_core/gpu.py`) — process-wide GPU lock so
  vision, STT, graph-extraction, and chat never load simultaneously. Substrate for
  Feature 11 (operating modes).
- **Shell design-system overhaul** — Aura presence (`shell/src/components/Aura.tsx`),
  a 6-theme engine (`shell/src/theme.ts`, Settings → Appearance), companion-voice
  chat layout, all-lucide icons, and an auto-growing chat input.
- **Planned-features design corpus** — 12 self-contained briefs in
  [`docs/planned-features/`](docs/planned-features/) plus tracking issues (#94–#105);
  build order lives in [`docs/project/roadmap.md`](docs/project/roadmap.md).

### Changed
- **Fast-by-default vision** — `moondream` for general screenshots, escalate to
  `qwen2.5vl:7b` / `llama3.2-vision:11b` only for hard/text-heavy cases.
- **Agent turn loop refactor** — `_prepare_messages` / `_sync_tool_rounds` extraction,
  `execute_tool` if-chain replaced with a dispatch table, `llm.max_tokens` support,
  idle-debounced consolidation, removal of the old `_honest_reply` / `_OPEN_TRIGGERS`
  heuristics.
- **Code-review optimization pass** — single memory search per turn, hoisted
  `tool_schemas`, atomic `update_entry`, single-fetch consolidation, mtime-cached
  state reads, `/status` TTL cache, seek-based audit-tail.

### Fixed
- **Security-state writes** are now atomic and cross-process locked via a shared
  `celestia_core/file_utils.py` `_file_lock`; vision history + activity feed writes
  locked too. Dead-code sweep.
- **GPU freeze** — vision model no longer stacks on the resident chat model in VRAM
  (`vision.unload_chat_model`, `vision.keep_alive` safety floor).
- Chat switching no longer blocks on graph extraction; new chats finalize in the
  background.

### Docs
- Full codebase audit ([`docs/archive/audit-2026-06.txt`](docs/archive/audit-2026-06.txt)).
- Docs reorganization (Jun 2026): archived finished plans, merged the companion
  M-track into the roadmap, added an [ideas backlog](docs/project/ideas-backlog.md),
  recreated this changelog.

---

## Phase history (shipped)

The product grew in phases rather than tagged releases. Summary from
[`docs/project/roadmap.md`](docs/project/roadmap.md):

| Phase | Delivered |
|-------|-----------|
| **0 — Foundation** | Chat, mem0 + Chroma, PC tool scaffolding |
| **1 — Voice** | faster-whisper STT, Orpheus TTS, tray, hotkeys |
| **2 — Screen** | Vision capture, confirm, two-pass text OCR |
| **2.5 — Security** | Safe / scoped / armed, audit log, config integrity |
| **3a — Scoped** | Workspaces, app allowlist, protected paths, `open` gating |
| **3b — Read/Write** | `file_read` / `file_write`, REPL read/write, overwrite confirm |
| **3c** | Clipboard (scoped), URL allowlist + smart opens, `security.policy.yaml`, `--pick-workspace` |
| **3 polish** | `memory_edit`, tray screen menu, voice confirm option, performance doc |
| **4 spike** | tk settings UI, `--logs`, n8n webhook on mode change |
| **4 — Product UI** *(in progress)* | Tauri shell, Memory page, shell PTT, activity log, quiet UI |
| **M0 — Memory v2** | Typed entries, auto-save, budgeted inject, shell Memory page |

### Early milestones (commit dates)

- **2026-05-23** — Initial commit; security policy, smart URL opens, Phase 3 features.
- **2026-05-24** — Tauri desktop shell, chat API, security polish.
- **2026-05-25** — FastAPI migration, SSE streaming, auth token, pipelined TTS,
  Tailwind + shadcn migration, mem0 Ollama config + faillog.
- **2026-05-26** — Settings overhaul, web skills, STT improvements, voice reply cap;
  vision in-chat confirm, screenshot history, morning briefing, PTT toggle.
- **2026-06-07** — Repo hygiene: split `run_celestia.py`, per-session storage,
  GitHub-only workflow, README rewrite, CI workflow.
- **2026-06-08** — Test suite expansion + the first code-review optimization PRs (#92, #93).
- **2026-06-09** — Knowledge-graph substrate, read-screen hotkey, shell UI overhaul.
- **2026-06-10** — GPU residency manager, fast vision, atomic/locked security state.
