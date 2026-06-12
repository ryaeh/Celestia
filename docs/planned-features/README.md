# Planned features

Exploratory feature concepts for Celestia. These are **proposals**, not commitments —
each doc is a self-contained brief. This index does the cross-feature analysis:
what they share, how they reinforce each other, and the order that unlocks the most
with the least rework.

**Build order + status:** the single project roadmap at
[`../project/roadmap.md`](../project/roadmap.md) (tracking epics
[#94–#105](https://github.com/ryaeh/Celestia/issues)). This README holds the analysis:
pillars, synergies, shared substrates, UI surfaces, and the map to older issues.

## The four pillars (why these features and not generic ones)

Celestia's structural advantages over a cloud chatbot:

1. **Local** — runs on-device via Ollama; data never leaves the machine.
2. **Sees** — screen capture + vision (`skills/vision/`).
3. **Remembers** — persistent memory + session distillation (`skills/memory/`).
4. **Acts** — gated PC control (`skills/pc_control/`, `celestia_core/security.py`).

Every feature below is chosen because it only works well when several pillars are true
at once. Anything a cloud assistant could do equally well is out of scope.

## The features

| # | Feature | Pillars | Primary subsystem |
|---|---------|---------|-------------------|
| [01](01-ambient-proactivity.md) | Ambient proactivity | Sees · Remembers · Acts | new watcher loop + vision |
| [02](02-time-machine.md) | Time machine / episodic memory | Remembers · Local | `session_consolidate` + memory |
| [03](03-local-rag.md) | Local RAG over your stuff | Remembers · Local | Chroma index |
| [04](04-scoped-autonomy.md) | Scoped autonomy + visible plan | Acts | agent loop + security modes |
| [05](05-macros-rituals.md) | Recordable macros / rituals | Acts · Local | pc_control + scheduler |
| [06](06-affective-continuity.md) | Affective continuity | Remembers | memory + personalities |
| [07](07-universal-read-hotkey.md) | Universal "read screen" hotkey | Sees | vision + hotkey |
| [08](08-privacy-guardian.md) | Local privacy guardian | Sees · Acts · Local | watcher loop + security |
| [09](09-adaptive-test-time-compute.md) | Adaptive test-time compute | Local | agent turn loop |
| [10](10-temporal-knowledge-graph.md) | Temporal knowledge-graph memory | Remembers · Local · Sees | new memory substrate |
| [11](11-operating-modes.md) | Operating modes | Local · Acts | new control plane (modes) |
| [12](12-adaptive-user-model.md) | Adaptive user model (living portrait) | Remembers · Local · Sees | rides the `10` graph |

`09` is a **horizontal enhancer**, not a user-facing companion feature: it makes every
other feature reason better at a fixed model size by spending more inference compute only
on hard turns. It's listed apart from the 8×8 matrix below for that reason — it composes
with all of them rather than competing. Strongest payoff with **04 Autonomy** (better
plans) and **03 RAG** (reasoning over retrieved context); cheap to pair with **01 Ambient**
(rare nudges can afford deep compute).

`10` and `11` are **substrates**, not single features. `10 Temporal knowledge-graph memory`
replaces the ad-hoc stores the memory cluster (`02`/`03`/`06`) implies with one structured,
time-aware graph — those features become *consumers* of it. `11 Operating modes` is the
control plane that makes the whole on-device stack affordable: it budgets VRAM, toggles which
features (and the memory extraction pass) are live, sets the ingestion tier `10` records, and
fixes proactivity + default security per context. Both sit apart from the 8×8 matrix because
nearly everything else rides on them.

`12 Adaptive user model` is the personalization layer on top of `10`: where the graph models
the user's *world*, `12` models the *user* — graded tastes, daily rhythms, and reaction
learning (how the user responds to Celestia tunes her behavior). It stores its portrait as
graph entries, so `10`'s supersede/history/inspect-UI mechanics come for free; it absorbs
`06`'s substrate and supplies `01` with "is this a good moment" judgment.

## Shared building blocks

The features are not independent — they cluster around a handful of new substrates.
Building a block once pays off across every feature that depends on it.

| Building block | Status | Feeds features |
|----------------|--------|----------------|
| **Observation daemon** (debounced background watch loop, quiet-hours aware) | new | 01, 08 |
| **Vision/OCR pipeline** (capture → OCR → vision model) | exists, extend | 01, 03, 07, 08 |
| **Episodic store** (timeline entries in Chroma + retrieval) | new on memory | 02, 03, 06 |
| **Scheduler / cron** (time + event triggers) | new | 01, 02, 05 |
| **Multi-step executor** (plan → approve → run with live checklist) | new on agent | 04, 05, 08 |
| **Security modes** (`safe`/`scoped`/`armed`) | exists | 01, 04, 05, 08, 11 |
| **Global hotkey infra** (`shell_ptt.py`) | exists | 07, 04, 11 |
| **Temporal knowledge graph** (nodes/edges + valid_from/until, hybrid retrieval) | new on memory | 02, 03, 06, 10 |
| **Mode control plane** (residency/VRAM + feature toggles + ingestion + behavior per mode) | new | 01, 04, 10, 11 |
| **Entity extraction + resolution** (inline-light + deep-bg, embedding-prefilter + LLM canonicalize) | new on `session_consolidate` | 10 |

Three natural clusters fall out of this:

- **Perception cluster (07 → 01 → 08):** all share the vision/OCR pipeline. `07` is the
  *manual* trigger, `01` *automates* the trigger via the observation daemon, `08` is `01`
  pointed at a security lens. Same plumbing, increasing autonomy.
- **Memory cluster (02 + 03 + 06):** all extend Chroma/mem0. `02` and `03` share an
  index+retrieve substrate; `06` rides on `02`'s episodic data.
- **Action cluster (04 + 05):** share the multi-step executor. `05` is essentially a
  *saved, replayable* `04` plan. Both want the scheduler.

## Synergy matrix

How strongly each pair reinforces the other. ●●● = one feeds the other directly /
shares core code · ●● = clear synergy · ● = mild · — = independent.

|        | 01 | 02 | 03 | 04 | 05 | 06 | 07 | 08 |
|--------|----|----|----|----|----|----|----|----|
| **01 Ambient**   | —   | ●●● | ●  | ●●● | ●● | ●● | ●● | ●●● |
| **02 Time machine** | ●●● | —   | ●●● | ●  | ●● | ●●● | ●  | ●  |
| **03 RAG**       | ●   | ●●● | —  | ●● | ●  | ●● | ●● | ●  |
| **04 Autonomy**  | ●●● | ●   | ●● | —   | ●●● | ●  | ●● | ●●● |
| **05 Macros**    | ●●  | ●●  | ●  | ●●● | —   | ●  | ●  | ●● |
| **06 Affect**    | ●●  | ●●● | ●● | ●  | ●  | —   | ●  | ●  |
| **07 Hotkey**    | ●●  | ●   | ●● | ●● | ●  | ●  | —   | ●● |
| **08 Guardian**  | ●●● | ●   | ●  | ●●● | ●● | ●  | ●● | —   |

### The high-value loops (●●● pairs worth designing for explicitly)

- **01 → 02:** ambient observations become timeline entries automatically. The watcher is
  the *ingestion engine* for episodic memory — build them to share a write path.
- **02 → 03:** the timeline is itself a RAG corpus. "Ask my day / week" is just RAG over
  episodic memory — one retrieval substrate serves both.
- **01 → 04:** the full companion loop — *observe → propose a plan → act on approval*.
  Ambient detects a situation; autonomy resolves it. This is the flagship combination.
- **04 ↔ 05:** a macro is a saved autonomy plan; replaying a macro runs through the same
  executor. Build one executor, get both.
- **02 → 06:** affective continuity reads from episodic memory ("last time you were
  stressed about this deadline…"). No separate mood store needed if `02` exists.
- **01 → 08:** the guardian is the observation daemon with a security-classifier instead
  of a helpfulness-classifier. Same loop, different prompt + ruleset.

## Recommended build order

Sequenced so each phase stands alone *and* lays a substrate the next phase reuses.

**Phase 1 — Perception foothold:** `07 Universal hotkey`.
Smallest, fully manual, ships the vision/OCR pipeline improvements with zero autonomy
risk. Immediately useful. No new daemons.

**Phase 2 — Memory substrate:** `02 Time machine`, then `03 RAG`.
Build the episodic store; `03` reuses its index+retrieve. Unlocks "ask my day/files".

**Phase 3 — Autonomy substrate:** `04 Scoped autonomy`, then `05 Macros`.
Build the plan→approve→execute loop behind the existing security modes; `05` saves plans.

**Phase 4 — Ambient layer:** `01 Ambient proactivity`.
Now the observation daemon can feed `02` (timeline), trigger `04` (plans), and reuse the
quiet-hours/scheduler from `05`. Highest payoff, but depends on the most substrate.

**Phase 5 — Specializations:** `06 Affect` (reads `02`), `08 Guardian` (reuses `01`).
Thin layers on top of everything already built.

**Substrate note (10 + 11):** these two re-shape the order above rather than slotting in at
the end. `10 Temporal knowledge-graph memory` *is* the Phase-2 memory substrate — build it
there and `02`/`03`/`06` become consumers of the graph instead of separate stores. `11
Operating modes` is best built once `10` exists (two of its four axes — ingestion tier and
the deep extraction pass — only matter with the graph), but before `01 Ambient`, since the
ambient daemon should come up already governed by a mode's feature/VRAM budget rather than
being retrofitted under one later. Revised spine: `07 → 10 → (02/03) → 11 → 04/05 → 01 →
06/08`.

```
07 ── vision/OCR ──┐
                   ├─► 01 ──► (feeds) 02 ──► 03
08 ◄── reuses 01 ──┘         │          │
                            06 ◄────────┘ (reads episodic)
04 ──► 05  (shared executor)
01 ──► 04  (observe → propose → act)
```

## UI surfaces (Tauri shell)

Every feature lands a surface in the desktop shell (`shell/src`), built on the existing
design system so the look stays cohesive: the **Aura** presence
(`shell/src/components/Aura.tsx`, state-driven idle/thinking/listening/speaking), the
**theme engine** (`shell/src/theme.ts` + `[data-theme]` blocks), and the panel/card
patterns in `App.css`. Sequence: ship the feature → land its surface on this substrate →
the cohesive **UI V2** polish pass comes after the cluster.

| # | Feature | Shell UI surface |
|---|---------|------------------|
| 07 | Universal read hotkey | Capture HUD / overlay + result card in chat *(shipped)* |
| 10 | Knowledge graph | Entity + timeline graph viewer; "what do you know about X" inspector — **deferred to UI V2**; `--graph` CLI is the interim surface |
| 02 | Time machine | Timeline scrubber / "rewind" view over past sessions |
| 03 | Local RAG | Source index page + inline citations in replies |
| 11 | Operating modes | Mode switcher pill in top bar + per-mode HUD; modes can drive the theme |
| 04 | Scoped autonomy | Live plan panel — visible steps, approve / pause / undo |
| 05 | Macros / rituals | Macro library + recorder page |
| 01 | Ambient proactivity | Quiet, dismissible nudge cards / toast center |
| 06 | Affective continuity | Aura reflects mood (reuse Aura state + `--aura-*` colors) |
| 08 | Privacy guardian | Privacy dashboard + incognito toggle + redaction badges |
| 09 | Adaptive compute | "Thinking harder" intensity on the Aura `thinking` state |
| 12 | Adaptive user model | "About you" review page (rides the `10` memory UI) |

## How this relates to older issues

These epics consolidate or build on earlier issues rather than replacing them:

| Epic | Folds in / builds on |
|------|----------------------|
| 10 Knowledge graph | #40 (Memory v3), #11 / #74 (Qdrant), #21 / #88 (export) |
| 11 Operating modes | #12 (gaming profile), #29 (focus/DND), #19 (model routing), #18 (routine macros) |
| 04 Scoped autonomy | #24 (undo last PC action), #35 (tool risk classes) |
| 05 Macros / rituals | #18 (routine macros) |
| 01 Ambient proactivity | #30 (proactive nudges), #40 (habit memory), #29 (focus/DND) |
| 03 Local RAG | #86 (conversation search) |
| 09 Adaptive compute | #19 (model routing), #80 (`llm.max_tokens`) |
| 12 Adaptive user model | #40 (Memory v3), #55–#58 (habit signals/rollup/kind/router), absorbs `06` substrate |

## Cross-cutting concerns

Decisions every feature must respect — settle these once, in shared infra:

- **Privacy / retention:** anything the watcher or episodic store records is sensitive.
  Need a retention policy, a "pause/incognito" toggle, and per-source opt-in.
- **Security gating:** every acting or watching feature routes through
  `security.gate_pc_tool()` / the `safe`/`scoped`/`armed` modes. Ambient + guardian need a
  new "observe-only" capability distinct from "act".
- **Performance:** local models are the budget. The observation daemon must be debounced
  and idle-aware (reuse the STT/TTS idle-unload pattern) so it never competes with chat.
- **Config:** all toggles via `get("...")` in `config.yaml`; quiet hours, frequencies, and
  opt-ins live there.
