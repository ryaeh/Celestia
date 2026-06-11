# Personality

How she talks is data in `personalities/`, not buried in Python.

```
personalities/
  default.yaml
  companion_warm.yaml
```

Pick one in config:

```yaml
personality:
  active: companion_warm
  dir: personalities
```

YAML fields that matter: `name`, `role`, `tone`, `speech_style`, `emotion_guidance` (Orpheus tags like `<laugh>`), `rules`.

You can also drop a `.md` file in that folder — the whole file gets appended to the system prompt.

**Memory** = facts about you. **Personality** = voice and attitude. Keep `voice.tts.emotion_tags: true` if you want Orpheus to follow `emotion_guidance`.

UI to switch packs without editing YAML — still on the [ideas backlog](../project/ideas-backlog.md) (see *Personality → Personality editor in the shell*).
