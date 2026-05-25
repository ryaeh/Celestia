# Memory

This is how Celestia remembers you — and how to fix it when she gets something wrong.

Long-term memory lives in Chroma (`data/chroma/`), with mem0 on top. Shell, tray, and CLI all share the **same** memory. What you save in one place shows up everywhere.

---

## What she stores (Memory v2)

Each entry has a **kind**:

| Kind | What it's for |
|------|----------------|
| **fact** | Stable stuff about you — name, preferences, projects |
| **instruction** | Standing rules (“keep replies short”, “call me …”) |
| **summary** | Short recap of what you talked about |
| **task** | Open todos or things you said you'd do |

She also keeps a separate **last session** note (`data/memory/last_session.json`) — not mixed with facts. When you say hi, she can reference “since last time” without loading your whole memory.

---

## Auto-save (happens in the background)

You don't have to say “remember” for everything. After enough chat turns, she quietly extracts facts, summaries, tasks, and instructions from the conversation.

- Saves are **silent** — no `[memory] saved` spam in chat (unless you turn verbose on in config).
- What got saved shows up in the shell **Memory** page, or in `data/memory/activity_feed.jsonl` if you want to peek at the log.

On **new chat** or when you quit `-i`, she consolidates what's left and updates the last-session note.

---

## What gets injected each reply

Default: **`always_budgeted`** — she pulls a small, relevant slice of memory every turn (capped around 8 items / ~1200 characters), so she doesn't forget you but also doesn't slow down every message.

On greetings (`hi`, `hello`, …), she also loads the **last session** block.

Config (`config.yaml`):

```yaml
memory:
  inject: always_budgeted   # always_budgeted | smart | off
  inject_max_lines: 8
  inject_max_chars: 1200
  session_consolidate_mode: auto
  session_consolidate_every: 6
```

- **smart** — only inject when the message looks memory-related
- **off** — never auto-inject; tools and manual `memory` still work

---

## What you can do

**In chat / `-i`:**

- `memory` — list what's stored
- `forget` — wipe everything (asks yes/no first)
- `forget purple` — delete lines containing “purple”
- `newchat` — finish this chat (consolidate + last-session), start fresh

**In the shell:** open **Memory** from the sidebar — add, edit, delete, refresh last-session.

**Ask in chat:** “forget that I …” or “remember that …” — she can use memory tools.

There's no magic edit-in-place in CLI; delete the wrong line and add the right one, or use the Memory page.

---

## When memory is wrong

It happens. Auto-save is conservative but not perfect.

1. Shell → **Memory** → find the bad entry → **Delete**
2. Or: `forget <word>` if you know what's in the text
3. Tell her the correct fact if you want it stored again

If something keeps coming back from old chats, start a **new chat** after deleting — consolidation only runs on what’s new since the last pass.

---

## User id

`app.user_id` in config (default `atlas_user`) scopes storage. Renaming the project folder doesn't wipe Chroma.

---

## What's next

Memory v2 is the foundation. The longer-term plan — habits, timing, “she knows your rhythm” — is **M2** in [companion-roadmap.md](../project/companion-roadmap.md) ([CC-85](https://linear.app/ryaeh/issue/CC-85/memory-v3-habit-learning-and-living-user-model) on Linear).

See also: [commands.md](commands.md) · [companion-roadmap.md](../project/companion-roadmap.md)
