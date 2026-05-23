# Phase 2.5 — Security (before Phase 3)

Goal: make Celestia safer **before** we add files, clipboard, and automation.  
Polish (big toggle, history viewer) lands in **Phase 4 UI**; the **rules and logs** land here.

---

## Threat model (simple)

Celestia runs as **you**. Anything on the PC that can run Python or click tray/hotkeys can try to use Celestia like a remote control.

We are **not** building antivirus. We are adding:

1. **Default safe** — dangerous tools off unless you opt in  
2. **Proof** — audit log when something runs  
3. **Notice** — warn if config was changed unexpectedly  

---

## 1. Armed mode

**Idea:** PC control (PowerShell, open app, open URL) only works when **armed**.

| State | Chat / memory / TTS / STT | PC tools |
|--------|----------------------------|----------|
| **Disarmed** (default) | Yes | Blocked |
| **Armed** | Yes | Allowed (still denylist + allowlists) |

### Phase 2.5 (backend)

- Config: `security.default_armed: false`
- CLI: `--arm` for one session; `--disarm` to turn off
- Tray: simple menu item **Arm PC control** / **Disarmed** (text + icon color)
- **Shared state:** `data/security_state.json` — `arm` in `-i` applies to **tray + voice** (default `shared_armed_state: true`)

### Phase 4 (UI)

- Big **ARMED** / **SAFE** toggle on main screen  
- Red/green indicator in tray  
- Optional: require typing `ARM` or short PIN before arming (later)

Vision and voice can stay available while disarmed; only **PC manipulation** is gated.

---

## 2. Tool audit log (“cool” but useful)

Same spirit as `logs/vision_audit.jsonl` — one line per event, easy to grep.

**File:** `logs/tool_audit.jsonl`

Each line (JSON):

```json
{
  "ts": "2026-05-20T14:30:00Z",
  "tool": "run_powershell",
  "armed": true,
  "source": "cli",
  "summary": "Get-Process | Select -First 5",
  "result": "ok"
}
```

- No full secrets; truncate long commands  
- `source`: `cli` | `tray` | `repl` | `screen`  
- Phase 4: small **Activity** panel — last 20 lines, filter by tool  

---

## 3. Config integrity check (easy, no Windows magic)

**Not** full code signing — just “did `config.yaml` change since you trusted it?”

1. First run (or `run_celestia.py --trust-config`): save SHA256 of `config.yaml` → `data/config.trust`  
2. Every startup: hash again; if different → print warning and log to `logs/security_events.jsonl`  
3. User runs `--trust-config` again after intentional edits  

### Persists across restarts?

**Yes.** `data/config.trust` stays until you delete it or run `--trust-config` again. Not wiped on reboot.

### If someone deletes the trust file and re-runs `--trust-config` on a hacked config?

The new hash becomes the baseline — warnings stop. That is why this is a **change detector for you**, not proof against an attacker with full disk access. Use armed mode + audit logs; treat unexpected `--trust-config` as suspicious.

Uses normal Python `hashlib` — no special system API.

---

## 4. UAC (what it means for you)

**UAC** = *User Account Control* — the Windows popup that asks “Do you want to allow this app to make changes?” when something tries to run as **Administrator**.

**For Atlas:**

- Run Atlas as a **normal user** (your daily account).  
- Do **not** “Run as administrator” on `run_atlas.py` or the future desktop app.  
- Keep UAC **on** (default in Windows 11).  

Why: if Atlas is admin, malware that drives Atlas gets admin too. Disarmed + non-admin = much smaller blast radius.

You do not need to configure UAC specially for Atlas — just don’t elevate the app.

---

## 5. What stays from Phase 0–2

- PowerShell denylist  
- Hide `open_path` / `open_url` unless message looks like an open request  
- Vision confirm + `vision_audit.jsonl`  

Armed mode stacks **on top** of these.

---

## 6. Implementation order (Phase 2.5 checklist)

- [x] `security` section in `config.yaml`  
- [x] `celestia_core/security.py` — armed state, gate `execute_tool`  
- [x] `--arm` / `--disarm` / `--trust-config`  
- [x] Tray arm/disarm menu item (icon color: red=armed, blue=safe)  
- [x] `logs/tool_audit.jsonl` on every tool call  
- [x] Config integrity check on startup  
- [x] REPL: `arm` / `disarm` / `status`  
- [x] Shared armed state (`-i` + tray + CLI) via `data/security_state.json`  
- [ ] Phase 4 Activity UI for audit tail  

**Stop Phase 3 until** armed + audit + integrity are done (your call — recommended).

---

## 7. Phase 4 UI hooks (design only for now)

- Main toggle: Armed / Safe  
- Activity tab: tool + vision audit tail  
- Settings: “Trust config again”, “Start disarmed”, optional PIN  

---

## Test ideas

```powershell
# Disarmed — should refuse PC tools
.\venv\Scripts\python.exe run_atlas.py "open notepad"

# Armed — should work
.\venv\Scripts\python.exe run_atlas.py --arm "open notepad"

# Audit
Get-Content logs\tool_audit.jsonl -Tail 5

# Integrity — edit config.yaml, restart, expect warning
```
