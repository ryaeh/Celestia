# Test checklist

Manual sanity pass after significant changes. Not automated — run the relevant sections only.

```powershell
cd C:\celestia
.\venv\Scripts\python.exe run_celestia.py --trust-config
.\venv\Scripts\python.exe run_celestia.py --check
```

---

## Core REPL (`-i`)

```powershell
.\venv\Scripts\python.exe run_celestia.py -i
```

- [ ] Type a message — reply comes back, no crash.
- [ ] `status` — shows mode, personality, memory inject.
- [ ] `memory` — lists stored entries (or "none" cleanly).
- [ ] `help` — prints command list.

---

## Security modes

In `-i`:

- [ ] `scope scoped` → `open calc` → calc opens.
- [ ] `open notepad` → Notepad opens (not Store notepad).
- [ ] `read <path-under-workspace>` → returns file contents.
- [ ] `scope safe` → `open notepad` → blocked message.
- [ ] `scope safe` → `write C:\celestia\docs\test.txt|hello` → blocked.
- [ ] `arm` → `scope` shows `armed` → `disarm` returns to `safe`.
- [ ] Check `logs\tool_audit.jsonl` — entries appear for tool calls.

---

## File write / overwrite

In scoped mode (workspace includes `C:\celestia`):

- [ ] `write C:\celestia\docs\test-scoped.txt|hello` → succeeds.
- [ ] Same path again → blocked (no `confirm_overwrite`).
- [ ] Agent tool with `confirm_overwrite=true` → succeeds.
- [ ] `read C:\celestia\docs\test-scoped.txt` → returns `hello`.
- [ ] Delete the test file after.

---

## Clipboard

In `-i` (scoped):

- [ ] `clip` → reads current clipboard text.
- [ ] `clip set testvalue` → `clip` → shows `testvalue`.

---

## Memory

- [ ] `memory` in `-i` — lists entries cleanly.
- [ ] Tell Celestia a fact ("my favorite color is green") → ask it back after a few turns.
- [ ] `forget green` → entry removed.
- [ ] `newchat` → starts a fresh session, last-session note updates.

---

## Screen / vision

- [ ] `screen Read every line of text in this image exactly` — crop a CMD or text window.
- [ ] `screen window Read every line exactly` — active window capture.
- [ ] Confirm prompt appears before image is sent.
- [ ] `screen region` — drag a box, Esc cancels without sending.

---

## Voice

- [ ] `listen` in `-i` — records ~5s, transcribes, replies.
- [ ] Tray: **Voice (PTT)** → `Ctrl+Alt+V` → speak → reply comes back.
- [ ] TTS speaks the reply (if Orpheus loaded; else Edge TTS).

---

## Shell UI — startup

```powershell
.\venv\Scripts\python.exe run_celestia.py --shell
```

- [ ] Shell window opens.
- [ ] Status bar shows mode (Safe / Scoped / Armed) and Ollama status.
- [ ] Sidebar shows session history (or "No chats yet" cleanly).

---

## Shell UI — chat

- [ ] Type a message → reply appears in the chat thread.
- [ ] Long reply renders without overflow.
- [ ] `+ New Chat` in sidebar → new session created → chat thread clears.
- [ ] Click a previous session → thread loads that session's history.
- [ ] Chat persists after closing and reopening the shell window.

---

## Shell UI — PTT

- [ ] Hold the mic button → "Listening…" indicator appears.
- [ ] Release → reply appears in the chat thread (same session as typed chat).
- [ ] Right-click / cancel gesture → discards recording, no reply.
- [ ] While "Thinking…" is shown, sending another message is blocked.

---

## Shell UI — Memory page

Open **Memory** from the sidebar:

- [ ] Last-session note displays (or "No last-session note yet" cleanly).
- [ ] **Refresh** button regenerates the note from current session.
- [ ] **Add** a new entry → appears in the correct kind group.
- [ ] **Edit** an entry → text and kind update correctly.
- [ ] **Delete** an entry → removed from the list.
- [ ] Changes reflect in the next chat turn's memory inject.

---

## Shell UI — Settings page

- [ ] Settings page opens from sidebar.
- [ ] Mode selector (Safe / Scoped / Armed) changes mode — verify with `GET /status`.
- [ ] Workspaces list loads.

---

## Tray

```powershell
.\venv\Scripts\python.exe run_celestia.py --tray
```

- [ ] Tray icon appears in system notification area.
- [ ] **Security** menu cycles Safe → Scoped → Armed.
- [ ] **Chat** opens the shell window (or console fallback if shell not started).
- [ ] **Screen → Region** captures and confirms before sending.
- [ ] Tray PTT hotkey (`Ctrl+Alt+V`) triggers voice input.
- [ ] `tray_max_mode` cap (if set) — tray cannot go above capped mode.

---

## After a config change

```powershell
.\venv\Scripts\python.exe run_celestia.py --trust-config
.\venv\Scripts\python.exe run_celestia.py --check
```

- [ ] No unexpected "config changed" warning on next start.

---

## Cleanup

```powershell
del C:\celestia\docs\test-scoped.txt   # if created during file tests
```
