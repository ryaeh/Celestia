# Memory

Facts live in Chroma under `data/chroma/` (mem0 on top). On by default.

She can **remember** (stores what you said, not a paraphrase), **recall** (injects matching facts into the prompt when inject mode allows), and **search** via tools.

**You can:**

- `memory` — list what’s stored
- `forget` — delete everything (confirms first)
- `forget purple` — delete lines containing “purple”
- ask in chat to remove something specific

There’s no edit-in-place — delete, then tell her the right fact again.

## Inject mode

```yaml
memory:
  inject: smart    # smart | always | off
```

- **smart** — only pulls memory in when the message looks like it needs it (default). “hi” often won’t load anything — that’s normal.
- **always** — every turn; good when you’re testing
- **off** — never auto-inject; tools still work

## User id

`app.user_id` in config (default `atlas_user`) scopes storage. Renaming the project folder doesn’t wipe Chroma.

## Clean-up example

```
memory
forget Atlas
remember my favorite color is blue
what is my favorite color
```

We try to filter junk where the model stored its own boilerplate (“I am Celestia…”) as if you said it.
