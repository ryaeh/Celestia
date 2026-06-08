# 06 — Affective continuity

**Pitch:** Make the companion *persistent* rather than a fresh prompt each session. A
lightweight rapport/mood layer so Celestia references shared history naturally — "last time
you were stressed about this deadline, how'd it go?" — instead of starting cold every time.

## Why this is a Celestia feature

Personalities exist (`personalities/*.yaml`) and memory exists, but each turn is largely
stateless about *relationship*. Persistent, private, on-device affect is what turns a tool
into a companion — and it can only be honest if it remembers you locally over months.

## How it works

- **New: affect layer** — a small, slowly-updated profile (mood trend, current
  concerns/projects, communication-style preferences) maintained by an occasional LLM pass,
  not per-turn.
- **Reads, doesn't duplicate:** sources its signal from **02**'s episodic memory and (if
  present) **01**'s behavioural cues — no separate mood database.
- **Reuses:** `personalities/` for tone; injects a compact "relationship context" block
  into the system prompt (cached per active personality like the existing prompt build).
- **Calibrated, not clingy:** intensity is configurable; defaults to subtle.

## Data & config

```yaml
affect:
  enabled: true
  intensity: subtle          # off | subtle | warm
  update_every_sessions: 5
```

Profile shape: `{mood_trend, active_concerns[], style_prefs, last_updated}`.

## Security & privacy

- Most sensitive of the memory features — emotional inference about the user. Strictly
  local, opt-out, and fully viewable/editable ("show me what you think you know about me").
- Honours the global pause/incognito toggle.

## Integrates with

- **02 Time machine (●●●):** the affect layer is a read-model over episodic memory — build
  02 first and this is a thin addition.
- **03 RAG (●●):** retrieval over past conversations personalizes replies.
- **01 Ambient (●●):** behavioural signals (frustration, focus) feed mood trend.

## Effort / risk

Low–medium *if* 02 exists (mostly a prompt-construction + small profile store). Risk is
tone — getting it wrong feels creepy or saccharine; hence conservative defaults and full
transparency. Phase 5 specialization.

## Open questions

- How to let users correct a wrong read cheaply ("no, I'm fine")?
- Does affect ever change behaviour (e.g. shorter replies when stressed) or only tone?
