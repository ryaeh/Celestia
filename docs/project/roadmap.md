# Celestia roadmap

One page: where Celestia is, what's being built next (in order), and what already shipped.

- **Current plan** → [landscape-2026-09.md](landscape-2026-09.md) (Sep 2026: T01–T14, D1–D9) as changed by [replan-2026-11.md](replan-2026-11.md) (Nov 2026: T15–T21, D10–D16, new build order)
- **Feature designs** → [`planned-features/`](../planned-features/) (briefs 01–12; the [README](../planned-features/README.md) has dependencies, UI surfaces, and the cross-feature analysis)
- **Idea pool** → [ideas-backlog.md](ideas-backlog.md)
- **Perf/GPU backlog** → [perf-and-qol-backlog.md](perf-and-qol-backlog.md)
- **UI V2 plan** → [ui-v2-plan.md](ui-v2-plan.md) (foundations + phased surfaces)
- **Shell redesign** → [shell-redesign-plan.md](shell-redesign-plan.md) (Console now, Orbit later)
- **Re-plan (Nov 2026, approved)** → [replan-2026-11.md](replan-2026-11.md)
- **Day-to-day tracking** → [GitHub Issues](https://github.com/ryaeh/Celestia/issues)

---

## Where we are (Sep 2026)

The core companion works end-to-end, locally: chat (SSE streaming) + voice (PTT, Orpheus
TTS, Whisper STT) + screen (capture modes, read-screen hotkey) + gated PC control
(safe/scoped/armed) + memory (typed entries, consolidation, temporal knowledge graph,
lifecycle v1, GPU-idle tidy with entity resolution) + privacy basics (incognito, secrets
scrubbing, untrusted-content wrapping, provenance) + a Tauri shell (Aura, themes, UI V2
foundations) + GPU residency management.

**Gate A exists.** The extraction and tool-calling evals, the real-model CI workflow, an MCP
client and the companion overlay bubble are on `main`
([PR #117](https://github.com/ryaeh/Celestia/pull/117), merged Sep 30).

**The plan changed (Sep 2026).** A landscape review turned into a scoped task list:
[`landscape-2026-09.md`](landscape-2026-09.md) (task IDs **T01–T14**, decisions **D1–D9**).
Headline: **security, privacy and model choice come before new agentic features**, and
nothing goes to the cloud silently.

**Re-planned (Nov 2026).** [`replan-2026-11.md`](replan-2026-11.md) was approved on 2026-11-05.
Celestia is now meant to be **distributable** (D10), so the first-run wizard (T18) is P0 and
companion safety basics (T14) are P1. The build order below follows the re-plan.

### Known gaps the plan fixes first

- **Model split decided (T02, #132):** chat `qwen2.5:3b`, background memory `qwen3.5:4b`.
  The old default `llama3.2:3b` kept calling tools on plain chat. GPU runs of 8–9B pending.
- **Voice can silently go to the cloud:** an Orpheus failure falls back to Edge TTS without
  asking. T05 makes cloud voice an explicit opt-in (D5).
- **Armed mode never expires.** T08.

---

## Next — the build order

Revised Nov 2026 per [`replan-2026-11.md` §5](replan-2026-11.md#5-build-order); it replaces
[`landscape-2026-09.md` §5](landscape-2026-09.md#5-revised-build-order). Feature briefs keep
their numbers (`01`–`12`); tasks are `T01`–`T21`.

| Wave | What | Tasks | Status |
|------|------|-------|--------|
| Now | **In flight** — land the Ollama launch gate, finish three-layer memory behind its eval, GPU runs of the 8–12 GB model candidates, then the first-run wizard | #136 (PR #137), T15, T02 → T18 | PR #137 in review; T15 branch large; T02 split chosen (PR #132), GPU runs pending; T18 open |
| 1 | **Trust core** — prompt-injection eval, then widened armed mode (TTL, per-command confirm, Rule-of-Two gate, approval channel), local voice with a Kokoro CPU fallback, companion safety basics | T03 → T08, T05, T14 | T01 done (PR #117); T04 done (PR #133); rest open |
| 2 | **Console shell** (parallel with wave 1) — layout, rail, tool trail; approval card once T08 lands | B0–B2, then B3 | Planned; issues #138–#141 |
| 3 | **Useful every day** — memory recall eval, reminders + local daily brief | T16, T17 | Open |
| 4 | **Acting well** — UI Automation first, plan preview + undo, MCP hardening and 2026-07-28 compatibility | T10 → T12; T11 + T19 | T11 partly built (PR #117, off by default) |
| 5 | **Memory over time** — graph transaction time, then the **time machine** (event-driven, encrypted, exclusion-aware, **no timer screenshots**, D7) + **03** semantic RAG on the same index | T07 → T09, 03 | Open. Store/extract/hybrid recall/tidy shipped; 03 v1 (keyword search, #86) shipped. |
| 6 | **Presence** — barge-in, Orbit voice stage, overlay click-through | T06, A1–A3 | Open |
| 7 | **Ambient and growth** — event nudges from the time machine, macros (05), adaptive user model (12, **no affect inference**, D9), memory MCP server, `SKILL.md` | 01, 05, 12, T20, T21 | Open |

Operating modes (11) shrink to "game mode" and quiet hours if T02 yields one chat+vision model;
the adaptive-compute router (#104) is dropped for now.

**Parallel "feels alive" track** (when there's slack): the companion bubble follow-ups
(click-through, speaking state).

**UI V2** stays the cohesive polish pass ([ui-v2-plan.md](ui-v2-plan.md)); its foundations
shipped Jun 2026 and the rest interleaves with the work above.

**Shell redesign** ([shell-redesign-plan.md](shell-redesign-plan.md), Nov 2026): build
**B · Console** (B0–B4) as the UI V2 target look, then **A · Orbit**, the voice-first stage
(A1–A3). B0–B4 are issues [#138](https://github.com/ryaeh/Celestia/issues/138)–[#142](https://github.com/ryaeh/Celestia/issues/142).
B0–B2 are frontend-only and can start now. B3, the approval card, waits on **T08**
(per-command confirmation); A3 waits on **T06**.

---

## Decisions (Sep 2026)

D1–D9 from [`landscape-2026-09.md` §2](landscape-2026-09.md#2-decisions); D10–D16 from
[`replan-2026-11.md` §6](replan-2026-11.md#6-decisions) (decided 2026-11-05):

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
| D10 | **Distributable.** Celestia is meant to be shared, so the first-run wizard (T18) is P0 and companion safety basics (T14) are P1. |
| D11 | The **Rule of Two** is a design invariant for tools: untrusted input, sensitive access and state change never combine in one turn without a human (T08). |
| D12 | Local TTS fallback is **Kokoro (CPU)**; Edge TTS only as an explicit, labelled opt-in. |
| D13 | A **scheduled brief and reminders** come before any ambient watcher (T17). |
| D14 | The time machine comes **after** approvals, the brief and UI Automation. |
| D15 | API (#135): **read-only memory MCP server first**, REST later; no inbound chat-app bridges until the Rule-of-Two gate ships. |
| D16 | The single-model strategy comes from the T02 GPU run, not from the plan. |

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

- **Installer** — now needed because Celestia is to be distributable (D10); not yet scheduled.
  The first-run wizard and model picker are T18.
- Optional local wake word (openWakeWord), off by default
- Transient GPU-idle grounding worker for 04 click targets (confirm-only)
- Autostart for the daily brief (the brief itself is T17)
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
| Sep 2026 | **Tool-calling eval + real-model CI**, **MCP client** (gated, off by default), **companion overlay bubble**; landscape plan T01–T14 adopted ([PR #117](https://github.com/ryaeh/Celestia/pull/117)) |
| Sep–Oct 2026 | **T02 model split** (chat `qwen2.5:3b`, background `qwen3.5:4b`, PR #132) and **T04 memory-poisoning defense** — origin, quarantine, review list (PR #133) |
| Oct 2026 | **Shell "workbench & companion" redesign** with message times (the model is told the time too); **Ollama launch gate** — start Ollama, run without it, or pull missing models *(PR #137 in review)* |
| Nov 2026 | **Re-plan approved** ([replan-2026-11.md](replan-2026-11.md): T15–T21, D10–D16, distributable) and the **Console** shell redesign planned (B0–B4, issues #138–#142) |

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
