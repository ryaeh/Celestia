# Docs

Everything for Celestia is under `docs/`. Start with **getting-started** if this is a fresh setup.

## Daily use

- [getting-started.md](getting-started.md) — install, config, first run
- [guide/commands.md](guide/commands.md) — what you can type in chat (`help` in the app is the live version)

## How things work

- [guide/security.md](guide/security.md) — safe / scoped / armed modes, audit log
- [guide/vision.md](guide/vision.md) — screenshots, region vs window vs full screen
- [guide/memory.md](guide/memory.md) — what she remembers and how to clean it up
- [guide/personality.md](guide/personality.md) — YAML packs in `personalities/`
- [guide/skills.md](guide/skills.md) — how to add a new tool skill

## Troubleshooting

- [guide/troubleshooting.md](guide/troubleshooting.md) — Ollama down, CUDA OOM, Whisper fail, shell port conflicts

## Under the hood

- [reference/architecture.md](reference/architecture.md) — folders, stack, data flow
- [reference/api.md](reference/api.md) — shell server HTTP API (all routes)
- [reference/deployment.md](reference/deployment.md) — startup modes, dev workflow, fresh machine setup
- [reference/performance.md](reference/performance.md) — VRAM profiles, model choices

## Roadmap & planning

- [project/roadmap.md](project/roadmap.md) — phases: what shipped and what's next (includes the M0–M4 companion track)
- [planned-features/](planned-features/) — 12 designed feature briefs + delivery [ROADMAP](planned-features/ROADMAP.md)
- [project/perf-and-qol-backlog.md](project/perf-and-qol-backlog.md) — perf/GPU findings + the UI V2 plan
- [project/ideas-backlog.md](project/ideas-backlog.md) — unsorted idea pool (security, personality, memory, app, frontend)

Issues and planned work are tracked on [GitHub Issues](https://github.com/ryaeh/celestia/issues).

## Archive

Finished plans and point-in-time snapshots, kept for history:

- [archive/optimization-plan.md](archive/optimization-plan.md) — the (completed) code-review optimization pass
- [archive/audit-2026-06.txt](archive/audit-2026-06.txt) — full codebase audit snapshot (Jun 2026)
- [archive/companion-roadmap.md](archive/companion-roadmap.md) — original standalone M-phase track (now folded into roadmap.md)

## Testing

- [testing/checklist.md](testing/checklist.md) — manual test pass (run after larger changes)

## Changelog

- [../CHANGELOG.md](../CHANGELOG.md) — what shipped in each phase
