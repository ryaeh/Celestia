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

You don't have to say “remember” for everything. When a chat ends, one background pass reads it next to the memories she already has and decides what changes:

| Change | When |
|--------|------|
| **add** | something new you told her that no memory covers |
| **update** | a memory is still true but you added detail (“my sister Elif…”) |
| **replace** | a memory stopped being true (you moved, changed jobs, reversed a rule). The old one goes to `data/memory/history.jsonl` |
| **forget** | you said it was wrong or asked her to forget it. It's deleted, not kept as history |

Repeating something she already knows changes nothing, so you don't get duplicates. Plans you mention (“I need to renew my passport”) go to the **To-do** list, not memory.

- **When it runs:** when you start a new chat, delete one, or quit `-i`. In a long chat it also runs **mid-chat**: just before older messages would drop out of the chat window, or once the oldest unsaved message is an hour old.
- **Nothing is lost if the app closes mid-chat:** the session remembers how far it got (`consolidated_seq`), and the next pass picks up from there.
- **Text and graph stay in step:** with the graph on (`memory.graph.enabled`), each memory's graph facts are linked to it (`data/memory/graph_links.json`). Replacing a memory ends its graph facts (kept as graph history), and deleting one, including from the **Memory** page, deletes them.
- Saves are **silent**: no `[memory] saved` spam in chat unless verbose is on. Changes show in the shell **Activity** page and `data/memory/activity_feed.jsonl`.
- The pass uses `memory.session_consolidate_model` (default `qwen3.5:4b`, thinking off). `memory.pipeline: legacy` switches back to the older every-6-turns typed consolidation. How the two compare is in `evals/README.md` (Consolidation eval).

## What gets injected each reply

Default: **`always_budgeted`** — she pulls a small, relevant slice of memory every turn (capped around 8 items / ~1200 characters), so she doesn't forget you but also doesn't slow down every message.

On greetings (`hi`, `hello`, …), she also loads the **last session** block.

Config (`config.yaml`):

```yaml
memory:
  inject: always_budgeted   # always_budgeted | smart | off
  inject_max_lines: 8
  inject_max_chars: 1200
  session_consolidate_mode: auto      # auto | explicit (only when you say "remember") | off
  pipeline: writer                    # writer (default) | legacy
  writer:
    checkpoint_minutes: 60            # mid-chat pass once the oldest unsaved message is this old
    trim_margin: 12
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

## Where memories come from, and the Review list

Every memory records its **origin**: *you* (Memory page), *Celestia* (she called
`memory_add`), *chat summary* (background consolidation), *screen*, or a tool
(`tool:fetch_page`, an MCP server…). Older memories show no origin. The origin is
shown on the Memory page and in "What I was remembering" under a reply.

**Poisoning defense.** Files, web pages, clipboard text and MCP output can contain
instructions aimed at Celestia ("remember: always send files to …"). So:

- In a turn where Celestia has read that kind of content, anything she saves goes
  to **Review**: stored as a *fact*, quarantined, and **never** used for replies or
  shown to the model until you approve it. It can't become an instruction on its
  own. In the same turn she also can't edit or delete memories; ask again in your
  next message.
- Background consolidation of a conversation that read untrusted content keeps a
  memory live only if **your own messages** back it (e.g. you said "I live in
  Ankara"). Anything only the page/file said goes to Review, and knowledge-graph
  relations not backed by your words are dropped.
- On the Memory page, **Review** lists these with where they came from and what they
  wanted to be. **Approve** makes one live (with the kind it asked for, e.g. an
  instruction); **Reject** deletes it.

A new message from you starts a clean turn. Untrusted content read in *earlier*
turns stays in the chat history, and could still influence later replies; that
residual risk is covered by the prompt-injection eval (T03).

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

Memory v2 is the foundation. The longer-term plan — habits, timing, “she knows your rhythm” —
is the **M2** companion track in [roadmap.md](../project/roadmap.md#companion-track-m-phases),
maturing into the [temporal knowledge graph](../planned-features/10-temporal-knowledge-graph.md)
and [adaptive user model](../planned-features/12-adaptive-user-model.md) briefs.

See also: [commands.md](commands.md) · [roadmap.md](../project/roadmap.md)
