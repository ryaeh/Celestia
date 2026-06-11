# Performance & QoL backlog

Captured from real-use testing (Jun 2026). Two tracks: **Performance/GPU** (backend,
designed to feed Feature 11 operating-modes) and **QoL** (most are UI → folded into the
**UI V2** pass). Ordered by impact within each track.

> **Status (Jun 2026):** perf items 1–2 are **shipped** (`gpu.py` residency manager +
> fast-by-default vision). Items 3–7 and the whole QoL/UI-V2 track remain open. The UI V2
> track *is* the committed UI overhaul plan referenced from [`roadmap.md`](roadmap.md);
> additional frontend ideas live in [`ideas-backlog.md`](ideas-backlog.md).

## Performance & GPU track

The root issue behind the screenshot freeze: **no VRAM budget**. Models load ad hoc on
Ollama's default 5-min `keep_alive`, so a vision model stacks on top of the resident chat
model and oversubscribes the GPU → display-driver hang. The safety floor is shipped
(`vision.unload_chat_model`, `vision.keep_alive`); the real fix is a residency policy.

1. ✅ **DONE — Model-residency manager (substrate for Feature 11).** Shipped as
   `celestia_core/gpu.py`: one module owning "which models may be resident, and for how
   long," with a process-wide **GPU lock** so vision, STT (Whisper), background
   graph-extraction, and chat never load simultaneously. Per-model `keep_alive`. Feature 11
   (operating modes) now just sets the policy per mode (gaming = minimal residency;
   work = warm chat).
2. ✅ **DONE — Fast-by-default vision, escalate on demand.** General screenshots use
   `moondream` (~1.6B, near-instant) by default and escalate to `qwen2.5vl:7b` /
   `llama3.2-vision:11b` only for text-heavy/hard cases (or a "look harder" action).
3. **Whisper model is oversized.** STT is `large-v3` (~3 GB, slow). `small.en` /
   `distil-large-v3` is a large speedup + VRAM win for English PTT. Config-only change.
4. **Batch graph extraction into the consolidation call.** A2 adds a *second* LLM call per
   background pass; the consolidation prompt can return typed memories **and** relations in
   one call (the brief wants this). Halves the deep-pass cost. Add embedding pre-filter +
   alias cache for canonicalization later.
5. **Idle-unload everything.** Chat, vision, STT all idle-unload after N min so an idle
   Celestia holds no VRAM (critical for gaming mode). Partly exists for STT; generalize.
6. **Token-budget tuning.** Vision `max_tokens` was 4096 (now 1536); audit chat/consolidate
   budgets for shorter, snappier replies.
7. **Warm-start (mode-gated).** Optionally preload the chat model on launch in "work" mode
   for instant first reply; never in low-VRAM modes.

## QoL backlog → UI V2

UI items land in the cohesive UI V2 pass on the existing design system (Aura + themes +
panels). Backend-only items can ship sooner.

1. **Markdown + code rendering in chat (UI V2).** Replies render as raw text today — code,
   transcripts, and lists show unformatted. Render markdown with syntax-highlighted code
   blocks + per-block copy. *High impact; she returns code/OCR transcripts constantly.*
2. **Screenshot Fullscreen / Area chooser (UI V2 + backend).** Camera button opens a small
   popover: **Fullscreen · Area · Active window**. "Area" shows a drag-select overlay
   (transparent fullscreen Tauri window or a Python region selector) → crops before analysis.
   Backend already has `vision.default_mode: region`; needs the selection overlay wired.
3. **Cancel / stop in-flight op (UI V2 + backend).** A stop button for a running vision/chat
   call so a slow GPU op never traps the user. Pairs with the GPU lock.
4. **Surface API errors as toasts (UI V2).** Silent failures (e.g. a hung `New chat` while
   the GPU was frozen) should show a toast, not do nothing. Removes "is it broken?" ambiguity.
5. **GPU/model status indicator (UI V2).** Small readout of the resident model + a GPU-busy
   state (reuse the Aura `thinking` state); optional VRAM bar. Feeds Feature 11's mode HUD.
6. **Chat conveniences (UI V2).** New-chat shortcut (Ctrl+N), message copy button,
   edit/resend, regenerate, scroll-to-bottom, timestamps on hover.
7. **Model pickers + VRAM presets in Settings (UI V2).** Choose chat/vision/STT models and a
   VRAM preset from the UI; becomes the front-end for Feature 11 modes.

## Notes

- The freeze safety floor shipped in `fix(vision): don't stack vision model on chat model`.
- Items 1 (perf) and 2/5 (QoL) are the natural bridge into **Feature 11 (operating modes)** —
  build the model-residency manager as 11's substrate rather than a throwaway.
