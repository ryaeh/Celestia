# Security

Celestia runs as you. It can only do what your user can do — the point of modes is to stop the *model* from driving the PC unless you meant it.

## Three modes

**Safe** — talk, remember things, voice, screen. No opening apps, no file tools, no PowerShell.

**Scoped** — safe stuff plus allowlisted apps (notepad, calc, paint, …) and `read` only in folders you’ve added. Good default for daily use.

**Armed** — broad PC control. Denylist and confirmations still exist, but you’re trusting her more.

```
scope safe
scope scoped
scope armed
arm          # same as armed
disarm       # same as safe
```

Tray **Security** cycles modes. With `shared_armed_state: true`, `-i`, tray, and voice see the same mode via `data/security_state.json`.

## Scoped: what’s blocked

We block the scary stuff even if the model asks nicely:

- Browsing `System32` as a folder
- Editing files under Windows / Program Files
- Launching random `.exe` from System32

**Allowed:** whitelisted apps by nickname (`notepad` → the real `System32\notepad.exe`) or full paths you put in config. Not “any exe in System32.”

Never on the allowlist in scoped: `cmd`, `powershell`, `regedit`.

**Files:** `read` only under workspaces:

```
scope add C:\Users\you\Projects
read C:\Users\you\Projects\readme.md
```

Allowlists and workspaces live in **`security.policy.yaml`** (apps, URLs, folders). Mode and audit settings stay in **`config.yaml`**. Malware with your user rights can edit any local file — `run_celestia.py --trust-config` hashes both files so unexpected changes show a warning on start.

## Armed

For PowerShell, odd apps, URLs. Default is safe/disarmed.

```powershell
.\venv\Scripts\python.exe run_celestia.py --arm "open notepad"
```

Voice and screen work fine in safe mode — only PC manipulation is gated.

## Audit log

`logs/tool_audit.jsonl` — one JSON line per tool: time, tool name, mode, where it came from (`cli`, `repl`, `tray`, `screen`), short summary, ok/fail.

```powershell
Get-Content logs\tool_audit.jsonl -Tail 10
```

Screenshots: `logs/vision_audit.jsonl` (no image bytes).

## Config integrity

1. `run_celestia.py --trust-config` saves hashes of `config.yaml` and `security.policy.yaml` to `data/config.trust`
2. Next start: if either file changed, you get a warning
3. You edited on purpose? Run `--trust-config` again

**URL allowlist (scoped):** use a short label (`github`) or full host (`github.com`). Both allow `https://github.com`. If you list `github.com` and `github.io`, `open github` asks which one.

That’s for *you* noticing unexpected edits — not protection against someone who already owns your disk. Use scoped mode and read the audit log when something feels off.

## UAC

Run as a normal user. Don’t “Run as administrator” on Celestia. Leave UAC on.

## Notepad vs System32

Running `notepad.exe` from System32 is fine — it’s on the allowlist. Using Notepad to open `hosts` or poking around System32 as a folder is not.

## Not built yet

`file_write`, clipboard, activity UI in a proper app, optional PIN before arm — [backlog](../project/backlog.md).
