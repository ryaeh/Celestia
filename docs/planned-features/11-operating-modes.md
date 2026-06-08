# 11 — Operating modes

**Pitch:** A single switch that retunes Celestia's whole posture for what you're doing right
now. **Gaming** mode keeps only chat + vision resident under a hard VRAM cap, pauses
background memory work, and goes silent. **Work** mode loads the full stack, turns on ambient
memory ingestion, and surfaces relevant nudges. One concept that unifies resource budget,
active features, privacy, and how much she interrupts — so the companion never competes with
what you're actually doing.

## Why this is a Celestia feature

It exists *because* she is **Local** — a cloud assistant has no GPU to budget and nothing to
pause. Modes are the control plane that makes every other pillar affordable on one machine:
they decide which models stay resident (**Sees**/chat), whether the memory graph ingests
ambiently (**Remembers**), and what level of autonomy is on (**Acts**). It is the
cross-cutting subsystem the `README` calls for under "Performance" and "Security gating."

## What a mode controls

A mode is a named profile governing four axes:

1. **Model residency / VRAM** — which models stay resident vs swap, and a hard VRAM cap.
   e.g. gaming = chat + vision only, everything else unloaded.
2. **Active features** — which subsystems are live: vision, voice, autonomy, **and whether
   the deep-background memory extraction pass runs** (gaming pauses it to free GPU/CPU).
3. **Memory ingestion level** — which ingestion tiers from `10` are active (chat-only vs
   +explicit vs +ambient). Per-mode default with a per-session override.
4. **Behavior profile** — a bundle of **proactivity level** + **default security mode**
   (`safe`/`scoped`/`armed`). e.g. gaming = silent + safe; work = nudges + scoped.

**Explicitly *not* controlled: personality / tone.** Celestia is always *her* — modes change
what she does and how much she interrupts, never who she is.

## Switching: manual + auto-detect-with-confirm

Two paths, combined:
- **Manual** — hotkey / tray / shell. Always available, fully predictable.
- **Auto-detect-with-confirm** — context signals (foreground app/process, fullscreen state,
  resource pressure) make her *propose* a switch ("Game launched — switch to gaming mode?").
  She flips on your OK, and can learn to auto-flip for cases you consistently confirm.

This avoids the failure mode of fully-automatic switching (silently unloading models you were
mid-task with) while keeping friction near zero.

## Proactivity: a per-mode dial

Proactivity is a slider set per mode, ranging:
- **Context-triggered (floor)** — speaks only on meaningful triggers (error on screen, long
  idle, scheduled reminder), gated by mode (silent in gaming/focus).
- **…up to freely-proactive (ceiling)** — initiates check-ins on its own cadence.

A mode picks a point on that range, so "how alive she feels" tracks what you're doing.

## Voice & autonomy under modes

- **Voice = PTT + barge-in** (extends `shell_ptt.py`): push-to-talk only — no always-on mic,
  fully private — plus barge-in (interrupt her mid-speech and she stops). Whether voice is
  active at all is a mode's "active features" flag.
- **Autonomy safety** (refines `04 Scoped autonomy`): regardless of mode, real PC actions go
  through **preview → undo → confirm-irreversible**:
  - reversible actions show a preview and log to an **undo stack** she can roll back;
  - irreversible actions (delete, send, purchase) **always confirm**, even in armed mode.
  A mode only sets the *default* security level; the safety model itself is constant.

## Data & config

```yaml
modes:
  active: "work"
  auto_detect: true            # propose-on-context; manual always available
  learn_autoswitch: true       # auto-flip cases the user consistently confirms
  profiles:
    work:
      vram_cap_mb: null        # full stack
      resident: [chat, embedding]
      swap: [vision, reasoning, extraction]
      features: { vision: true, voice: true, autonomy: true, deep_memory_pass: true }
      ingestion: { chat: true, explicit_captures: true, ambient: true }
      proactivity: context-triggered     # context-triggered .. freely-proactive
      security_default: scoped
    gaming:
      vram_cap_mb: 2048
      resident: [chat, vision]
      swap: []                  # nothing else loads
      features: { vision: true, voice: true, autonomy: false, deep_memory_pass: false }
      ingestion: { chat: true, explicit_captures: false, ambient: false }
      proactivity: silent
      security_default: safe
```

Mode profiles are user-definable; `work`/`gaming`/`focus` ship as defaults.

## Model residency strategy

Tiered, hardware-aware: detect available VRAM at startup, keep the **chat model resident**,
and load vision/reasoning/extraction/embedding models on demand with **idle-unload** (reuse
the existing STT/TTS unload pattern). A mode's `vram_cap` and `resident`/`swap` lists
constrain this — so the same strategy adapts from a modest laptop to a strong desktop.

## Security & privacy

- Modes set *defaults* only; they never widen capability past the `safe`/`scoped`/`armed`
  gate in `security.gate_pc_tool()`. Irreversible actions confirm regardless.
- Gaming/focus shrinking ingestion to chat-only is a privacy feature as much as a perf one.
- Auto-switch reads foreground-app metadata only; it records nothing.

## Integrates with

- **10 Knowledge graph (●●●):** modes gate ingestion tier, the deep extraction pass, and the
  VRAM for extraction/embedding models.
- **04 Autonomy (●●●):** mode sets the default security level; the preview/undo/confirm model
  refines `04`'s executor.
- **01 Ambient (●●●):** the observation daemon only runs when the mode enables ambient
  features — modes are the daemon's master switch.
- **09 Adaptive compute (●●):** a mode can cap reasoning depth (gaming = shallow) within the
  VRAM budget.

## Effort / risk

Medium-high. The hard parts are robust auto-detect (mitigated by confirm-before-switch) and
clean model load/unload transitions without stalling chat (reuse idle-unload infra). Best
built after `10` exists, since two of its four axes (ingestion, deep pass) only matter once
the graph does.

## Open questions

- Mode transitions mid-action: queue the switch until the current turn/plan finishes?
- Should auto-detect ever switch *out* of a mode automatically, or only ever propose?
- Per-mode quiet hours, or keep quiet-hours global across modes?
