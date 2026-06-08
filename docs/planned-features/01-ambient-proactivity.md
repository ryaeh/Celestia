# 01 — Ambient proactivity

**Pitch:** Celestia stops being purely reactive. A low-frequency background watcher
observes the screen and *initiates* when it sees something worth a nudge — instead of
waiting to be asked.

Examples:
- "That stack trace has been on screen ~4 minutes — want me to look at it?"
- "You've alt-tabbed between these 12 tabs a lot — want a summary?"
- "It's 6pm and that doc still says DRAFT — remind you tomorrow?"

## Why this is a Celestia feature

A cloud assistant can't watch your screen continuously and privately. This needs all of:
sees (vision), remembers (knows what's normal/recent for you), acts (can offer to do the
fix), and local (continuous screen observation is only acceptable if nothing leaves the
device).

## How it works

- **New: observation daemon** — a debounced background loop. Captures a low-res screen
  frame on an interval *only* when there's activity, runs a cheap classifier ("is anything
  here worth surfacing?") before spending a full vision-model pass. Idle-aware: backs off
  hard when the user is away or in quiet hours.
- **Reuses:** `skills/vision/` (capture → OCR → vision model), memory for "what's normal",
  the shell SSE channel to deliver an unobtrusive nudge.
- **Two-stage cost control:** cheap trigger (pixel-diff / OCR keyword / window-title
  change) → only then the expensive vision+LLM judgement. Mirrors the STT/TTS
  idle-unload discipline so it never competes with an active chat turn.

## Data & config

```yaml
ambient:
  enabled: false            # opt-in, off by default
  interval_seconds: 30
  quiet_hours: ["22:00", "08:00"]
  max_nudges_per_hour: 3
  min_silence_before_nudge_seconds: 120
```

## Security & privacy

- Requires a new **observe-only** capability, distinct from act. Available in `scoped`+,
  never in `safe`.
- Nudges that *offer to act* still route the action through `security.gate_pc_tool()`.
- A visible "Celestia is watching" indicator + one-click pause (incognito).

## Integrates with

- **02 Time machine (●●●):** every observation is also a timeline entry — the daemon is
  the ingestion engine for episodic memory. Share one write path.
- **04 Autonomy (●●●):** observe → propose a plan → act on approval (the flagship loop).
- **08 Guardian (●●●):** same daemon, security classifier instead of helpfulness one.
- **06 Affect (●●):** behavioural signals (frustration, context-switching) feed rapport.

## Effort / risk

High effort, high payoff. Risk: false-positive nudges feel naggy → invest in the cheap
pre-filter and conservative defaults. Depends on the observation-daemon substrate, so
best built in Phase 4 after vision/memory are solid.

## Open questions

- Nudge delivery: toast, tray, or a soft in-shell card?
- How to learn "don't nudge me about X" without a heavy feedback UI?
