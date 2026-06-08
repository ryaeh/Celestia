# 10 — Temporal knowledge-graph memory

**Pitch:** Memory that isn't a flat pile of facts but a *structured, time-aware model of
your world* — entities, the relationships between them, and how those relationships
changed over time. Celestia can answer "what does my project depend on?" by walking edges,
and "you used to use Llama 3 but switched to Qwen last month" because every edge knows when
it was true. No cloud assistant can do this: it requires retaining your full local history
and grounding it in things you'd never upload.

## Why this is a Celestia feature

It is the **Remembers** pillar taken to its limit, and it only works because everything is
**Local**. The graph can ingest screen context and file work (the **Sees** pillar) that
would never go to a cloud product, and it persists forever on-device. This doc defines the
memory *substrate*; the existing memory-cluster briefs (`02` time machine, `03` RAG,
`06` affect) become consumers of it rather than separate stores.

## The model: three layers + a temporal graph

Two complementary representations, written together, queried together.

**Layers** (what kind of memory):
- **Semantic** — durable facts ("Doruk's main project is Celestia").
- **Episodic** — time-stamped events ("Tuesday you debugged lock contention"). This is
  where `02 Time machine` lives.
- **Procedural** — learned preferences and how-you-like-things ("prefers terse replies,
  PowerShell over cmd").

**Temporal knowledge graph** (how things connect):
- **Nodes** = entities (people, projects, tools, files, concepts).
- **Edges** = typed relationships, each carrying `valid_from` / `valid_until`.
  `[Doruk] —works_on→ [Celestia] —uses→ [Ollama] —runs→ [Llama 3 | until 2026-05]`.
- A new contradicting edge **supersedes** the old one: the old edge gets a `valid_until`
  and is retained as history; the new edge becomes current. This is *versioned supersede* —
  conflicts are resolved once, at write time, leaving a clean "current truth" plus a
  queryable past.

## Retrieval: graph-walk + similarity (hybrid)

Every recall does both and merges:
1. **Similarity** — vector search over layer entries (finds things that *sound* relevant).
2. **Graph-walk** — from entities mentioned in the query, traverse edges N hops to pull in
   structurally-connected facts even when they aren't textually similar.

Graph-walk is what answers connection/structure questions ("if Ollama changes, what's
affected?") that pure similarity misses. Results are ranked, not filtered by age — see
forgetting.

## Forgetting: never delete, rank only

Nothing is ever deleted. Superseded edges and stale facts stay in the graph as history;
they simply rank lower (recency + relevance + current-vs-historical weighting). "Forgetting"
is a ranking outcome, not a destructive op — which is exactly what makes the time-travel
queries in `02` possible.

## Ingestion: layered sources, mode-controlled

The graph is fed from three source tiers, and **which tiers are active is governed per
operating mode** (see `11 Operating modes`):
- **Chat** — always on.
- **Explicit captures** — things you point at: the `07` read-hotkey, files you share.
- **Ambient** — passive screen-watch + indexed files (the `01` observation daemon).

You can change the active tier by switching modes (work = ambient on; gaming = chat-only
for privacy + perf), with a per-session override. This is the line between "better chatbot
memory" and "a companion that knows your digital life."

## Extraction & entity resolution

Building the graph means running an LLM extraction pass (entities + relations) and resolving
each entity to a canonical node. Both are tuned to stay off the chat hot-path.

**Hybrid extraction timing:**
- **Inline (light):** cheap fact/entity capture each turn so "remember X" works instantly.
- **Background (deep):** full relation extraction, edge-building, and canonicalization run in
  the consolidation pass (extends `session_consolidate.py`). Mode can pause this to free GPU.

**Optimized full-LLM canonicalization** (knowing "llama3" == "Llama 3" == "the model"):
- **Embedding pre-filter** narrows to a few plausible candidate nodes.
- The **small fast model makes the final merge decision** on every entity (true LLM
  canonicalization, not bare similarity thresholds) — but only against that short list.
- **Batched** in the deep-background pass: resolve a whole session's entities in one/few
  calls, not one call per entity.
- **Alias cache:** once settled, repeat mentions skip the LLM entirely.

This gets full-LLM accuracy at roughly hybrid cost.

## Transparency: inspect / edit / export UI

A memory page in the shell (`shell/src/pages/`) to browse the graph, see what Celestia knows
and *from which source*, correct/delete/merge nodes and edges, and export the whole graph.
For a local-first product that ingests your screen, opacity is a non-starter — this is where
trust is earned, and also where the user resolves any entity merges the model got wrong.

## Cold start: per-graph bootstrap choice

Memory supports **multiple named graphs**. When a new graph is created, you choose its
bootstrap:
- **Guided seed** — a short onboarding (name, key facts, folders/apps to index, default
  mode) so she's useful on day one; then grows passively.
- **Blank slate** — starts empty, learns purely from interaction.

The choice is per-graph, so different contexts can start differently.

## Data & config

```yaml
memory:
  graph:
    enabled: true
    active_graph: "default"
    extraction_model: "small-fast"      # not the chat model
    embedding_model: "..."
    walk_hops: 2                          # graph-walk depth
    retain_history: true                  # never delete; versioned supersede
    inline_extraction: light             # light | off
    deep_pass: background                # background | off (mode can override)
  ingestion:
    # default tiers; per-mode overrides live in modes config (see 11)
    chat: true
    explicit_captures: true
    ambient: false
```

Edge shape: `{subject, predicate, object, valid_from, valid_until|null, source, confidence}`.
Node shape: `{id, canonical_name, aliases[], type, layer_refs[]}`.

## Security & privacy

- Pure local read/write; nothing leaves the device.
- Ambient ingestion honours the global pause/incognito toggle and per-source opt-in (shared
  with `01`/`08`).
- The inspect/edit/export UI is the user's hard control surface over everything recorded.

## Integrates with

- **02 Time machine (●●●):** episodic layer *is* the timeline; the graph adds entity links
  across days.
- **03 RAG (●●●):** graph-walk + similarity is a richer retrieval substrate than flat RAG;
  `03` queries become graph queries.
- **06 Affect (●●●):** procedural layer + episodic edges give rapport its substrate.
- **01 Ambient (●●●):** the watcher is the ambient ingestion engine — shared write path.
- **11 Operating modes (●●●):** modes govern ingestion tier, extraction-pass activity, and
  the VRAM budget for the extraction/embedding models.

## Effort / risk

High — this is the flagship substrate. Main risks: entity-resolution correctness (mitigated
by the inspect/merge UI), graph staleness (mitigated by versioned supersede + the bg pass),
and extraction cost on local hardware (mitigated by hybrid timing + small model + batching).
Supersedes the ad-hoc stores implied by `02`/`03`; build this first in the memory cluster.

## Open questions

- Graph-walk ranking: how to weight hop-distance vs similarity vs recency in the merge?
- Multiple graphs: fully isolated, or can edges cross-reference a shared "global" graph?
- Confidence decay: should low-confidence edges auto-demote over time, or only on contradiction?
