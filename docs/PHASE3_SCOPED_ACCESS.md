# Phase 3+ — Scoped access (replace “arm for everything”)

Your idea: **filter by where actions happen**, not one global arm for every open/launch.

Armed mode stays as **“full PC control”**. Scoped mode is the **daily driver**: safe folders + safe apps only.

---

## Three security levels (target)

| Level | Voice / chat / vision | Open apps | Files | PowerShell |
|-------|----------------------|-----------|-------|------------|
| **Safe** (default) | Yes | Blocked | Blocked | Blocked |
| **Scoped** | Yes | Allowlist only | Allowlist roots only | Read-only or off |
| **Armed** | Yes | Broad (denylist) | Broad | Denylist |

Today: Safe ↔ Armed only. **Scoped** is Phase 3.

---

## What gets filtered

### 1. By action type (process / tool)

Already logged in `logs/tool_audit.jsonl` as `source`: `cli` | `repl` | `tray`.

Later: tag **risk class** per tool:

- `low` — `open_path` if target in app allowlist  
- `medium` — `file_read` under workspace  
- `high` — `file_write`, `run_powershell`, `open_url`  

Scoped mode allows **low + medium** without arm; **high** needs arm or one-time confirm.

### 2. By path (files & launches)

**Protected prefixes (deny by default — your “extra layer”):**

Anything that **targets** these paths is blocked in scoped mode, even if the app is on the allowlist:

- Open **folder** `C:\Windows\System32` → block  
- Open **file** `C:\Windows\System32\config.sys` in Notepad → block  
- **Write** under `C:\Windows\`, `C:\Program Files\`, etc. → block  
- Launch **random** `C:\Windows\System32\evil.exe` → block  

**Exception (explicit allowlist only):**

- Launch **`C:\Windows\System32\notepad.exe`** by full path → allow (classic Not Defteri lives there; launching the binary is normal)  
- Not the same as “do anything in System32” — only named executables you whitelist by **full path**

Later Linux: `/etc`, `/usr/bin` (with per-binary exceptions like `/usr/bin gedit`), others’ `$HOME`.

**Allowed roots (user-defined):**

```yaml
security:
  mode: scoped          # safe | scoped | armed  (armed = today’s shared_armed_state)
  workspaces:
    - C:\Users\you\Projects
    - C:\Users\you\Documents\Celestia
  app_allowlist:
    - notepad
    - notepad.exe
    - code
    - "C:\\Program Files\\Notepad++\\notepad++.exe"
  url_allowlist: []     # empty = block all URLs in scoped
```

**Rules (defense in depth):**

1. **Protected prefix** — if the target path is under `Windows\`, `System32\` (as data/folder), `Program Files\`, etc. → **deny** unless a narrow exception applies.  
2. **Executable launch** — resolve binary to full path; allow only if in `allowed_executables` (full paths), not “any .exe under System32”.  
3. **Workspace** — file read/write only under user `workspaces`.  
4. **App nickname** — `notepad` → maps to one fixed `System32\notepad.exe`, not “run whatever is in System32”.

### 3. By origin (optional later)

Example: tray voice may only use **scoped**, never armed, unless user enables in config:

```yaml
security:
  tray_max_mode: scoped
```

---

## How you’ll configure it (phases)

| Phase | UX |
|-------|-----|
| **3a** | Done — `scope` / `scope scoped` / config allowlists |
| **3b** | `file_read` / `file_write` under workspaces |
| **3c** | CLI wizard: `run_celestia.py --pick-workspace` (prints paths to paste) |
| **4** | UI: folder picker, toggles Safe / Scoped / Armed, protected-path presets |

---

## Implementation sketch (Windows now, Linux-ready)

```
celestia_core/
  security.py          # armed + shared state (done)
  scope.py             # NEW: path normalize, is_allowed, mode check
  platform/
    __init__.py        # get_platform() -> windows | linux
    windows.py         # resolve path, protected prefixes
    linux.py           # XDG paths, /home/... (stub until summer)
skills/
  pc_control/
    tools.py           # gate open_path via scope.check_app()
  files/               # NEW Phase 3: read_file, write_file under workspace
```

**Path checks (both OS):**

1. Resolve to absolute path (no `..` escape).  
2. Deny if under protected prefix.  
3. Allow if under any workspace root OR exact app allowlist entry.  
4. Audit every deny with reason.

**Linux (summer):**

- Same `config.yaml` shape with POSIX paths: `/home/you/projects`  
- `open_path` → `xdg-open` or `subprocess` with allowlist  
- Tray/hotkeys: portal or pynput on X11/Wayland (separate phase)  
- No rewrite of agent/memory — only `platform/` + pc_control backends  

---

## Suggested build order

1. **Phase 3a** — `scope.py` + workspace allowlist; `open_path` works in **scoped** without arm for notepad etc.  
2. **Phase 3b** — `file_read` / `file_write` only under workspaces.  
3. **Phase 3c** — REPL `scope` commands + clipboard (scoped).  
4. **Phase 4** — UI picker + security mode dropdown.  
5. **Phase 5 / summer** — `platform/linux.py`, test on your distro.

---

## Relation to current armed mode

- Keep **shared armed state** for “I trust CC with everything right now.”  
- Add **`security.mode: scoped`** so voice can open Notepad / edit project files **without** arm.  
- **Arm** = escalate to full PC for one session (or until disarm).

---

## Notepad and System32 (are you wrong?)

You are **right to be suspicious**, but two cases differ:

| Action | Risk | Celestia policy |
|--------|------|-----------------|
| **Run** `System32\notepad.exe` | Low if it is the real Microsoft binary (normal install location) | Allow via **one fixed full path**, not “anything in System32” |
| **Open/edit files inside** System32 | High (hosts, configs, drivers) | **Block** in scoped mode |
| **Open** System32 as a folder | High | **Block** |
| User says “open notepad” and model passes `System32\malware.exe` | High | Block — only whitelisted full paths for launches |

Notepad the **program** from System32 is fine; Notepad used to **touch sensitive paths** is what we block.

`cmd.exe`, `powershell.exe`, `regedit.exe` under System32 should **never** be in the executable allowlist in scoped mode.

---

## Opinion

| Verdict | Why |
|---------|-----|
| **Strong fit** | Matches “companion on *my* stuff”, not raw admin bot |
| **Path deny layer** | Your idea is correct — **allowlist apps + deny protected paths** together |
| **Better than arm-only** | Daily use: scoped; rare: armed |
| **Linux** | Same model: deny `/etc`, allow `/usr/bin/gedit` by full path only |
| **Do not skip** | Add scope **before** wide file/clipboard tools in Phase 3 |

Armed was the right Phase 2.5 step. Scoped access + **protected path blocking** is the right Phase 3 centerpiece.
