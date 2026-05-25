# Dev workflow

Personal notes on how this project is organized and how to move work through it. Private repo — this is for picking up context, not for external contributors.

---

## Session startup

```powershell
cd C:\celestia
.\venv\Scripts\python.exe run_celestia.py --check   # verify services
.\venv\Scripts\python.exe run_celestia.py -i         # start working
```

For the shell:

```powershell
# One-shot (starts Python server + opens Tauri window)
.\venv\Scripts\python.exe run_celestia.py --shell

# Dev hot-reload (two terminals)
.\venv\Scripts\python.exe run_celestia.py --shell-server
cd shell && npm run tauri dev
```

See [resume.md](resume.md) for the quick cheat sheet.

---

## Adding a backlog item

1. Add a row to [backlog.md](backlog.md) with **Horizon** (`short` / `long` / `opt`) and **Status** (`planned` / `exploring` / `deferred`).
2. Create a matching Linear issue on team **Celestia** with the same horizon label (`short-term`, `long-term`, `optimization`) and a priority label (`high priority`, `natural priority`, `low priority`).
3. Write a clear **Done when** description — one sentence that makes it obvious when the ticket is shippable.

Horizon guide:

| Horizon | Meaning |
|---------|---------|
| `short` | Next 1–2 weeks, active priority |
| `long` | Phase 4+, large features, platform work |
| `opt` | UX polish, perf, model routing — anytime |

---

## Shipping a feature

1. Code → `python3 -m py_compile <file>` syntax check.
2. Run the relevant section of [testing/checklist.md](../testing/checklist.md).
3. Mark the Linear issue **Done**.
4. Remove the row from [backlog.md](backlog.md).
5. Add an entry to [shipped-audit.md](shipped-audit.md) if it was a notable feature.
6. Update the relevant `docs/guide/` page (or create one if it is a new feature area).
7. Add a line to [CHANGELOG.md](../../CHANGELOG.md) under the current phase.
8. Run `--trust-config` if `config.yaml` or `security.policy.yaml` changed.

---

## Linear issue ID map

- **CC-1–CC-4** — Onboarding, canceled.
- **CC-6–CC-46** — Duplicates, archived, labeled `low priority`. Use **CC-47+** when planning.
- **CC-47–CC-87** — Canonical backlog (re-imported May 2026).
- **CC-88–CC-113** — Next cycle tickets (from the May 2026 project review). See [roadmap.md](roadmap.md).

When creating a new issue, use the next available CC-N number. The Linear team auto-assigns sequential IDs — just note the ID in the backlog row.

---

## Linear views

See [linear-views.md](linear-views.md) for the recommended filter setup.

Quick access:

| View | Filter |
|------|--------|
| Do next | Label = `high priority`, State = Backlog or In Progress |
| Normal backlog | Label = `natural priority`, State is not Done/Canceled |
| Later | Label = `low priority` |

---

## Config changes

After editing `config.yaml` or `security.policy.yaml`:

```powershell
.\venv\Scripts\python.exe run_celestia.py --trust-config
```

This re-hashes the files so the integrity check does not warn on next startup. See [security.md](security.md).

---

## Syntax checking (no test suite yet)

```powershell
# Check a single file
.\venv\Scripts\python.exe -m py_compile celestia_core/agent.py

# Check all Python files
Get-ChildItem -Recurse -Filter "*.py" | ForEach-Object {
    .\venv\Scripts\python.exe -m py_compile $_.FullName
}
```

A formal pytest suite is on the backlog (CC-112). Until then, run the manual [checklist](../testing/checklist.md) after larger changes.

---

## Data directories

| Path | Contents | Reset? |
|------|----------|--------|
| `data/chroma/` | Long-term vector memory | `rmdir /S /Q data\chroma` — wipes all memories |
| `data/shell_chat/sessions.json` | Chat session store | `del` to start fresh; loses history |
| `data/memory/last_session.json` | Last-session note | Safe to delete; regenerates on next `newchat` |
| `data/memory/activity_feed.jsonl` | Memory event log | Safe to delete |
| `data/config.trust` | Config integrity hashes | Delete + run `--trust-config` to rebuild |
| `data/security_state.json` | Shared mode state | Resets to `safe` on next start if deleted |
| `logs/tool_audit.jsonl` | Tool call audit log | Safe to rotate/delete |
| `logs/vision_audit.jsonl` | Vision audit log | Safe to rotate/delete |

---

## Architecture quick reference

| Layer | Files | Notes |
|-------|-------|-------|
| Entry | `run_celestia.py` | CLI flags, tray, shell launch |
| Agent loop | `celestia_core/agent.py` | LLM → tools → memory inject |
| Shell API | `celestia_core/shell_server.py` | HTTP server, all routes |
| Shell frontend | `shell/src/` | React + Tauri |
| Skills | `skills/*/tools.py` + `skills/registry.py` | Add new tools here |
| Memory | `skills/memory/store.py` | mem0 + Chroma CRUD |
| Security | `celestia_core/security.py` + `scope.py` | Mode, gates, audit |
| Config | `celestia_core/config.py` | Reads `config.yaml` |

Full details: [reference/architecture.md](../reference/architecture.md).
