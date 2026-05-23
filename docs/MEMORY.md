# Celestia memory

Memory is **on** by default (`memory.enabled: true`). Data lives in `data/chroma/` (Chroma + mem0).

## How it works

| Action | What happens |
|--------|----------------|
| **Remember** | Model calls `memory_add` — stores your words as-is (`infer: false`) |
| **Recall** | Matching facts are injected into the prompt (when `memory.inject` allows) |
| **Search** | Model can call `memory_search` |
| **Change** | No direct edit — use **delete** then **add** again |
| **List** | REPL: type `memory` |
| **Clear all** | REPL: `forget` (confirm yes) or `run_celestia.py --forget-memory` |
| **Delete one** | REPL: `forget purple` or ask in chat to remove a fact |

## Why it felt “off”

1. **Inject mode `smart`** — short messages like `hi` or vague questions may **not** load memory into the prompt (by design).
2. **Add-only** — there was no delete tool; wrong facts stayed forever.
3. **Pollution** — the model sometimes stored *its own* lines (“I am Atlas…”) as if they were your facts.

Fixes: `memory_list` / `memory_delete` tools, REPL `memory` / `forget`, junk filtered from auto-inject.

## Config

```yaml
memory:
  enabled: true
  inject: smart    # smart | always | off
```

- **`always`** — load memories every turn (except bare hello). Best for testing.
- **`smart`** — load when the message looks memory-related (default).
- **`off`** — never auto-inject (tools still work).

## User id

`app.user_id` (default `atlas_user`) scopes memories. Same id after rename from Atlas folder — your old entries are still there.

## Clean slate example

In interactive mode:

```
memory
forget Atlas
forget hearing
remember my favorite color is blue
what is my favorite color
```
