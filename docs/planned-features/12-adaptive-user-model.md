# 12 — Adaptive user model (the living portrait)

**Pitch:** Beyond remembering the user's *world* (`10`), Celestia builds a living portrait
of the *user*: graded tastes with confidence, daily rhythms, and — uniquely — how the user
responds to *her*. She tunes herself without ever being told: suggestions you ignore happen
less, styles you respond to happen more. Being yourself is the feedback. No cloud assistant
can do this honestly — it requires watching behavior over months and keeping every
conclusion on your machine, inspectable.

## Why this is a Celestia feature

It is the **Remembers** pillar pointed inward, and it only works because she is **Local**
(the portrait never leaves the device, and the user can see all of it) and **Sees** (behavior,
not just statements, feeds it). `10` makes her *informed*; this makes her *adaptive*. It is
the layer that turns "a tool with notes about you" into "someone who gets you."

## The model: three components

1. **Taste profile** — graded likes/dislikes with a confidence score, learned from
   *everything*: explicit statements, choices made, suggestions ignored, things returned to,
   reply pace. Nothing is off-limits by topic — the review page (below) is the control
   surface, not a blocklist.
2. **Rhythm model** — what the user's days actually look like: when they work, wind down,
   want quiet. The fuller form of the habit-memory line (signal log → rollup → habit kind).
3. **Reaction learning** — implicit feedback from how the user responds to Celestia herself:
   ignored suggestions, cut-off replies, rephrased questions, accepted nudges. This is the
   loop that tunes her, and it works from chat alone — no ambient access required.

## What adapts (four surfaces)

- **How she talks** — length, depth, directness, when to joke vs be brief.
- **What she suggests** — which ideas she offers, when she stays quiet.
- **How she does tasks** — learned defaults: the folder you always use, the naming you prefer.
- **What she prioritizes** — your project before trivia, people you care about first.

**Explicitly fixed: her identity.** She adapts *within* her personality — briefer, warmer,
quieter *for you*, but her humor, honesty, and manner stay hers (consistent with `11`:
nothing changes who she is). Adapting toward mirroring the user is out of scope by design.

## Operating rules

- **Quiet adaptation, fully reviewable.** She never asks permission to learn; instead, every
  conclusion lives on an "about you" page in the shell (part of the `10` memory UI): what she
  believes, how confident, learned from what. Edit, correct, or delete any of it, anytime.
- **Pattern before update.** A one-off contradiction is an exception ("today was unusual").
  Repeated contradiction triggers a versioned supersede — the old belief becomes "used to
  prefer X" with its validity window closed, kept as history (same mechanics as `10` edges).
- **In-the-moment mood sensing.** She reads available signals — hour, phrasing, message pace,
  current activity — and adjusts tone and timing *now*. Momentary state is not written into
  the durable portrait; only repeated patterns graduate into the rhythm model.
- **Gentle, pattern-backed pushback.** When a strong pattern warrants it, she may challenge
  once ("you usually regret these late-night purchases — still want it?"). Never twice for
  the same decision; capped frequency overall.
- **Guard against over-fitting (don't shrink her to your past self).** Pure adaptation
  narrows her to what you've already done. She must occasionally suggest *outside* the
  learned profile — a new tool, a different approach — explicitly flagged as a stretch.
  Adaptation tunes *how* she helps, it does not wall off the unfamiliar.
- **Reaction signals are noisy — treat them as weak evidence.** A cut-off reply isn't
  dislike (it could be a doorbell); a skipped suggestion isn't rejection (bad timing).
  Reaction-learning therefore uses the **highest** pattern threshold of all three components
  and the longest confirmation window — never updates the portrait off a single signal.

## Data & config

```yaml
memory:
  user_model:
    enabled: true
    learn_from: behavior            # behavior (everything) | actions | stated-only
    pattern_threshold: 3            # repeats before a belief updates/supersedes
    mood_sensing: true              # in-the-moment tone/timing adjustment
    pushback: gentle                # gentle | on-request | off
    pushback_min_confidence: 0.8
    pushback_cooldown_hours: 24
```

Portrait entry shape: `{kind: taste|rhythm|reaction, statement, confidence, evidence_refs[],
valid_from, valid_until|null, source: stated|observed|inferred}` — stored as nodes/edges in
the `10` graph so supersede, history, and the inspect UI come for free.

## Security & privacy

- Entirely local; the portrait is the most sensitive data Celestia holds and never leaves
  the device.
- Behavioral watching (beyond chat) rides the **mode-gated ambient ingestion** from `11` —
  gaming/focus modes mean she is not studying you. Reaction learning (chat-only) follows the
  chat ingestion tier.
- The "about you" page is the trust contract: nothing she believes about the user is hidden,
  and every entry shows its evidence.

## Integrates with

- **10 Knowledge graph (●●●):** the portrait *is* the procedural layer matured — same store,
  same supersede mechanics, same UI. Build `10` first; `12` rides it.
- **06 Affective continuity (●●●):** `06` recalls how things felt; `12` generalizes it into
  durable understanding. `12` absorbs `06`'s substrate.
- **01 Ambient (●●●):** observations feed the rhythm model; the proactivity dial uses the
  portrait to pick *good moments*.
- **11 Modes (●●):** gates what watching is active; mood sensing helps propose mode switches.
- **09 Adaptive compute (●):** "is this a moment worth a deep think" can consult the rhythm
  model.

## Effort / risk

High — and unlike the other briefs, the cost is mostly *time*: the portrait needs weeks of
signal before it is worth trusting. Main risks: wrong conclusions (mitigated by the pattern
threshold + review page), creepiness (mitigated by total transparency — quiet adaptation is
only acceptable because the page exists), and over-adaptation (mitigated by the fixed-identity
rule). Ship the review page in the same release as the first learned behavior, not after.

## Open questions

- Pattern threshold: **per-kind** (decided — reaction tuning needs the highest bar, tastes
  next, stated facts lowest); exact numbers TBD from real signal.
- How often is a "stretch" suggestion right vs annoying — fixed rate, or tied to confidence?
- Should reaction learning have a "reset" (user had a bad month; start fresh) distinct from
  deleting entries?
- Cold start: does the `10` guided-seed onboarding pre-fill any portrait entries, or must all
  of it be earned from observation?
