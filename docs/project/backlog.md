# Backlog — planned and to-be-added

Features **not shipped yet**, or only sketched in code/config. Use this doc to track ideas; [roadmap.md](roadmap.md) stays the phase timeline.

**Status legend:** `planned` · `exploring` · `deferred`

---

## Custom (user ideas)

Add rows here when you have new features beyond the phases below.

| Item | Status | Notes |
|------|--------|-------|
| **Session chat memory (tray/voice)** | planned | Tray multi-turn chat: same history as `-i` |
| **Quiet UI — drop console system messages** | planned | After Phase 4 UI: stop printing `[memory] saved: …`, vision pass spam (`pass 1/2`, capture mode), security mode lines, tray status noise; emotion/expression chatter (`<laugh>`, tag hints) only in UI or optional `verbose` / Activity panel — REPL stays clean, chat feels like a person not a log |

---

## Near term (Phase 3)

| Item | Status | Notes |
|------|--------|-------|
| **Tool risk classes** | exploring | Tag tools low/medium/high; scoped allows low+medium without arm |
| **tray_max_mode** | exploring | e.g. tray voice never exceeds `scoped` unless config allows |

---

## Security and audit (polish)

| Item | Status | Notes |
|------|--------|-------|
| **Activity log UI (full)** | planned | Phase 4 — richer than settings spike |
| **PIN / type ARM to arm** | deferred | Optional gate before armed mode |
| **Per-source mode caps** | exploring | Different max mode for tray vs CLI |

---

## Phase 4 — Product UI

| Item | Status | Notes |
|------|--------|-------|
| **Desktop shell (Tauri)** | planned | Replace minimal tk settings |
| **Vision confirm in UI** | planned | Replace or supplement tk preview |
| **Activity / status panel** | planned | Absorb today's console `[vision]`, `[memory]`, `[security]` lines — optional "developer verbose" toggle |
| **Quiet default output** | planned | Same as Custom row: no system messages in chat stream; memory save + expression tags invisible unless verbose |
| **Autostart / installer** | deferred | Windows service or login startup |
| **Per-user personality files** | deferred | `personalities/users/<id>.yaml` |

---

## Ideas (worth a look later)

Not committed — good fits for Celestia beyond current phases.

| Item | Notes |
|------|--------|
| **Wake word / always-listening** | Optional "Celestia" hotword; heavy on GPU and privacy — off by default |
| **Proactive nudges** | "You asked me to remind you…" from memory or calendar; needs rules so she's not annoying |
| **Focus / do-not-disturb** | Suppress TTS and popups while gaming or in a call |
| **Conversation threads** | Named chats (work / personal) with separate memory inject scope |
| **Skill packs** | Drop-in folders: `skills/github/`, `skills/spotify/` with their own allowlists |
| **Undo last PC action** | One-step rollback where possible (close app we opened, not delete file) |
| **Screenshot history** | Local ring buffer of recent captures for re-ask without re-crop |
| **Model routing** | Fast model for chit-chat, bigger model when tools or vision needed |
| **Offline-only mode** | Hard block outbound URLs/tools; badge in tray |
| **Export / import memory** | Backup `data/chroma` + personality as a zip for new machine |
| **Plugin MCP tools** | Let power users attach MCP servers under scoped rules |
| **Windows notification read** | Read toast text in scoped mode (privacy confirm) |
| **Routine macros** | "Start work mode" → scoped + open projects folder + briefing — user-defined |

---

## Integrations

| Item | Status | Notes |
|------|--------|-------|
| **VirusTotal check skill** | exploring | See research below — file hash lookup + URL/domain scan via VT API v3; natural phrases: “check X file on VirusTotal”, “is Y site flagged?” |
| **Morning briefing skill** | deferred | Calendar, weather, todos — needs trusted sources |
| **Qdrant option** | exploring | Config stub exists; Chroma is default |

### VirusTotal integration (research — not implemented)

**Verdict: feasible** for personal use as an optional skill + tool(s), with clear limits.

| Capability | API (v3) | Celestia fit |
|------------|----------|----------------|
| **File already known to VT** | `GET /files/{sha256}` (or MD5/SHA1) | Compute hash locally, no upload — fast, lower privacy risk |
| **Unknown file** | `POST /files` (upload) | Works, but **uploads enter VT’s dataset** unless Premium **Private Scanning** — must **confirm** before upload |
| **Website / URL** | `POST /urls` → poll `GET /analyses/{id}` or `GET /urls/{url_id}` | Async (seconds–minutes); AI summarizes `last_analysis_stats` (malicious / suspicious / harmless counts) |
| **Domain only** | `GET /domains/{domain}` | “Check example.com” without full URL path |

**Requirements:** free [VirusTotal API key](https://www.virustotal.com/gui/join-us) in `.env` (e.g. `VIRUSTOTAL_API_KEY`), never committed. HTTP client only (`requests` / `httpx`).

**Public API limits (important):** ~**500 requests/day**, **4/minute** ([public vs premium](https://docs.virustotal.com/reference/public-vs-premium-api)). Fine for occasional “check this file/site”; not for scanning folders or monitoring. Premium removes caps and adds private file scan.

**Terms / usage:** Public API is for **non-commercial** use and has rules about automated workflows — treat as **personal assistant**, not a product backend. Heavy or commercial use needs Premium.

**Security / scoped mode ideas (when built):**

- Tool only in **scoped** or **armed**, with explicit user intent (no background scanning).
- **Hash lookup first**; upload only after confirm (“This file isn’t in VT yet — upload for scan?”).
- URL checks: normalize URL; optional tie-in with `url_allowlist` is separate (VT check is user-requested, not auto on every open).
- Never log API key; audit log records hash/URL checked, not file bytes.

**Simpler fallback (no API):** open `https://www.virustotal.com/gui/file/{sha256}` or URL report in browser — zero quota, user reads the page; weaker for “tell me if it flags” in chat.

**Suggested tools (future):** `virustotal_check_file`, `virustotal_check_url` (or one tool with `kind`); agent summarizes engines flagged vs clean.

---

## Platform — Linux (summer target)

| Item | Status | Notes |
|------|--------|-------|
| **platform/linux.py** | planned | Path rules, protected prefixes, XDG workspaces |
| **Tray / hotkeys on Linux** | planned | X11/Wayland; portal or pynput |
| **open_path via xdg-open** | planned | Same allowlist model as Windows |

---

## Vision and voice

| Item | Status | Notes |
|------|--------|-------|
| **Gaming / low-VRAM profile UI preset** | exploring | See [reference/performance.md](../reference/performance.md) |

---

## PC control and files

| Item | Status | Notes |
|------|--------|-------|
| **Recursive directory listing (scoped)** | exploring | List dir under workspace only |
| **Rename / move in workspace** | deferred | Higher risk; confirm heavily |
| **More built-in apps in allowlist** | exploring | snippingtool, etc. — config-driven |

---

## Developer / ops

| Item | Status | Notes |
|------|--------|-------|
| **Automated test suite** | deferred | Today: [testing/checklist.md](../testing/checklist.md) manual only |
| **CI on Windows** | deferred | Lint + smoke tests |
| **Config migration tool** | deferred | atlas → celestia keys if needed |

---

## Won't do (explicit)

| Item | Reason |
|------|--------|
| Run Celestia as Administrator by default | Expands blast radius; use normal user + UAC |
| Skip vision confirm by default | Privacy and mistake prevention |
| Docker required for memory | Chroma local is the design |

---

## How to add an idea

1. Add a row to the best section above with `planned` or `exploring`.  
2. If it changes phase boundaries, note it in [roadmap.md](roadmap.md).  
3. When shipped, **remove** from this file and document behavior in the [user guide](../README.md#user-guide).
