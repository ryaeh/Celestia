# Linear views — Celestia team

Sync with [backlog.md](backlog.md) **Horizon** column. Labels: `short-term`, `long-term`, `optimization`.

## Create labels (once)

Team **Celestia** → Settings → Labels → add:

- `short-term` — active next 1–2 weeks
- `long-term` — Phase 4+, Linux, large features
- `optimization` — UX quiet mode, perf, model routing

## Create views

Team → **Views** → **New view**:

| View | Filters |
|------|---------|
| **Short-Term Plans** | Team = Celestia, Label = `short-term`, State is not Canceled |
| **Long-Term Plans** | Team = Celestia, Label = `long-term`, State is not Canceled |
| **Optimization** | Team = Celestia, Label = `optimization`, State is not Canceled |

Sort by **Priority** or **Updated** as you prefer.

## GitHub link (optional)

Linear → Settings → Integrations → GitHub → connect `ryaeh/celestia` so PRs can link to issues (CC-*).

## Issue ID map

Backlog rows map to Linear **CC-5** through **CC-46** (created from backlog import). Onboarding issues **CC-1–CC-4** should stay canceled.

When you ship a feature: mark Linear **Done**, remove row from backlog.md, document in [guide/](../guide/).
