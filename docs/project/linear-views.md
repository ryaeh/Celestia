# Linear views — Celestia team

Sync with [backlog.md](backlog.md). Use **horizon** labels (`short-term`, `long-term`, `optimization`) plus **priority** labels (`high priority`, `natural priority`, `low priority`).

## Priority labels (created)

| Label | Meaning | Build order |
|-------|---------|-------------|
| `high priority` | Do next — core shell path | **CC-5** → **CC-84** → **CC-49** |
| `natural priority` | Useful soon, not blocking the next release | After high-priority stack |
| `low priority` | Later, optional, Linux, duplicates (archived CC-6–46) | Backlog when time allows |

## Horizon labels (existing)

- `short-term` — active next 1–2 weeks
- `long-term` — Phase 4+, Linux, large features
- `optimization` — UX quiet mode, perf, model routing

## Recommended views

Team → **Views** → **New view**:

| View | Filters |
|------|---------|
| **Do next** | Team = Celestia, Label = `high priority`, State = Backlog or In Progress |
| **Normal backlog** | Team = Celestia, Label = `natural priority`, State is not Canceled/Done |
| **Later** | Team = Celestia, Label = `low priority`, State = Backlog |
| **Short-Term Plans** | Team = Celestia, Label = `short-term`, State is not Canceled |
| **Long-Term Plans** | Team = Celestia, Label = `long-term`, State is not Canceled |
| **Optimization** | Team = Celestia, Label = `optimization`, State is not Canceled |

Sort **Do next** by Priority (High) then Updated.

**Companion track (memory + human-like chat):** [companion-roadmap.md](companion-roadmap.md) — M0–M4, separate from main Phase numbers.

## GitHub link (optional)

Linear → Settings → Integrations → GitHub → connect `ryaeh/celestia` so PRs can link to issues (CC-*).

## Issue ID map

Canonical backlog issues are **CC-47** through **CC-84** (re-import). Older **CC-6–CC-46** duplicates are archived and labeled `low priority` — use the CC-47+ issue when planning work. Onboarding **CC-1–CC-4** stay canceled.

When you ship a feature: mark Linear **Done**, remove row from backlog.md, document in [guide/](../guide/).
