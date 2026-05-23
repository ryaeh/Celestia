# Personality packs (Celestia)

Celestia’s character is **data**, not hard-coded — so you can swap or extend it without rewriting the agent.

## Folder

```
personalities/
  default.yaml       ← active by default
  companion_warm.yaml
  your_custom.yaml
```

## Config

```yaml
app:
  display_name: Celestia

personality:
  active: default          # filename without extension
  dir: personalities
```

Switch:

```yaml
personality:
  active: companion_warm
```

## File formats

### YAML (recommended)

| Field | Purpose |
|--------|---------|
| `name` | How Celestia refers to herself |
| `role` | Who she is |
| `tone` | Mood / style |
| `speech_style` | How to write/spoken replies |
| `emotion_guidance` | Orpheus tags (`<laugh>`, etc.) |
| `rules` | Extra bullet rules |

### Markdown

`personalities/my_pack.md` — entire file is appended to the system prompt.

## Phase 4 UI (later)

- Dropdown: pick personality pack
- Live preview of tone rules
- Optional per-user pack in `personalities/users/<id>.yaml`

## Emotion + voice

Personality text guides **wording**; Orpheus tags in `emotion_guidance` guide **sound**.  
Keep `voice.tts.emotion_tags: true` in config for Orpheus.

## Tips for human-like feel

1. One active pack — don’t merge ten voices.
2. Tune **speech_style** for how she sounds when `--speak` is on.
3. Use memory for **facts** (preferences), personality for **how** she talks.
4. Stronger chat model (`qwen2.5:7b`) helps nuance; personality steers character.
