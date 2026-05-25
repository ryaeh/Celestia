# Backlog — planned and to-be-added

Features **not shipped yet**. Shipped work is listed in [shipped-audit.md](shipped-audit.md). Phase timeline: [roadmap.md](roadmap.md). Linear views: [linear-views.md](linear-views.md). Dev workflow: [workflow.md](workflow.md).

**Horizon:** `short` · `long` · `opt` (maps to Linear labels `short-term`, `long-term`, `optimization`)

**Status:** `planned` · `exploring` · `deferred`

---

## Custom

| Item | Horizon | Status | Done when |
|------|---------|--------|-----------|
| **Tray/voice in-app session chat** | short | planned | Tray or Phase 4 UI keeps multi-turn history like `-i` without a separate console window; voice uses same session store. |
| **Quiet UI — drop console system messages** | opt | planned | No `[memory] saved`, vision pass spam, or mode lines in default REPL/chat; optional `verbose` or Activity panel only. |

---

## Near term (Phase 3 polish)

| Item | Horizon | Status | Done when |
|------|---------|--------|-----------|
| **Tool risk classes** | short | exploring | Tools tagged low/medium/high; scoped allows low+medium without `arm`; documented in [security.md](../guide/security.md). |

---

## Security and audit

| Item | Horizon | Status | Done when |
|------|---------|--------|-----------|
| **Activity log UI (full)** | long | planned | UI shows tool audit + security events; filterable; replaces reading raw JSONL. |
| **PIN / type ARM to arm** | long | deferred | Optional confirm before armed; configurable in `config.yaml`. |
| **Per-source mode caps** | short | exploring | e.g. tray max `scoped`, CLI max `armed` via config. |

---

## Phase 4 — Product UI

| Item | Horizon | Status | Done when |
|------|---------|--------|-----------|
| **Desktop shell (Tauri)** | long | exploring | v1: `--shell`, Settings, `/status` API; Chat/Personality/Activity later. tk optional via `ui.shell_settings: false`. |
| **Vision confirm in UI** | long | planned | Screenshot preview + confirm in shell; tk dialog optional fallback. |
| **Activity / status panel** | opt | planned | `[vision]`, `[memory]`, `[security]` in panel; REPL quiet by default. |
| **Quiet default output** | opt | planned | Chat stream has no system tags unless verbose; overlaps Activity panel. |
| **Autostart / installer** | long | deferred | Login or service install documented and opt-in. |
| **Per-user personality files** | long | deferred | `personalities/users/<id>.yaml` load by `app.user_id`. |

---

## Ideas (later)

| Item | Horizon | Notes / done when |
|------|---------|-------------------|
| **Wake word / always-listening** | long | Hotword optional; off by default; GPU/privacy called out in guide. |
| **Proactive nudges** | long | Memory/calendar reminders with rate limits. |
| **Focus / do-not-disturb** | opt | Suppress TTS/popups during gaming or calls. |
| **Conversation threads** | long | Named chats; separate memory inject scope. |
| **Skill packs** | long | `skills/<pack>/` drop-in + optional allowlist file. |
| **Undo last PC action** | short | Close last opened app where possible; no file undelete. |
| **Screenshot history** | opt | Ring buffer for re-ask without re-crop. |
| **Model routing** | opt | Small model for chat, large for tools/vision; config-driven. |
| **Offline-only mode** | long | Hard block outbound tools; tray badge. |
| **Export / import memory** | long | Zip `data/chroma` + personalities for new machine. |
| **Plugin MCP tools** | long | Attach MCP servers under scoped rules. |
| **Windows notification read** | long | Toast text in scoped with confirm. |
| **Routine macros** | long | User-defined “work mode” macro (mode + folders + briefing). |

---

## Integrations

| Item | Horizon | Status | Done when |
|------|---------|--------|-----------|
| **VirusTotal check skill** | short | exploring | `virustotal_check_file` / URL; hash-first; confirm before upload; key in `.env`. Research below. |
| **Morning briefing skill** | long | deferred | Calendar/weather/todos from trusted APIs; scoped/armed gates. |
| **Qdrant option** | long | exploring | `memory.vector_store: qdrant` works with [optional-docker](../optional-docker/README.md). |

### VirusTotal (research)

Feasible via API v3: `GET /files/{hash}`, `POST /urls`, ~500 req/day public limit. Personal use only; confirm before file upload (shared dataset). See prior research in git history or Linear **CC-32**.

---

## Platform — Linux (summer)

| Item | Horizon | Status | Done when |
|------|---------|--------|-----------|
| **platform/linux.py** | long | planned | Path rules, XDG workspaces, protected prefixes. |
| **Tray / hotkeys on Linux** | long | planned | X11/Wayland tray; hotkeys via portal or pynput. |
| **open_path via xdg-open** | long | planned | Same allowlist model as Windows. |

---

## Vision and voice

| Item | Horizon | Status | Done when |
|------|---------|--------|-----------|
| **Gaming / low-VRAM profile preset** | opt | exploring | One config preset documented in [performance.md](../reference/performance.md). |

---

## PC control and files

| Item | Horizon | Status | Done when |
|------|---------|--------|-----------|
| **Recursive directory listing (scoped)** | short | exploring | `list_dir` recursive only under workspace roots. |
| **Rename / move in workspace** | long | deferred | Scoped rename/move with confirm; audit logged. |

---

## Developer / ops

| Item | Horizon | Status | Done when |
|------|---------|--------|-----------|
| **Automated test suite** | long | deferred | pytest smoke for scope, url_policy, open_dispatch. |
| **CI on Windows** | long | deferred | GitHub Actions lint + smoke on push. |
| **Config migration tool** | long | deferred | atlas → celestia key migration if still needed. |

---

## Won't do (explicit)

| Item | Reason |
|------|--------|
| Run Celestia as Administrator by default | Blast radius; normal user + UAC |
| Skip vision confirm by default | Privacy and mistakes |
| Docker required for memory | Chroma local is the design |

---

> **How to maintain:** see [workflow.md](workflow.md) for the full process.
