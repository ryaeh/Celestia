# Celestia roadmap

One page: where Celestia is, what's being built next (in order), and what already shipped.

- **Feature designs** → [`planned-features/`](../planned-features/) (briefs 01–12; the [README](../planned-features/README.md) has dependencies, UI surfaces, and the cross-feature analysis)
- **Idea pool** → [ideas-backlog.md](ideas-backlog.md)
- **Perf/GPU + UI V2 plan** → [perf-and-qol-backlog.md](perf-and-qol-backlog.md)
- **Day-to-day tracking** → [GitHub Issues](https://github.com/ryaeh/Celestia/issues)

---

## Where we are (Jun 2026)

The core companion works end-to-end, locally: chat (SSE streaming) + voice (PTT, Orpheus
TTS, Whisper STT) + screen (capture modes, read-screen hotkey) + gated PC control
(safe/scoped/armed) + memory (typed entries, consolidation, **knowledge-graph substrate**,
**lifecycle v1**: importance, recall ranking, decay, keeper pins) + a Tauri shell on its own
design system (Aura, themes) + GPU residency management so models don't fight over VRAM.

Current focus: **living with the graph memory** (tuning extraction quality in real use)
while the next features land in the order below.

---

## Next — the build order

One sequence, one numbering (the brief numbers). Each step ships something you can *feel*,
and lays substrate the next step reuses.

| Order | What | Status |
|-------|------|--------|
| 1 | **07 — Read-screen hotkey** ([#94](https://github.com/ryaeh/Celestia/issues/94)) | ✅ Shipped |
| 2 | **10 — Temporal knowledge-graph memory** ([#95](https://github.com/ryaeh/Celestia/issues/95)) | ✅ Substrate built (store · extract · hybrid recall · `--graph` CLI). Graph viewer/editor lands with UI V2. |
| 3 | **02 — Time machine** ([#96](https://github.com/ryaeh/Celestia/issues/96)) · **03 — Local RAG** ([#97](https://github.com/ryaeh/Celestia/issues/97)) | Next up — both are consumers of the graph. Start 03 with conversation search ([#86](https://github.com/ryaeh/Celestia/issues/86)), the highest-value slice. |
| 4 | **11 — Operating modes** ([#98](https://github.com/ryaeh/Celestia/issues/98)) | Residency substrate (`gpu.py`) ✅; the mode control plane on top is open. Keep it to 3–4 modes at first. |
| 5 | **04 — Scoped autonomy** ([#99](https://github.com/ryaeh/Celestia/issues/99)) · **05 — Macros** ([#100](https://github.com/ryaeh/Celestia/issues/100)) | 04 builds the plan→approve→execute loop; a macro is a *saved* 04 plan. |
| 6 | **01 — Ambient proactivity** ([#101](https://github.com/ryaeh/Celestia/issues/101)) | Last big substrate consumer — comes up already governed by 11's budgets and informed by 12's signal. |
| 7 | **12 — Adaptive user model** ([#105](https://github.com/ryaeh/Celestia/issues/105)) | The personalization layer; **06 Affect is folded into it** ([#102](https://github.com/ryaeh/Celestia/issues/102), only the Aura-mood surface kept). **Signal collection starts much earlier** — it needs weeks of data, so begin as soon as graph ingestion is trusted. |
| — | **08 — Privacy guardian** ([#103](https://github.com/ryaeh/Celestia/issues/103)) | **Descoped.** Cheap 80% (secrets scrubbing + clipboard warnings) ships early as standalone utilities; the full anomaly monitor is a late, optional specialization on 01's daemon. |
| — | **09 — Adaptive test-time compute** ([#104](https://github.com/ryaeh/Celestia/issues/104)) | Horizontal — router-first, and *measure before* building `consensus`. Layer in only when the turn loop is stable. |

**UI V2** is the cohesive polish pass (markdown rendering, cancel/stop, toasts, GPU pill,
model pickers, Settings expansion, the **graph viewer**) and runs **after** the cluster
above starts landing surfaces — features first, polish once. The item list lives in
[perf-and-qol-backlog.md](perf-and-qol-backlog.md).

---

## Watch-outs

Honest risks to keep in view while building the list above. Each is now baked into the
relevant brief as a **Build decision** (see
[`planned-features/README.md`](../planned-features/README.md#build-decisions-jun-2026)).
Two hard gates fall out of them:

- **Gate A — eval set before LLM-stacking.** The extraction gold-set + voice-consistency
  baseline must exist before 02/03/12 ride on the graph, and before 04/09 trust the model.
- **Gate B — privacy off-switch before the first watcher.** Incognito/pause toggle +
  retention policy ship before 01 (or any ambient ingestion in 10) records anything.


- **One builder, twelve briefs.** The real risk is substrate-itis — months of platform work
  with nothing *felt*. Rule: every step must end in a moment Celestia visibly does something
  new for you, not just a new store/daemon/executor.
- **The 7B ceiling.** Extraction, canonicalization, planning, and classification all assume
  the LLM is reliable; qwen2.5:7b is the bottleneck everywhere. Build the eval set
  (voice-consistency tests, extraction gold-set) *before* stacking more LLM-dependent
  features.
- **Privacy debt accrues before the guardian ships.** 01/02/08/12 each record more. The
  incognito toggle + retention policy should ship **before** the first watcher (01), not
  after (Gate B). 08 is descoped to ship the cheap protective utilities early instead.
- **Graph junk compounds.** 7B extraction noise multiplies once 02/03 consume the graph.
  The contradiction inbox + memory health panel (ideas backlog) are prerequisites for
  scaling ingestion, and hybrid recall should be A/B-checked against plain vector recall.
- **Undo is a promise we can't always keep.** 04's undo log works for file ops; it cannot
  un-send a message or un-close an app. v1 autonomy should be file-ops-first with short
  plans.

---

## Later / unscheduled

- Linux port (`platform/linux.py`), tray on target distro
- Installer + first-run wizard (pairs with the **Cookbook** model-recommender idea)
- Morning briefing as a daily ritual, autostart
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

Earlier planning eras (phase numbers 0–5, Linear CC-epics, the M0–M4 companion track) are
preserved in [`../archive/`](../archive/) — their unfinished items were absorbed into the
briefs and backlogs linked at the top.

---

## Locked-in stances

| Choice | Decision |
|--------|----------|
| Chat model | **qwen2.5:7b** — stays. No always-resident 14B (transient idle-time workers may use bigger models). |
| Embeddings | nomic-embed-text via Ollama |
| Identity | Personality/tone **never** changes with modes or adaptation — she adapts *within* herself |
| Memory | Never silently delete — rank down, supersede with history, or ask |
| Stack | FastAPI + Tauri + Ollama + Chroma — no replatforming |
