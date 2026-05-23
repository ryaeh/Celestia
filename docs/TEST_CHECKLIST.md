# Celestia — test checklist

## 0. Preflight

```powershell
cd C:\celestia
.\venv\Scripts\python.exe run_celestia.py --trust-config
.\venv\Scripts\python.exe run_celestia.py --check
```

---

## Phase 3 — Scoped + file_read

In `-i`:

```
scope scoped
open calc
open notepad
read C:\celestia\config.yaml
scope
```

Tray yellow (scoped) → voice: “open notepad”.

Blocked checks:

```
scope safe
open notepad
```

---

## Phase 2.5 — Security

```
arm
open notepad
disarm
```

Audit: `Get-Content logs\tool_audit.jsonl -Tail 5`

---

## Phase 2 — Screen

```
screen Read every line of text in this image exactly
```

Tight crop on CMD/text.

---

## Memory

```
remember my favorite color is blue
what is my favorite color
memory
```

---

## Clear memory

```powershell
.\venv\Scripts\python.exe run_celestia.py --forget-memory
```
