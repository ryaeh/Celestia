# 04 — Scoped autonomy + visible plan

**Pitch:** For multi-step requests ("clean up my Downloads", "set up my morning apps"),
Celestia shows the *full plan* first, you approve once (or per-step), then it executes with
a live checklist. Real agentic PC work — with the brakes the security design already
implies.

> **Build decision (Jun 2026).** Two honest constraints shape v1:
> - **Undo is a promise we can only keep for some actions.** You can't un-send a message or
>   un-close an app. So v1 autonomy is **file-ops-first**, where undo is *real* (move-to-
>   trash, backup-before-overwrite). Irreversible actions (send, delete-permanent, purchase)
>   always confirm individually and are **never** part of an approve-once batch — this is
>   the preview → undo → confirm-irreversible model from 11.
> - **7B plans are mediocre, so keep them short.** Cap `max_steps` low (≈5) for v1; long
>   autonomous plans are where the model wanders. Pair with 09's `think` tier for plan
>   generation specifically.

## Why this is a Celestia feature

The `safe`/`scoped`/`armed` security modes (`celestia_core/security.py`) were built for
exactly this. Today tools fire one at a time with no preview. A visible plan is the natural
payoff: autonomy you can actually trust because you see it before it runs.

## How it works

- **New: multi-step executor** — agent produces a structured plan (ordered steps, each a
  tool call with args + a human description). The plan is surfaced to the shell *before*
  execution.
- **Approval model by mode:**
  - `safe`: plan shown, nothing runs (read-only preview).
  - `scoped`: per-step approval; each step gated by `gate_pc_tool()` and `scope.py`.
  - `armed`: approve-once, then auto-run with live status.
- **Reuses:** the agent tool loop in `agent.py`, `gate_pc_tool()`, `scope.py`, the shell
  SSE channel for the live checklist.
- **Resilience:** a failed step pauses the run and asks how to proceed (retry/skip/abort)
  rather than barrelling on.

## Data & config

```yaml
autonomy:
  enabled: false
  default_mode: scoped       # safe | scoped | armed
  max_steps: 12
  pause_on_step_error: true
```

Plan shape: `{goal, steps: [{tool, args, description, status}], created_at}`.

## Security & privacy

- Every step passes through the existing gate; the plan UI is a *second* checkpoint, not a
  replacement.
- `armed` approve-once is still bounded by `max_steps` and the scope allowlist.
- Full audit-log entry per executed step (extends the existing audit log).

## Integrates with

- **01 Ambient (●●●):** ambient detects a situation → generates a plan → this executes it.
  The observe→propose→act loop.
- **05 Macros (●●●):** a macro is a saved plan; replay runs through this same executor.
- **08 Guardian (●●●):** guardian flags a threat → proposes a remediation plan here.
- **03 RAG (●●):** plans grounded in retrieved setup notes/docs.

## Effort / risk

High effort, high risk (it acts on the real machine). Mitigations: start `safe`-only
(preview, no exec), then enable `scoped`. The plan-preview UI is the critical safety
surface. Phase 3.

## Open questions

- Plan representation: let the LLM emit JSON steps, or a constrained DSL?
- Each tool declares its own reversibility + undo action; tools with no real undo are
  flagged irreversible and forced to per-step confirm. (Replaces the old open "can steps
  declare an undo?" — yes, and it's mandatory metadata.)
