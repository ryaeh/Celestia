# Celestia roadmap

One page: where Celestia is, what's being built next (in order), and what already shipped.

- **Current plan (Sep 2026)** → [landscape-2026-09.md](landscape-2026-09.md) — tasks T01–T14, decisions D1–D9
- **Feature designs** → [`planned-features/`](../planned-features/) (briefs 01–12; the [README](../planned-features/README.md) has dependencies, UI surfaces, and the cross-feature analysis)
- **Idea pool** → [ideas-backlog.md](ideas-backlog.md)
- **Perf/GPU backlog** → [perf-and-qol-backlog.md](perf-and-qol-backlog.md)
- **UI V2 plan** → [ui-v2-plan.md](ui-v2-plan.md) (foundations + phased surfaces)
- **Day-to-day tracking** → [GitHub Issues](https://github.com/ryaeh/Celestia/issues)

---

## Where we are (Sep 2026)

The core companion works end-to-end, locally: chat (SSE streaming) + voice (PTT, Orpheus
TTS, Whisper STT) + screen (capture modes, read-screen hotkey) + gated PC control
(safe/scoped/armed) + memory (typed entries, consolidation, temporal knowledge graph,
lifecycle v1, GPU-idle tidy with entity resolution) + privacy basics (incognito, secrets
scrubbing, untrusted-content wrapping, provenance) + a Tauri shell (Aura, themes, UI V2
foundations) + GPU residency management.

**Gate A exists.** The extraction eval is on `main`; the tool-calling eval, the real-model
CI workflow, an MCP client and the companion overlay bubble are in review in
[PR #117](https://github.com/ryaeh/Celestia/pull/117).

**The plan changed (Sep 2026).** A landscape review turned into a scoped task list:
[`landscape-2026-09.md`](landscape-2026-09.md) (task IDs **T01–T14**, decisions **D1–D9**).
Headline: **security, privacy and model choice come before new agentic features**, and
nothing goes to the cloud silently. The build order below follows it.

### Known gaps the plan fixes first

- **Model split decided (T02, #132):** chat `qwen2.5:3b`, background memory `qwen3.5:4b`.
  The old default `llama3.2:3b` kept calling tools on plain chat. GPU runs of 8–9B pending.
- **Voice can silently go to the cloud:** an Orpheus failure falls back to Edge TTS without
  asking. T05 makes cloud voice an explicit opt-in (D5).
- **Armed mode never expires.** T08.

---

## Next — the build order

Revised Sep 2026 per [`landscape-2026-09.md` §5](landscape-2026-09.md#5-revised-build-order).
Feature briefs keep their numbers (`01`–`12`); tasks are `T01`–`T14`.

| Order | What | Tasks | Status |
|-------|------|-------|--------|
| 1 | **Security & model sprint** — evals on `main`, model re-baseline, prompt-injection eval, memory-poisoning defense, no silent cloud voice | T01 → T02, T03, T04, T05 | T01 done (PR #117); T02 PR #132, T04 PR #133 in review; T03, T05 open |
| 2 | **Finish 10 — graph** — transaction-time (`invalidated_at`, as-of queries) | T07 | Open. Store/extract/hybrid recall/tidy already shipped. |
| 3 | **02 — Time machine** on the privacy design (event-driven, encrypted, exclusion-aware; **no timer screenshots**, D7) + **03** semantic RAG on the same index | T09 | Open. 03 v1 (keyword conversation search, #86) shipped. |
| 4 | **11 — Operating modes, reduced** — smaller if T02 yields one chat+vision model | — | Residency substrate (`gpu.py`) shipped |
| 5 | **04 — Scoped autonomy** — armed TTL + per-command confirm, UI Automation first, gated MCP, plan preview + undo journal; then **05 macros** | T08, T10, T11, T12 | T11 partly built (PR #117, off by default) |
| 6 | **01 — Ambient proactivity** — nudges from 02's event stream only | — | Open |
| 7 | **12 — Adaptive user model** — tastes + rhythms, **no affect inference** (D9) | — | Open |

**Parallel "feels alive" track** (when there's slack): T06 voice barge-in; the companion
bubble follow-ups (click-through, speaking state).

**UI V2** stays the cohesive polish pass ([ui-v2-plan.md](ui-v2-plan.md)); its foundations
shipped Jun 2026 and the rest interleaves with the work above.

---

## Decisions (Sep 2026)

From [`landscape-2026-09.md` §2](landscape-2026-09.md#2-decisions):

| # | Decision |
|---|----------|
| D1 | Security and privacy work comes **before** new agentic features (01, 04, MCP). |
| D2 | Model swap only via Gate A evals (T02). |
| D3 | No always-resident 14B+. Big/MoE/GUI models only as transient GPU-idle workers. |
| D4 | Keep mem0 + SQLite graph. No Graphiti/Zep migration. |
| D5 | No cloud calls by default. Edge TTS becomes an explicit opt-in. |
| D6 | MCP sits **alongside** `skills/registry.py` as a gated client; it doesn't replace it. |
| D7 | Time machine capture is event-driven, encrypted and exclusion-aware — never timer-based screenshots. |
| D8 | Screen understanding: Windows UI Automation first, VLM fallback; VLM-grounded clicks always need confirmation. |
| D9 | Descoped: pixel-level "click anywhere" agent, emotion inference in 12, Linux port. |

**Positioning:** a free, offline Windows companion on an 8–12 GB NVIDIA GPU that sees the
screen, keeps an inspectable time-aware memory, acts only through audited, gated, undoable
permissions. If a cloud assistant or a local chat
frontend does something equally well, it's out of scope.

---

## Watch-outs

The two hard gates still hold:

- **Gate A — eval set before LLM-stacking.** Extraction + tool-calling evals exist (T01
  lands the second on `main`); a prompt-injection track (T03) is
  next. Single CPU runs vary by ~±5 points — compare models on repeated runs.
- **Gate B — privacy off-switch before the first watcher.** Incognito shipped; the time
  machine (T09) adds exclusions, encryption, retention and "forget last hour/day" before it
  records anything.

- **One builder, many briefs.** Every step must end in something Celestia visibly does, not
  just a new store/daemon/executor.
- **The small-model ceiling.** Extraction, planning and classification all lean on a 3–9B
  model. Measure (T02) before stacking features on it.
- **Memory is an attack surface.** Injected text can become a stored "instruction"
  (OWASP ASI06). T04 adds origin tracking + quarantine before ingestion grows.
- **MCP is a supply-chain risk.** Tool-description poisoning and "rug-pull" manifest changes
  are real; the client stays off by default until T03/T04 and manifest pinning (T11) land.
- **Undo is a promise we can't always keep.** 04 v1 is file-ops-first with short plans and a
  reversible journal (T12); irreversible actions always confirm.

---

## Later / unscheduled

- Installer + first-run wizard (pairs with the **Cookbook** model-recommender idea)
- Optional local wake word (openWakeWord), off by default
- Celestia memory as a local read-only MCP server
- Transient GPU-idle grounding worker for 04 click targets (confirm-only)
- Morning briefing as a daily ritual, autostart
- Linux port — **someday** (D9)
- Everything in [ideas-backlog.md](ideas-backlog.md) not yet promoted

---

## Shipped — the story so far

Kept as the growth record, condensed. Details: [`CHANGELOG.md`](../../CHANGELOG.md).

| When | Milestone |
|------|-----------|
| May 2026 | **Foundation → PC control** — chat, mem0+Chroma memory, voice (Whisper STT, Orpheus TTS, tray, hotkeys), vision (capture, confirm, two-pass OCR), security modes (safe/scoped/armed, audit log, config integrity), scoped workspaces, file read/write, clipboard, URL allowlist |
| May 2026 | **Product UI** — Tauri shell, FastAPI + SSE streaming, auth token, Memory page, shell PTT, Tailwind+shadcn, settings UI |
| Jun 2026 (early) | **Hardening** — agent hot path, atomic memory updates, mtime-cached state, locked cross-process writes, seek-based audit tail, shell_server tests, full codebase [audit](../archive/audit-2026-06.txt) |
| Jun 2026 | **Memory v2 → v3 substrate** — typed entries + consolidation (M0); then the temporal knowledge graph (store, extraction, hybrid recall) and lifecycle v1 (importance, recall ranking, TTL decay, keeper pins, Memory-page controls) |
| Jun 2026 | **Perception + GPU** — read-screen hotkey, Activity feed, per-monitor/region/active-window capture, fast-by-default vision, model-residency manager (`gpu.py`) |
| Jun 2026 | **Shell design system** — Aura presence, 6-theme engine, companion-voice layout, auto-growing input |
| Jun 2026 | **Design corpus** — 12 planned-feature briefs + this roadmap; docs reorganized |
| Jun 2026 (mid) | **Privacy + trust basics (Gate B)** — incognito / pause-learning, secrets scrubbing before storage, untrusted-content wrapping for tool results, "why did you say that?" provenance, policy-file integrity, conversation search (03 v1) |
| Jun 2026 (mid) | **UI V2 foundations** — markdown rendering, toasts, cancel/stop, `/ws/state` live-state channel, GPU HUD |
| Jul 2026 | **Gate A (extraction) + GPU-idle tidy** — extraction gold set + scoring runner; idle daemon with graph entity resolution (Phase 2) |
| Sep 2026 *(in review, PR #117)* | **Tool-calling eval + real-model CI**, **MCP client** (gated, off by default), **companion overlay bubble**; landscape plan T01–T14 adopted |

Earlier planning eras (phase numbers 0–5, Linear CC-epics, the M0–M4 companion track) are
preserved in [`../archive/`](../archive/) — their unfinished items were absorbed into the
briefs and backlogs linked at the top.

---

## Locked-in stances

| Choice | Decision |
|--------|----------|
| Chat model | **`qwen2.5:3b`** (T02 CPU evals, English cases, 3 repeats: pass 0.90 vs 0.69 for the old `llama3.2:3b`, far fewer stray tool calls). 8–9B GPU candidates still to test. No always-resident 14B+ (D3). |
| Memory model | **`qwen3.5:4b`**, thinking off, for consolidation + graph extraction (extraction F1 0.69 vs 0.07 for the chat model). Background only. |
| Voice | Local by default: Whisper STT + Orpheus TTS. Cloud voice (Edge) only as an explicit opt-in (D5, T05). |
| Embeddings | nomic-embed-text via Ollama |
| Identity | Personality/tone **never** changes with modes or adaptation — she adapts *within* herself |
| Memory | Never silently delete — rank down, supersede with history, or ask |
| Memory store | mem0 + Chroma + SQLite graph — no Graphiti/Zep (D4) |
| Tools | `skills/registry.py` stays the dispatch layer; MCP is an extra, gated client (D6) |
| Stack | FastAPI + Tauri + Ollama + Chroma — no replatforming |
