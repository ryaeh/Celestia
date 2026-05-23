# Shipped vs backlog audit (2026-05-23)

Comparison of `main` vs [backlog.md](backlog.md) and Linear team **Celestia** (CC-*). Use this when cleaning issues.

## Shipped on `main` (removed from backlog; no separate Linear issues)

| Feature | Where |
|---------|--------|
| `file_write` + scope gates | `skills/files/tools.py`, `scope.py` |
| Clipboard read/write | `skills/clipboard/` |
| URL allowlist + smart `open github` | `url_policy.py`, `open_dispatch.py`, `security.policy.yaml` |
| Session chat (`-i`) | `config.yaml` `chat.session_*`, `agent.py` |
| Session → long-term memory | `session_consolidate.py` |
| Settings UI spike | `ui/settings_app.py` |
| n8n webhook on mode change | `skills/integrations/n8n.py` |
| Tray screen menu (flat) | `ui/tray.py` |
| Integrity trust (config + policy) | `security.py` |
| `tray_max_mode` (tray/voice cap) | `security.py`, `ui/tray.py`, `config.yaml` |
| Expanded app allowlist | `security.policy.yaml`, `scope.py` `_BUILTIN_EXE` |
| Desktop shell v1 (Tauri) | `shell/`, `shell_server.py`, `--shell`, `--settings` |

## Backlog kept (reworded or unchanged)

| Item | Action |
|------|--------|
| Session chat memory (tray/voice) | **Reworded** — `--tray-chat` exists but separate console; goal is in-tray/UI session |
| Everything else in backlog.md | Kept with **Horizon** + **Done when** columns |

## Linear

| Issue | Action |
|-------|--------|
| CC-1 … CC-4 | Onboarding — **Canceled** |
| CC-44 … CC-46 | Won't do — already **Canceled** |
| CC-5 … CC-43 | **Updated** descriptions + horizon labels — see [linear-views.md](linear-views.md) |

No Linear issues were filed for shipped-only features (file_write, clipboard, etc.).
