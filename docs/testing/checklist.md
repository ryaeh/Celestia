# Test checklist

Run through this after a big change. Not automated — just a sanity pass.

**Preflight**

```powershell
cd C:\celestia
.\venv\Scripts\python.exe run_celestia.py --trust-config
.\venv\Scripts\python.exe run_celestia.py --check
```

**Scoped**

In `-i`: `scope scoped` → `open calc`, `open notepad`, `read` a file under workspace, `scope`.  
`write C:\celestia\docs\test-scoped.txt|hello` (under repo) → read it back.  
`clip` / `clip set test` — clipboard round-trip.  
Tray on scoped → voice “open notepad”.  
Then `scope safe` → `open notepad` should fail; `write` should fail.

**file_write overwrite**

In scoped: write same path twice without confirm → blocked; with agent `confirm_overwrite=true` or REPL yes → succeeds.

**Armed**

`arm` → `open notepad` → `disarm`. Peek at `logs\tool_audit.jsonl`.

**Screen**

`screen Read every line of text in this image exactly` — tight crop on CMD.  
`screen window …` for a single window.

**Memory**

Remember a color, ask it back, `memory`, then `--forget-memory` if you want a clean slate.
