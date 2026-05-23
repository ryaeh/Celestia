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

Long-term facts (Chroma) are separate from **chat session** (recent turns in `-i`).

- Every few turns (config `memory.session_consolidate_every`), Celestia may auto-save 0–3 summarized user facts — no confirm. Look for `[memory] saved: …`
- `newchat` — consolidates remaining session, then clears chat history

- `memory` — list facts
- `forget` — wipe everything (asks yes/no)
- `forget <text>` — drop lines that contain that text
- Agent `memory_edit` — update a fact by id from `memory`

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
.\venv\Scripts\python.exe run_celestia.py --settings
.\venv\Scripts\python.exe run_celestia.py --logs 30
```

## Tray window

- **Security** — cycles safe → scoped → armed (tooltip; icon letter S/C/A)
- **Chat** — keeps going until you hit Enter on an empty line
- **Voice** — one shot per use
- **Screen** — submenu: region, fullscreen, active window

```powershell
.\venv\Scripts\python.exe run_celestia.py --tray
```
