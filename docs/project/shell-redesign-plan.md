# Shell redesign — Console first, Orbit later

Status: **proposed, Nov 2026.** Four directions were explored as full chat screens; the owner
picked **B · Console** to build now and **A · Orbit** to add later. C · Margin and D · Midday are
kept as reference only.

- **Design canvas** (private, owner's account): <https://claude.ai/artifact/XJNCP1jqrVi9aFE4AY1TQU>
  — four 1280×840 artboards with accent tweaks. The sample conversation, memory entries and
  the VRAM figure on it are illustrative, not read from real data.
- **Roadmap context:** [`roadmap.md`](roadmap.md). This is the UI V2 "cohesive polish pass"
  ([`ui-v2-plan.md`](ui-v2-plan.md)) with a concrete target look; it interleaves with the
  feature work and does not jump the build order.

## Why B first

Console makes the product's actual promise visible: *a companion that acts only through
audited, gated, undoable permissions, with an inspectable memory* (see the roadmap's
positioning). It puts the mode switch, the tool trail, the memory in use and the approval
step on screen instead of behind Settings. Most of it is data the shell already receives.

## Guardrails (carry over from the current shell)

- **Identity unchanged.** Chrome only; no change to her voice, tone or personality.
- **Local only.** The mockup loaded fonts from Google Fonts for preview. The app must bundle
  them (`@fontsource-variable/*`, as Geist is today). No network fetch for fonts.
- **Themes keep working.** B is a layout + type + token pass on the existing theme engine
  (`App.css` variables). All six themes stay selectable; text meets WCAG AA (4.5:1) on every
  surface of every theme. Whether to add a seventh theme ("Graphite": graphite + amber) and make
  it the default is an open question below.
- **Accessibility.** Real `<button>`/`<input>` + labels, `aria-label` on icon-only buttons,
  never colour alone for status (every status dot has a word).

## What B changes, and what each part needs

| B element | Today | Needs |
|---|---|---|
| Dense sidebar: history grouped Today / Yesterday / Earlier, `Ctrl N` hint, To-do open count | `Sidebar.tsx`, flat history | Frontend only |
| Log with a timestamp gutter, lowercase names | `.msg` in `Home.tsx`; message `ts` already stored | Frontend only |
| Inline tool lines (`search_conversations "launch gate" · done`) | SSE already emits `{tool, phase: start/end, ok, label}` (`agent.py`) | Frontend; decide if they persist or are live-only |
| Blocked tool calls shown as a row with the reason | Gate returns a `Blocked: …` string as the tool result | Frontend |
| Right rail: **Mode** switch | Mode is pushed over `/ws/state`; switching lives in Settings | Frontend (reuse the existing mode endpoint) |
| Right rail: **This turn** timeline | Same tool events as above | Frontend |
| Right rail: **Memory in use** | `provenance` on the stream's done event (live reply only) | Frontend; persisting provenance is a later option |
| Right rail: **Model** + VRAM bar | GPU data on `/ws/state`; chat model from config | Frontend |
| Status bar (Ollama, model, mode, learning, `Ctrl K`) | `ollama_state`, mode and incognito already live | Frontend |
| **Approval card** (Allow once / Always allow / Deny) | **Does not exist.** `gate_pc_tool` blocks state-changing PowerShell in scoped mode outright (`security.py`, "Blocked in scoped mode (needs armed)") | **Backend — this is T08 step 2** (per-command confirmation) plus a pending-approval channel (SSE event + token-guarded `POST`). "Always allow" needs a rule store under config integrity; treat it as a separate security decision |
| Command palette `Ctrl K`, `/` commands | Not built (UI V2 Phase 3) | Separate task; ship the search field first |
| Composer buttons "Look at screen", "Use clipboard" | The tools and the read-screen hotkey exist; no buttons | Small user-initiated endpoints; clipboard text must stay wrapped as untrusted |

## Build plan — B · Console

| Phase | Scope | Depends on |
|---|---|---|
| **B0 Foundations** | Bundle Instrument Sans + JetBrains Mono; type scale and the `--font-mono` token; three-column app frame (sidebar, chat, rail) behind the current theme variables; check all six themes for contrast | — |
| **B1 Console shell** | Grouped sidebar, timestamp-gutter log, status bar, right rail with Mode, Model/VRAM and Memory in use, using data the shell already has. Rail collapses under ~1100 px | B0 |
| **B2 Tool trail** | Inline tool lines and the **This turn** timeline from SSE tool events; blocked calls rendered with their reason and a "switch mode" action | B1 |
| **B3 Approvals** | Pending-approval backend and the card UI; audit every decision | **T08**, and B2 |
| **B4 Reach** | Command palette, slash commands, composer buttons | UI V2 Phase 3 |

Each phase ends with something visible in the shell. A phase is done when `npm run build`
passes, the manual checklist in `docs/testing/checklist.md` is updated, and any backend piece
has pytest coverage with Ollama mocked.

## Later — A · Orbit (voice-first stage)

A second view, not a replacement: a large moon, the live words in big type, and the transcript
and "what I was remembering" in a side panel. Reuses the Aura moon states (idle crescent,
listening full moon with ripples, speaking). Build after B2.

| Phase | Scope | Depends on |
|---|---|---|
| **A1 Stage view** | Chat ⇄ Orbit toggle; stage driven by the existing Aura state and the last turn | B1 |
| **A2 Live voice feedback** | Partial transcript while PTT is held; speaking state from TTS (also a pending follow-up for the companion bubble) | UI V2 Phase 3 "live voice feedback" |
| **A3 Barge-in** | Speaking over her stops playback | **T06**, which depends on **T05** |

## Open questions for the owner

1. Add a "Graphite" theme (graphite + amber) and make it the default, or keep Aurora as default and let B apply to all themes?
2. Should tool lines persist in the stored transcript, or stay live-only like provenance?
3. "Always allow `git push` here" — worth a rule store at all, or only Allow once / Deny?
4. Task IDs: this needs issue numbers and T-IDs before B0 starts (one task per branch/PR).

## Parked ideas from the other directions

- **C · Margin:** numbered provenance footnotes in the reply text with matching margin notes. A possible later upgrade for the "what I was remembering" row.
- **D · Midday:** suggestion chips under replies ("Draft the PR description"). Cheap to add once replies can carry actions.
