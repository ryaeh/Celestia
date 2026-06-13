# UI V2 — the plan

The cohesive polish pass for the Tauri shell. This doc carves the way: it frames UI V2 as
**three load-bearing foundations + phased surfaces** (not 20 unordered polish items), maps
every backlog item to a phase, and records the one architectural decision the back half hinges
on (SSE → WebSocket).

- Source backlogs: [`perf-and-qol-backlog.md`](perf-and-qol-backlog.md) (the committed UI V2
  item list) + the *Frontend* section of [`ideas-backlog.md`](ideas-backlog.md) (additions).
- Roadmap context: [`roadmap.md`](roadmap.md) — *"UI V2 runs after the feature cluster starts
  landing surfaces — features first, polish once."*

## Reconciling with "features first, polish once"

UI V2 is *not* jumping the queue, because it isn't built as one monolithic pass. The **two
foundations below are the deliberate exception** — they're high-impact now and make every
remaining feature surface (02/03/04/10/11/12) nicer to build. Everything past the foundations
**interleaves with the feature work**: the graph viewer lands *with* Feature 10's UI, model
pickers *with* Feature 11, the "about you" page *with* Feature 12. So UI V2 is a spine that the
feature surfaces hang off, not a separate project competing with them.

## Identity guardrail

Per the locked-in stances: **no UI change alters her voice, tone, or personality.** UI V2 is
chrome and ergonomics. Markdown rendering, toasts, HUDs — none of them touch what she says or
how she says it.

---

## The three foundations

Each foundation is a primitive the rest reuses. Build order matters: 1 and 2 unblock most of
Phase 1; 3 is the big backend piece that unblocks the live-state surfaces.

### F1 — Markdown / code rendering pipeline  ✅ SHIPPED (Jun 2026)
`shell/src/components/MessageBody.tsx` — assistant replies render as GitHub-flavored markdown
(react-markdown + remark-gfm) with syntax-highlighted code blocks (rehype-highlight), per-block
copy, and externally-opened links. No raw HTML (no rehype-raw) → model output can't inject
markup, consistent with the prompt-injection posture. highlight.js tokens + all markdown
elements are themed against the palette, so it tracks all 6 themes. Replaced the raw
`<p>{content}>` in `Home.tsx`. User messages stay plain by design.

### F2 — Toast / notification primitive  ✅ SHIPPED (Jun 2026)
`sonner` `<Toaster>` mounted in `App.tsx`, themed via `.celestia-toast`. First use: code-copy
confirmation. This is the shared surface that **cancel feedback, API-error surfacing, mode-change
toasts, "memory saved", and copy confirmations** all reuse — so those items become trivial.

### F3 — In-flight op / cancel control plane  ⏳ OPEN (the big one)
Backend cancellation for long ops (chat turn, vision) + a frontend **stop button**, and the
**server→client state-push channel** it shares with the GPU/model HUD. This is the genuinely
large, design-heavy piece. It is the bridge to Feature 11's mode HUD. See the SSE→WebSocket
decision below — F3 is where that lands.

---

## The SSE → WebSocket decision

**Decision: keep SSE for chat token streaming; add ONE WebSocket only for server→client state
push. Do not replace SSE wholesale.**

- SSE already does chat streaming well (`/chat/stream`); there's no reason to rip it out.
- What SSE *can't* do is push unsolicited state: tray/CLI mode changes reflected live in the
  shell, GPU-busy state, PTT phase, incognito toggle from another surface. Today the shell
  polls (`fetchStatus`) for these.
- A single WebSocket (`/ws/state`) carrying a small typed event stream
  (`{type: "mode"|"gpu"|"ptt"|"incognito", ...}`) is the right backbone. It also becomes the
  cancel channel for F3 (client → server "cancel current op").
- Cost: one WS endpoint + a tiny client store. Build it **inside F3**, not speculatively.

This keeps the change incremental and reversible — chat keeps working on SSE if the WS is down.

---

## Phases

### Phase 0 — Foundations (the carve)  ✅ DONE
- F1 markdown rendering, F2 toast primitive.

### Phase 1 — Cheap wins on the foundations (pure frontend, no new backend)
Now unblocked by F2; each is small.
- **API errors → toasts** (perf-QoL #4) — replace silent failures / the inline error banner
  with toasts. Removes "is it broken?" ambiguity.
- **Chat conveniences, frontend subset** (perf-QoL #6) — message copy button, new-chat shortcut
  (Ctrl+N), scroll-to-bottom affordance, timestamps on hover.
- **Mode pill in the header** (ideas/Frontend) — read-only colored pill first (safe/scoped/armed),
  glows red while armed. Becomes Feature 11's HUD anchor; pairs later with time-boxed arming.

### Phase 2 — The control plane (= Foundation F3)
The big backend piece; do it as one arc.
- **Cancel / stop in-flight op** (perf-QoL #3) — backend cancellation for chat/vision + a stop
  button. Pairs with the GPU lock so a slow op never traps the user.
- **SSE → WebSocket state-push channel** (per the decision above) — `/ws/state` + client store.
- **GPU / model status indicator** (perf-QoL #5) — resident model + GPU-busy readout, optional
  VRAM bar; consumes the push channel. Feeds Feature 11's mode HUD.

### Phase 3 — Larger surfaces (interleave with feature work)
Built on the stable foundation; each ships *with* its owning feature where one exists.
- **Settings expansion + model pickers + VRAM presets** (perf-QoL #7) — the front-end for
  Feature 11 modes. Follows the standing convention: `config.yaml` key via `get()` → Settings
  control → `--trust-config`.
- **Screenshot Fullscreen / Area chooser** (perf-QoL #2) — backend already has
  `vision.default_mode: region`; needs the drag-select overlay wired.
- **Command palette (Ctrl+K)** (ideas/Frontend) — cmdk-style box: new chat, switch personality,
  change mode, screenshot, search sessions. Makes every feature reachable; ties Phase 1 actions
  together.
- **Edit / resend + regenerate** (perf-QoL #6, backend-touching subset) — needs per-message
  addressing in the session store.
- **A4 graph viewer = timeline-first** (ideas/Frontend) — ships *with* Feature 10's UI: a time
  slider ("what did you know about X in March", superseded edges ghosted), not a force-directed
  hairball.
- **"About you" page skeleton** (ideas/Frontend) — ships *with* Feature 12; design empty states
  now so 12 has a home.
- **Live voice feedback** (ideas/Frontend) — partial transcript + aura pulse while PTT held;
  waveform while she speaks.
- **Session auto-titles** (ideas/Frontend) — cheap LLM call at consolidation. (Keyword session
  *search* already shipped, #86.)

---

## Dependency graph (text)

```
F1 markdown ✅ ─────────────► (every reply, OCR dump, code surface)
F2 toast ✅ ───┬─► API-error toasts
               ├─► copy / chat conveniences
               └─► cancel feedback ─┐
F3 control plane ──┬─ cancel/stop ──┘
                   ├─ /ws/state (SSE→WS)
                   └─ GPU/model HUD ──► Feature 11 mode HUD
Mode pill ────────────────────────────► Feature 11 mode HUD
Settings expansion ───────────────────► Feature 11 model/VRAM control
Graph viewer ─────────────────────────► Feature 10 UI
"About you" page ─────────────────────► Feature 12 UI
```

## Risks / follow-ups

- **Bundle size.** `rehype-highlight` bundles highlight.js with its full language set (~690 kB
  raw / ~213 kB gzip). Fine for a local desktop app loaded from disk; if it ever matters, trim
  to a curated language list via `lowlight`. Low priority.
- **Streaming markdown re-parse.** `MessageBody` re-parses on every streamed token. Couple this
  with **B-14 (batch SSE tokens via RAF)** from the audit when it becomes visibly janky.
- **Dev-only advisories.** `esbuild`/`vite`/`@vitejs/plugin-react` carry high-severity dev-server
  advisories (GHSA-gv7w-rqvm-qjhr, GHSA-g7r4-m6w7-qqqr). Pre-existing, dev-only; the fix is a
  breaking Vite 7→8 bump — track as its own task, not part of UI V2.
- **Accessibility.** Command palette needs keyboard nav + focus trap; toasts need sensible
  durations and an aria-live region (sonner handles most of this).

## Cross-refs
- Item source of truth: [`perf-and-qol-backlog.md`](perf-and-qol-backlog.md) (QoL → UI V2 track)
  and [`ideas-backlog.md`](ideas-backlog.md) (*Frontend* additions).
- Feeds: Feature 11 (mode HUD, model/VRAM presets), Feature 10 (graph viewer), Feature 12
  ("about you" page).
- Audit ties: B-14 (batch SSE tokens) pairs with the streaming-markdown perf note.
