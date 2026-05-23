# Pick up here (Celestia)

## Daily start

```powershell
cd C:\celestia
.\venv\Scripts\python.exe run_celestia.py -i
```

In chat type **`help`** for full command list.

Tray (separate window):

```powershell
.\venv\Scripts\python.exe run_celestia.py --tray
```

## Security modes (shared: `-i`, tray, voice)

| Mode | How to set |
|------|------------|
| **safe** | `disarm` or `scope safe` |
| **scoped** | `scope scoped` — notepad/calc + `read` in workspaces |
| **armed** | `arm` or `scope armed` — full PC |

**Tray:** menu **Security: Safe -> Scoped** (click to cycle). Hover the tray icon for tooltip. Icon letter: **S** / **C** / **A** (Windows often does not show icon colors).

**Tray chat:** menu **Chat (multi-turn)** — keeps prompting `you>` until you press Enter on an empty line (not one message only).

## Next session

- [ ] `file_write`
- [ ] Clipboard

## Docs

- [SETUP.md](SETUP.md)
- [PHASE3_SCOPED_ACCESS.md](PHASE3_SCOPED_ACCESS.md)
- [ROADMAP.md](ROADMAP.md)
