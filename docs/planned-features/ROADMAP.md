# Planned-features roadmap

The delivery plan for the 11 planned-feature briefs in this folder. Each brief is a
self-contained design; this doc sequences them into phases, records dependencies, and links
the tracking issue for each. For the *why* (pillars, synergy matrix, shared building blocks)
see [`README.md`](README.md).

> These are **proposals under active design**, not commitments. Status reflects the GitHub
> issue, not shipped code.

## The spine

```
07 ──► 10 ──► 02 / 03 ──► 11 ──► 04 / 05 ──► 01 ──► 06 / 08 / 12
                                                  (09 = horizontal, composes with all)
                                                  (12 collects signal from the moment 10 ships)
```

Each phase stands alone *and* lays a substrate the next phase reuses.

## Phases

### Phase 1 — Perception foothold
Smallest, fully manual, zero autonomy risk. Ships the vision/OCR pipeline improvements the
later perception features reuse.

| # | Feature | Issue | Depends on | Status |
|---|---------|-------|------------|--------|
| 07 | Universal "read screen" hotkey | [#94](https://github.com/ryaeh/Celestia/issues/94) | — (uses existing vision + hotkey) | Planned |

### Phase 2 — Memory substrate
The flagship. Build the temporal knowledge graph first; the rest of the memory cluster
becomes consumers of it.

| # | Feature | Issue | Depends on | Status |
|---|---------|-------|------------|--------|
| 10 | Temporal knowledge-graph memory | [#95](https://github.com/ryaeh/Celestia/issues/95) | — (substrate) | Planned |
| 02 | Time machine / episodic memory | [#96](https://github.com/ryaeh/Celestia/issues/96) | 10 | Planned |
| 03 | Local RAG over your stuff | [#97](https://github.com/ryaeh/Celestia/issues/97) | 10 | Planned |

### Phase 3 — Control plane + autonomy
Modes come before the ambient layer so the daemon comes up already governed by a mode's
feature/VRAM budget. Autonomy builds the executor that macros reuse.

| # | Feature | Issue | Depends on | Status |
|---|---------|-------|------------|--------|
| 11 | Operating modes (control plane) | [#98](https://github.com/ryaeh/Celestia/issues/98) | 10 (ingestion + deep-pass axes) | Planned |
| 04 | Scoped autonomy + visible plan | [#99](https://github.com/ryaeh/Celestia/issues/99) | security modes (exist) | Planned |
| 05 | Recordable macros / rituals | [#100](https://github.com/ryaeh/Celestia/issues/100) | 04 (executor), 11 (modes) | Planned |

### Phase 4 — Ambient layer
Highest payoff, most substrate. The observation daemon feeds `02`, can trigger `04`, and is
master-switched by `11`.

| # | Feature | Issue | Depends on | Status |
|---|---------|-------|------------|--------|
| 01 | Ambient proactivity | [#101](https://github.com/ryaeh/Celestia/issues/101) | 07, 10, 11, (triggers 04) | Planned |

### Phase 5 — Specializations
Thin layers on top of everything already built.

| # | Feature | Issue | Depends on | Status |
|---|---------|-------|------------|--------|
| 06 | Affective continuity | [#102](https://github.com/ryaeh/Celestia/issues/102) | 02, 10 | Planned |
| 08 | Local privacy guardian | [#103](https://github.com/ryaeh/Celestia/issues/103) | 01 (reuses daemon) | Planned |
| 12 | Adaptive user model (living portrait) | [#105](https://github.com/ryaeh/Celestia/issues/105) | 10 (store + UI), 11 (ingestion gates); **needs weeks of signal — start collecting as soon as 10 ships** | Planned |

### Horizontal — composes with all phases
Not a phase. Layer in once the turn loop is stable.

| # | Feature | Issue | Depends on | Status |
|---|---------|-------|------------|--------|
| 09 | Adaptive test-time compute | [#104](https://github.com/ryaeh/Celestia/issues/104) | turn loop; capped per mode (11) | Planned |

## How this relates to existing issues

Several of these epics consolidate or build on older issues rather than replacing them:

| Planned epic | Folds in / builds on |
|--------------|----------------------|
| 10 Knowledge graph | #40 (Memory v3), #11 / #74 (Qdrant), #21 / #88 (export) |
| 11 Operating modes | #12 (gaming profile), #29 (focus/DND), #19 (model routing), #18 (routine macros) |
| 04 Scoped autonomy | #24 (undo last PC action), #35 (tool risk classes) |
| 05 Macros / rituals | #18 (routine macros) |
| 01 Ambient proactivity | #30 (proactive nudges), #40 (habit memory), #29 (focus/DND) |
| 03 Local RAG | #86 (conversation search) |
| 09 Adaptive compute | #19 (model routing), #80 (`llm.max_tokens`) |
| 12 Adaptive user model | #40 (Memory v3), #55–#58 (habit signals/rollup/kind/router), absorbs `06` substrate |

## Cross-cutting concerns

Settle these once, in shared infra (see [`README.md`](README.md#cross-cutting-concerns)):
privacy/retention + pause/incognito, security gating (observe-only vs act), performance
(debounced, idle-aware daemons), and config (all toggles via `get()` in `config.yaml`).
