# Companion roadmap — M phases

This is the **memory + conversation** track — how Celestia stops feeling like a command line and starts feeling like someone who knows you.

It uses **M0, M1, M2…** on purpose so it doesn't clash with the main product phases in [roadmap.md](roadmap.md) (Phase 4 shell, Phase 5 installer, etc.).

---

## Where we are now — M0 (shipped)

**Memory v2** is live. This is the floor everything else builds on.

What you have today:

- Typed memory: facts, instructions, summaries, tasks
- Auto-save from chat (quiet; check the Memory page or activity feed)
- Budgeted inject every turn + last-session on "hi"
- Shell **Memory** page + `/memory` API
- One global memory for shell, tray, and CLI
- Model: **qwen2.5:7b** (Ollama) — we're keeping this; no 14B plan

**Docs:** [guide/memory.md](../guide/memory.md)

**Your job for M0:** use it daily, delete bad entries, see what auto-save gets right. No new code required until M1.

---

## M1 — Feels faster (voice & pacing)

**Goal:** Same brain, but talking to her stops feeling like "press button → wait → essay."

| Piece | What |
|-------|------|
| Streaming LLM | First words show up quickly in shell / voice |
| Early TTS | Start speaking on the first sentence, not after the full reply |
| End-of-utterance PTT | Pause while talking → she sends (less rigid hold-to-talk) |
| Shorter voice replies | Cap length so 7B doesn't ramble |
| Quiet UI | System noise stays in Activity, not chat |

**LLM:** qwen2.5:7b is enough here. This phase is pipeline latency, not IQ.

**Audio:** Headset-first (~95%). Laptop speakers sometimes (~5%) — duplex and echo are harder on speakers; design for headphones, degrade gracefully on speakers.

**Done when:** First audio within ~1–2s feels normal; most voice replies are 2–3 sentences unless you ask for more.

---

## M2 — Feels like she knows you (habit memory)

**Goal:** The differentiator — she learns your **rhythm**, not just facts you typed.

| Piece | What |
|-------|------|
| Signal log | Each chat logs time, day, topic tags, session length — lightweight, no LLM every turn |
| Active window | **OK** to log window title when allowed (e.g. "Visual Studio Code", "Discord") — helps habits without you narrating |
| Habit rollup | Weekly (or idle) job infers patterns with **confidence** — not promoted to fact until repeated or you confirm |
| Inject router | Time + context → maybe one habit line ("Usually wind down around now?") |
| Memory UI | Habits: confirm / wrong / pin; Activity panel shows what she learned quietly |

**Storage:** Keep Chroma for now. Revisit Qdrant only if scale or latency forces it — habit UX comes first.

**Done when:** After a couple weeks, at least one habit feels right without you saying "remember"; wrong ones are easy to kill.

---

## M3a — Feels like a conversation (dialogue manager)

**Goal:** Not every message is a full "turn." She knows when to answer, when to listen, when to brainstorm.

| State | She… |
|-------|------|
| **Listen** | Short ack while you're mid-thought |
| **Answer** | Normal reply, capped length |
| **Brainstorm** | Adds bullets / "what if" — one idea at a time, not a lecture |
| **Command** | Tools when you clearly asked |
| **Vent** | Empathy first, fixes only if you want |

Build this in **text chat first** (shell) — easier to debug than audio.

**LLM:** Still qwen2.5:7b + strict per-state token caps. No 14B.

---

## M3b — Feels like you're in the same room (duplex)

**Goal:** Interrupt her mid-sentence; overlap without everything breaking.

| Piece | What |
|-------|------|
| Barge-in | You talk → TTS stops → she listens |
| Duplex mic | Mic open while she speaks (headset strongly preferred) |
| Idea board | Shared bullet list in session during brainstorm |

Depends on M1 streaming + M3a states.

---

## M4 — She speaks first (proactive companion)

**Goal:** She can **start** — not only react.

| Piece | What |
|-------|------|
| Unprompted openers | Greeting, time-of-day, high-confidence habit ("Want to pick up where we left off?") |
| Rules | Opt-in tiers, quiet hours, don't nag — trust > frequency |
| Nudges | Tied to M2 habits |

Only after M2 habits are trustworthy. Wrong proactive is worse than no proactive.

**Done when:** You can leave proactive on for a week without muting her.

---

## How M phases relate to main roadmap

```text
Main roadmap (roadmap.md)     Companion track (this doc)
─────────────────────────     ──────────────────────────
Phase 4 — Product UI    ↔    M0 Memory v2 + shell Memory page (done)
                              M1 streaming voice (uses shell PTT)
                              M2 habits (Memory page + Activity)
Phase 4+ quiet UI       ↔    quiet UI, Activity panel
Later — briefing        ↔    M4 proactive nudges
```

---

## Model & hardware stance (locked in)

| Choice | Decision |
|--------|----------|
| Main chat model | **qwen2.5:7b** — stay |
| Larger 14B | **No** — RAM cost not worth it for now |
| Embeddings | nomic-embed-text via Ollama |
| "Human enough" bar | Short bursts, remembers rhythm, interruptible, not a help desk — achievable on 7B + architecture |

---

## Suggested build order

1. **M0** — use & tune v2 (you are here)
2. **M1** — streaming voice (biggest feel upgrade)
3. **M2** — signals → habits → UI
4. **M3a** — dialogue manager in text
5. **M3b** — duplex on top
6. **M4** — speak-first / proactive

One feature, test, commit — same as the rest of Celestia.
