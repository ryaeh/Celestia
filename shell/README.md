# Celestia desktop shell

Tauri 2 + React + TypeScript UI. Python stays the brain — the shell talks to `celestia_core/shell_server.py` on localhost.

## Prerequisites

- Node.js 20+
- Rust ([rustup.rs](https://rustup.rs/))
- WebView2 (Windows 10/11)

One-time:

```powershell
cd C:\celestia\shell
npm install
```

## Run

From repo root (starts API + dev window):

```powershell
.\venv\Scripts\python.exe run_celestia.py --shell
```

Settings route:

```powershell
.\venv\Scripts\python.exe run_celestia.py --settings
```

## Dev (hot reload)

Terminal 1 — API only:

```powershell
.\venv\Scripts\python.exe run_celestia.py --shell-server
```

Terminal 2 — Vite + Tauri:

```powershell
cd shell
$env:VITE_SHELL_API="http://127.0.0.1:8765"
npm run tauri dev
```

Or use `--shell` which sets `VITE_SHELL_API` and `VITE_SHELL_ROUTE` automatically.

## API (127.0.0.1)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/status` | Mode, personality, Ollama preflight |
| POST | `/mode` | Set mode (not capped by `tray_max_mode`) |
| GET | `/workspaces` | Scoped workspace paths |
| GET | `/audit/tail?n=20` | Recent tool audit lines |

Port: `ui.shell_port` in `config.yaml` (default `8765`).

## Config

```yaml
ui:
  shell_port: 8765
  shell_settings: true   # --settings → shell; false → tk window
```

## Agents / cloud

- Do not bundle secrets in the shell.
- Prefer `run_celestia.py --shell-server` + `npm run tauri dev` for UI iteration.
- Preview UI at `http://localhost:1420` when Vite is running.
