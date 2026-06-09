# 07 — Universal "read screen" hotkey

**Pitch:** One global hotkey → Celestia captures the screen, OCRs + vision-reads it, and
answers about whatever's in front of you — even apps with no API. "What does this error
mean?" "Summarize this page." "Translate this." Instant, manual, zero autonomy.

## Why this is a Celestia feature

It works on *anything* on screen because it reads pixels, not APIs. Local OCR + vision
means it works offline and on private content. This is the simplest, safest expression of
the "sees" pillar — and the on-ramp for the whole perception cluster.

## How it works

- **Reuses:** the global hotkey infrastructure in `celestia_core/shell_ptt.py` (already
  handles a system-wide push-to-talk hotkey) and the `skills/vision/` capture → OCR →
  vision pipeline.
- **Flow:** hotkey → capture active monitor/window → OCR for text + vision model for layout
  → inject as context → answer in the shell (and optionally speak via TTS).
- **No background process:** purely user-triggered, so no daemon, no watching, no privacy
  surface beyond the moment of capture.

## Data & config

```yaml
read_hotkey:
  enabled: true
  hotkey: "ctrl+alt+space"
  scope: active_window       # active_window | fullscreen
  speak_answer: false
```

## Security & privacy

- Captures only on explicit keypress — nothing continuous.
- Capture is processed locally and discarded unless the user saves it (or 03's screenshot
  corpus is enabled).
- Available in all modes (it's read-only); offering to *act* on what it sees routes through
  the normal gate.

## Integrates with

- **01 Ambient (●●):** this is the *manual* trigger; 01 *automates* the same pipeline. Build
  this first to harden capture/OCR/vision, then 01 reuses it.
- **04 Autonomy (●●):** "fix this error on screen" → hand the read context to a plan.
- **03 RAG (●●):** captured screenshots + OCR text feed the screenshot corpus.
- **08 Guardian (●●):** shares the capture+classify pipeline.

## Effort / risk

Low. Both halves (hotkey, vision) already exist — this is mostly wiring + an OCR quality
pass. Lowest-risk, highest-immediate-utility. **Phase 1 / first to build.**

## Open questions

- Multi-monitor: which display, or a quick picker?
- Region select (drag a box) vs whole window — worth the extra UI?
