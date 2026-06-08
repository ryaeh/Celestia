# 05 — Recordable macros / rituals

**Pitch:** Capture a sequence of actions once and replay it on a trigger or schedule.
"Every weekday 9am: open these three apps, read me my calendar, summarize unread." Builds
straight on the CC-59 morning briefing.

## Why this is a Celestia feature

Cloud assistants can't open your apps or run your scripts. Celestia already has gated PC
control; macros make repeated PC work a one-liner — and scheduling makes it ambient.

## How it works

- **New: scheduler** — time triggers (cron-like) and event triggers (login, hotkey, "when
  I open app X"). A single scheduler service shared with 01 (quiet hours) and 02 (nightly
  reflection).
- **Macro = saved plan:** reuses the **04** multi-step executor. Recording a macro is
  capturing a plan; running one replays it through the same gated executor.
- **Reuses:** `skills/pc_control/tools.py`, `security.py` gating, the CC-59 briefing as the
  first built-in ritual.
- **Authoring:** create from a successful autonomy run ("save these steps as a macro"), or
  hand-write in config.

## Data & config

```yaml
macros:
  - name: "morning"
    trigger: { type: cron, at: "09:00", days: ["mon-fri"] }
    steps:
      - { tool: open_path, args: { path: "..." } }
      - { tool: briefing, args: {} }
```

## Security & privacy

- Every replayed step re-passes `gate_pc_tool()` at run time — a macro can't escalate past
  the current security mode.
- Scheduled macros that act require `scoped`+; in `safe` they only preview.
- Audit-logged per run.

## Integrates with

- **04 Autonomy (●●●):** shares the executor; macros are persisted plans.
- **01 Ambient (●●):** shares the scheduler + quiet-hours logic.
- **02 Time machine (●●):** "you do X every morning" detected from the timeline → suggest
  turning it into a macro.
- **08 Guardian (●●):** scheduled security sweeps as a built-in ritual.

## Effort / risk

Medium — most risk is inherited from 04's executor. The scheduler itself is small. Best
built right after 04 (Phase 3) so it reuses the executor instead of duplicating it.

## Open questions

- Event triggers ("when app X opens") need a process/window watcher — share with 01's
  observation daemon?
- Failure handling for *unattended* scheduled runs (no user to approve a paused step).
