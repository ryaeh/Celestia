# 02 — Time machine / episodic memory

**Pitch:** A queryable, auto-maintained timeline of your days. "What was I working on
Tuesday afternoon?" / "Summarize everything about the Celestia refactor this week." A
second brain you never had to maintain — and it's entirely local.

## Why this is a Celestia feature

You already auto-distill chat sessions (`skills/memory/session_consolidate.py`). Extend
that from "long-term facts" to "episodic, time-stamped entries" and you get a personal
history no cloud product can match — because it can include things you'd never upload
(screen context, local file work, private notes).

## How it works

- **New: episodic store** — time-stamped entries in Chroma alongside the existing memory
  collection, tagged with `when`, `source` (chat / ambient / file), and a short summary.
- **Reuses:** `session_consolidate.py` already produces distilled blocks — route them into
  the episodic store with timestamps instead of only the long-term collection.
- **New: nightly reflection pass** — a scheduled LLM job writes a private daily journal
  entry ("today you debugged the lock contention, shipped commit 1, were stuck on X").
- **Retrieval:** time-windowed semantic search ("this week" + query) for "ask my day".

## Data & config

```yaml
memory:
  episodic:
    enabled: true
    nightly_reflection: true
    reflection_time: "23:30"
    retention_days: 365
```

Entry shape: `{ts, source, title, summary, refs[], embedding}`.

## Security & privacy

- Pure local read/write of Chroma; nothing leaves device.
- Honour the global pause/incognito toggle (shared with 01/08) so nothing is recorded
  during private sessions.
- Retention policy + a "forget this day/topic" command.

## Integrates with

- **01 Ambient (●●●):** the watcher's observations are episodic entries — shared write
  path makes the timeline rich without extra work.
- **03 RAG (●●●):** the timeline *is* a RAG corpus; "ask my day/week" is RAG over episodic
  memory. One retrieval substrate.
- **06 Affect (●●●):** rapport reads episodic data ("last time this deadline stressed
  you…") — no separate mood store needed.
- **05 Macros (●●):** detect "you do this every morning" from the timeline → suggest a
  macro.

## Effort / risk

Medium. Builds directly on existing consolidation. Main risk is timeline noise/quality —
the nightly reflection pass is the quality gate. Phase 2 foundation for the memory cluster.

## Open questions

- Granularity: per-session entries vs hourly rollups vs daily only?
- UI: a scrollable timeline in the shell, or purely conversational recall?
