# Commands

Works from interactive mode (`-i`), one-off CLI, and the tray console. Security mode is shared (see `data/security_state.json` when `shared_armed_state` is true).

The app’s `help` command is always current; this page is the same stuff in prose.

## Chat

Anything that isn’t a command below goes to the agent. Whether it can run PC tools depends on your mode.

## Security

- `arm` — full PC control
- `disarm` — same as `scope safe`
- `status` — mode, memory inject, personality
- `scope` — show mode, workspaces, allowlist
- `scope safe` — no PC tools
- `scope scoped` — allowlisted apps + `read` / `write` in workspaces
- `scope armed` — same as `arm`
- `scope add <path>` / `scope remove <path>` — workspaces for this session

CLI: `--arm "message"`, `--disarm`

## Open apps (no AI)

- `open notepad`, `open calc`, etc. — only if mode allows

## Files

- `read <path>` — in scoped mode, only under your workspaces; armed is much wider
- `write <path>` — paste content (empty line to finish), or `write path|content` on one line
- Agent tool `file_write` — same rules; use `confirm_overwrite=true` if the file exists

## Clipboard

- `clip` / `clipboard` — read text from clipboard
- `clip set <text>` — copy to clipboard (confirms if replacing existing text)

## Memory

Global long-term memory (Chroma/mem0) is shared across shell, tray, and CLI. Entries are typed: **facts**, **instructions**, **summaries**, and **tasks**.

- **Auto-save:** `session_consolidate_mode: auto` extracts memories every N turns and on new chat / quit. Saves are silent; see the shell **Memory** page or `data/memory/activity_feed.jsonl`.
- **Inject:** `inject: always_budgeted` loads up to ~8 relevant items each turn; greetings also get the **last session** note (`data/memory/last_session.json`).
- `newchat` — consolidates the current chat, updates last-session, then starts fresh
- `memory` — list stored entries (with kind)
- `forget` — wipe everything (asks yes/no)
- `forget <text>` — drop lines that contain that text
- Agent `memory_add` / `memory_edit` — manual add or update (optional `kind` on add)
- Shell **Memory** page — list, add, edit, delete entries; refresh last-session note

Long-term plan (M phases): [companion-roadmap.md](../project/companion-roadmap.md)

## Voice

- `listen` — ~5 seconds, transcribe, reply

Tray: **Voice (PTT)** or **Ctrl+Alt+V** (from config).

## Screen

Always asks before sending the image. For CMD or a text file, crop tight and say something like “read every line exactly.”

- `screen` — uses `vision.default_mode` from config (usually region)
- `screen <question>`
- `screen region [question]` — drag a box, Esc cancels
- `screen fullscreen [q]`
- `screen window [q]` — active window only

CLI:

```powershell
.\venv\Scripts\python.exe run_celestia.py --screen "question"
.\venv\Scripts\python.exe run_celestia.py --screen "question" --screen-mode active_window
```

Tray **Ctrl+Shift+S** uses the config default. Menu **Screen** → Region / Fullscreen / Active window.

More detail: [vision.md](vision.md)

## Other

- `help` — print commands
- `tray` — start tray from `-i`
- empty line in `-i` — quit

CLI utilities:

```powershell
.\venv\Scripts\python.exe run_celestia.py --pick-workspace
.\venv\Scripts\python.exe run_celestia.py --settings    # Tauri shell (ui.shell_settings: true)
.\venv\Scripts\python.exe run_celestia.py --shell       # Home + live status
.\venv\Scripts\python.exe run_celestia.py --shell-server
.\venv\Scripts\python.exe run_celestia.py --logs 30
```

Set `ui.shell_settings: false` in `config.yaml` to use the legacy tk settings window instead.

## Tray window

- **Security** — cycles safe → scoped → armed (tooltip; icon letter S/C/A)
- **Chat** — opens the desktop shell (`ui.shell_settings: true`); same session as Home chat and voice PTT
- **Voice (PTT)** — global hotkey; replies append to the **active** shell chat session
- **Screen** — submenu: region, fullscreen, active window

Session file: `data/shell_chat/sessions.json` (config: `ui.shell_chat_store`).

```powershell
.\venv\Scripts\python.exe run_celestia.py --tray
```
