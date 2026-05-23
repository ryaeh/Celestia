# Pick up here

```powershell
cd C:\celestia
.\venv\Scripts\python.exe run_celestia.py -i
```

`help` in chat lists commands.

Tray in another window:

```powershell
.\venv\Scripts\python.exe run_celestia.py --tray
```

**Modes** (same in `-i`, tray, and voice if shared state is on):

- safe — `disarm` or `scope safe`
- scoped — `scope scoped` (notepad/calc + read/write in workspaces + clipboard)
- armed — `arm` or `scope armed`

Tray **Security** menu cycles them. Tooltip shows S / C / A — Windows often won't color the icon.

**Settings / logs:**

```powershell
.\venv\Scripts\python.exe run_celestia.py --settings
.\venv\Scripts\python.exe run_celestia.py --logs
.\venv\Scripts\python.exe run_celestia.py --pick-workspace
```

**Next:** Phase 4 Tauri UI — see [backlog.md](backlog.md).

**Docs:** [README.md](../README.md) · [getting-started.md](../getting-started.md) · [guide/commands.md](../guide/commands.md)
