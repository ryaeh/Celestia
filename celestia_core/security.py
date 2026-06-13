"""Armed/safe/scoped modes, tool audit log, config integrity."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from celestia_core.config import ROOT, get, load_config
from celestia_core.file_utils import atomic_write_text, file_lock

Mode = Literal["safe", "scoped", "armed"]

_MODE_RANK: dict[str, int] = {"safe": 0, "scoped": 1, "armed": 2}
_TRAY_SOURCES = frozenset({"tray", "voice", "screen"})

PC_TOOLS_ALWAYS_OK = frozenset({"get_system_status", "list_processes", "get_pc_specs"})
PC_TOOLS_SCOPED_BLOCK = frozenset({"run_powershell"})

# State-changing PowerShell/Cmd verbs + operators. A command matching any of these
# is NOT read-only and stays armed-only even when scoped read-only PowerShell is
# enabled. Matched anywhere in the string, so `Get-Date; Remove-Item x` is blocked.
_PS_MUTATING = re.compile(
    r"\b(Set|Remove|New|Add|Clear|Stop|Start|Restart|Suspend|Resume|Move|Copy|"
    r"Rename|Export|Import|Install|Uninstall|Register|Unregister|Disable|Enable|"
    r"Invoke|Write|Send|Push|Pop|Mount|Dismount|Format|Initialize|Reset|Update)-"
    r"|\bOut-File\b|\b(del|erase|rd|rmdir|mkdir|move|copy|ren|format)\b"
    r"|[>]|`",
    re.IGNORECASE,
)


def is_readonly_powershell(command: str) -> bool:
    """True if *command* looks read-only (Get-*, dir, ipconfig, …).

    Conservative: any state-changing verb/operator anywhere in the command makes
    it non-read-only. The deeper `BLOCKED_PS` safety denylist in pc_control still
    applies as a second layer at execution time.
    """
    cmd = (command or "").strip()
    if not cmd:
        return False
    return not _PS_MUTATING.search(cmd)
PC_TOOLS_SCOPE_CHECK = frozenset({"open_path", "file_read", "file_write"})
PC_TOOLS_SAFE_BLOCK = frozenset(
    {
        "run_powershell",
        "open_path",
        "open_url",
        "file_read",
        "file_write",
        "clipboard_write",
    }
)

_session_mode: Mode | None = None

# Cache of the parsed state file, keyed on its mtime. get_mode() is called on
# every gate/audit; re-reading + parsing the JSON each time is wasteful. The
# mtime key keeps it correct across tray/CLI/shell processes — any write (here
# or elsewhere) bumps the mtime and forces a re-read.
_state_cache: tuple[int, dict[str, Any]] | None = None


def _state_path() -> Path:
    return ROOT / "data" / "security_state.json"


def _state_lock_path() -> Path:
    return ROOT / "data" / ".security_state.lock"


def _use_shared_state() -> bool:
    if get("security.shared_armed_state", True):
        return True
    return bool(get("security.persist_armed_state", False))


def _read_state() -> dict[str, Any]:
    global _state_cache
    path = _state_path()
    try:
        mtime = path.stat().st_mtime_ns
    except OSError:
        return {}
    if _state_cache is not None and _state_cache[0] == mtime:
        return _state_cache[1]
    try:
        data = json.loads(path.read_text(encoding="utf-8")) or {}
    except (json.JSONDecodeError, OSError):
        return {}
    _state_cache = (mtime, data)
    return data


def _write_state(data: dict[str, Any]) -> None:
    global _state_cache
    data["updated"] = _now_iso()
    # The security mode gates all PC control and is shared across tray/shell/CLI
    # processes — serialize writes with a cross-process lock and write atomically
    # so a concurrent or crashed write can neither be lost nor corrupt the file.
    with file_lock(_state_lock_path()):
        atomic_write_text(_state_path(), json.dumps(data, indent=2))
    _state_cache = None  # invalidate; next read re-stats the freshly written file


def _default_mode() -> Mode:
    m = (get("security.mode", "safe") or "safe").lower()
    if m in ("safe", "scoped", "armed"):
        return m  # type: ignore
    return "safe"


def _mode_rank(mode: str) -> int:
    return _MODE_RANK.get(mode.lower(), 0)


def get_tray_max_mode() -> Mode | None:
    """Max mode tray/voice/screen may set; None = no cap."""
    raw = get("security.tray_max_mode")
    if raw is None or str(raw).strip() == "":
        return None
    m = str(raw).lower().strip()
    if m in _MODE_RANK:
        return m  # type: ignore
    return None


def effective_mode_for(mode: str, source: str | None) -> tuple[Mode, str | None]:
    """Apply tray_max_mode cap for tray-like sources. Returns (mode, warning)."""
    m = mode.lower()
    if m not in _MODE_RANK:
        raise ValueError(f"Invalid mode: {mode}")
    cap = get_tray_max_mode()
    if cap is None or (source or "") not in _TRAY_SOURCES:
        return m, None  # type: ignore
    if _mode_rank(m) > _mode_rank(cap):
        return cap, (
            f"[security] Tray/voice capped at {cap.upper()} "
            f"(security.tray_max_mode in config.yaml)"
        )
    return m, None  # type: ignore


def next_mode_cycled(current: str, *, max_mode: Mode | None = None) -> Mode:
    """Next mode in safe → scoped → armed cycle, optionally capped."""
    order: tuple[Mode, ...] = ("safe", "scoped", "armed")
    if max_mode is not None:
        order = tuple(m for m in order if _mode_rank(m) <= _mode_rank(max_mode))
        if not order:
            order = ("safe",)
    cur = current.lower()
    if cur not in order:
        cur = order[0]
    idx = order.index(cur)  # type: ignore[arg-type]
    return order[(idx + 1) % len(order)]


def get_mode() -> Mode:
    global _session_mode
    if _use_shared_state():
        data = _read_state()
        if "mode" in data:
            m = str(data["mode"]).lower()
            if m in ("safe", "scoped", "armed"):
                return m  # type: ignore
        if data.get("armed"):
            return "armed"
        return _default_mode()
    if _session_mode:
        return _session_mode
    return _default_mode()


def set_mode(mode: str, *, source: str | None = None) -> str | None:
    """Set security mode. Returns optional warning when capped for tray/voice."""
    global _session_mode
    effective, warn = effective_mode_for(mode, source)
    if _use_shared_state():
        _write_state({"mode": effective, "armed": effective == "armed"})
        _session_mode = None
    else:
        _session_mode = effective
    try:
        from skills.integrations.n8n import notify_security_mode

        notify_security_mode(effective, source=source)
    except Exception:
        pass
    return warn


def is_armed() -> bool:
    return get_mode() == "armed"


def set_armed(value: bool, *, source: str | None = None) -> None:
    set_mode("armed" if value else "safe", source=source)


def toggle_armed(*, source: str | None = None) -> bool:
    if get_mode() == "armed":
        set_mode("safe", source=source)
        return False
    set_mode("armed", source=source)
    return True


def armed_status_label() -> str:
    m = get_mode()
    cap = get_tray_max_mode()
    suffix = f", tray max {cap}" if cap else ""
    if m == "armed":
        return f"ARMED{suffix}"
    if m == "scoped":
        return f"scoped (allowlist){suffix}"
    return f"safe{suffix}"


def preflight_reply_from_blocked(blocked: str) -> str:
    return _preflight_reply(blocked)


def preflight_chat_pc(user_message: str) -> str | None:
    """
    Browser-open requests: run open_url or return blocked (no model hallucination).
    Other open requests: block honestly in safe mode.
    """
    from celestia_core.open_dispatch import (
        handle_open_in_browser_request,
        is_primary_open_request,
    )

    browser = handle_open_in_browser_request(user_message)
    if browser:
        return browser

    if not is_primary_open_request(user_message):
        return None

    low = user_message.lower()
    if re.search(r"\b(open|launch|start|browse|visit)\b", low):
        blocked = gate_pc_tool("open_path", {"path": "notepad"})
        if blocked:
            return _preflight_reply(blocked)

    return None


def _preflight_reply(blocked: str) -> str:
    mode = get_mode()
    if mode == "safe":
        tip = "Use `scope scoped` or `arm`, or type the command yourself: open https://…"
    elif mode == "scoped":
        tip = "Add the host to url_allowlist in security.policy.yaml, use `arm`, or: open https://…"
    else:
        tip = ""
    base = blocked if blocked.startswith("Blocked:") else f"Blocked: {blocked}"
    if tip:
        return f"I did not open anything. {base}\n\n{tip}"
    return f"I could not complete that. {base}"


def gate_pc_tool(name: str, arguments: dict[str, Any] | None = None) -> str | None:
    if name in PC_TOOLS_ALWAYS_OK:
        return None

    mode = get_mode()
    args = arguments or {}

    if mode == "safe":
        if name in PC_TOOLS_SAFE_BLOCK:
            return (
                "Blocked: PC control is safe (off). "
                "Use: scope scoped — allowlisted apps/folders | arm — full PC."
            )
        return None

    if mode == "scoped":
        if name == "run_powershell":
            cmd = str(args.get("command", ""))
            if get("security.scoped_allow_readonly_powershell", True) and is_readonly_powershell(cmd):
                return None  # read-only Get-*/dir/ipconfig etc. — allowed in scoped
            return (
                "Blocked in scoped mode (needs armed): that PowerShell changes state. "
                "Read-only commands (Get-*, dir, ipconfig, systeminfo) are allowed; "
                "type arm for full access."
            )
        if name == "open_url":
            from celestia_core.scope import check_open_url

            return check_open_url(str(args.get("url", "")))
        if name in PC_TOOLS_SCOPE_CHECK:
            from celestia_core.scope import check_file_read, check_file_write, check_open_path

            path = str(args.get("path", ""))
            if name == "file_read":
                return check_file_read(path)
            if name == "file_write":
                return check_file_write(path)
            return check_open_path(path)
        return None

    if mode == "armed":
        if name in ("file_read", "file_write"):
            from celestia_core.scope import check_file_read, check_file_write

            path = str(args.get("path", ""))
            if name == "file_read":
                return check_file_read(path)
            return check_file_write(path)

    return None


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _trust_path() -> Path:
    rel = get("security.integrity_store", "data/config.trust")
    p = Path(rel)
    return p if p.is_absolute() else ROOT / rel


def _config_path() -> Path:
    p = ROOT / "config.yaml"
    if p.exists():
        return p
    return ROOT / "config.example.yaml"


def _integrity_files() -> list[Path]:
    """Files whose integrity we baseline.

    The policy file is watched **even when absent** so that *creating* one later
    (e.g. malware writing itself into the app allowlist) is flagged, not just edits
    to an already-present file. ``trust_config`` records an absent file as ``null``.
    """
    from celestia_core.config import policy_path

    return [_config_path(), policy_path()]


def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _audit_path() -> Path:
    rel = get("security.audit_log", "logs/tool_audit.jsonl")
    p = Path(rel)
    return p if p.is_absolute() else ROOT / rel


def _security_events_path() -> Path:
    return ROOT / "logs" / "security_events.jsonl"


def _append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def audit_tool(
    name: str,
    arguments: dict[str, Any],
    result: str,
    *,
    source: str = "cli",
) -> None:
    if not get("security.audit_tools", True):
        return
    summary = _summarize_args(name, arguments)
    blocked = result.startswith("Blocked:")
    _append_jsonl(
        _audit_path(),
        {
            "ts": _now_iso(),
            "tool": name,
            "mode": get_mode(),
            "armed": is_armed(),
            "source": source,
            "summary": summary,
            "result": "blocked" if blocked else "ok",
            "detail": result[:200] if blocked else "",
        },
    )


def _summarize_args(name: str, arguments: dict[str, Any]) -> str:
    if name == "run_powershell":
        cmd = str(arguments.get("command", ""))
        return cmd[:120] + ("…" if len(cmd) > 120 else "")
    if name in ("open_path", "open_url"):
        return str(arguments.get("path") or arguments.get("url", ""))[:120]
    if name == "file_write":
        p = str(arguments.get("path", ""))[:80]
        return f"{p} ({len(str(arguments.get('content', '')))} chars)"
    if name in ("clipboard_read", "clipboard_write"):
        return str(arguments.get("text", ""))[:80]
    if name == "memory_add":
        return str(arguments.get("content", ""))[:80]
    if name == "memory_search":
        return str(arguments.get("query", ""))[:80]
    return json.dumps(arguments, ensure_ascii=False)[:120]


def trust_config() -> str:
    files = _integrity_files()
    # Present files get their sha256; a watched-but-absent file (the policy file)
    # is recorded as null so a later creation is detectable as tampering.
    digests: dict[str, str | None] = {
        p.name: (_hash_file(p) if p.exists() else None) for p in files
    }
    store = _trust_path()
    store.parent.mkdir(parents=True, exist_ok=True)
    store.write_text(
        json.dumps({"files": digests, "trusted_at": _now_iso()}, indent=2),
        encoding="utf-8",
    )
    present = [n for n, h in digests.items() if h is not None]
    absent = [n for n, h in digests.items() if h is None]
    msg = f"Trusted: {', '.join(present)}"
    if absent:
        msg += f" (watching for creation of: {', '.join(absent)})"
    return msg


def check_config_integrity() -> str | None:
    if not get("security.integrity_check", True):
        return None
    store = _trust_path()
    if not store.exists():
        return None
    try:
        data = json.loads(store.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return "Config integrity store is corrupt — run --trust-config"

    expected_files: dict[str, str | None] = data.get("files") or {}
    if not expected_files and data.get("sha256"):
        expected_files = {data.get("path", "config.yaml").split("\\")[-1].split("/")[-1]: data["sha256"]}

    if not expected_files:
        return None

    changed: list[str] = []
    for name, expected in expected_files.items():
        path = ROOT / name
        exists = path.exists()
        if expected is None:
            # Watched-but-absent at trust time → a newly-created file is suspicious
            # (the "malware adds itself to the allowlist" case).
            if exists:
                changed.append(f"{name} (added)")
        elif not exists:
            changed.append(f"{name} (removed)")
        elif _hash_file(path) != expected:
            changed.append(f"{name} (modified)")

    if changed:
        names = ", ".join(changed)
        msg = (
            f"Warning: {names} since last --trust-config. "
            "Review the change, then run: python run_celestia.py --trust-config"
        )
        _append_jsonl(
            _security_events_path(),
            {"ts": _now_iso(), "event": "config_integrity_mismatch", "files": changed},
        )
        return msg
    return None


def bootstrap_security() -> None:
    load_config()
    warn = check_config_integrity()
    if warn:
        print(f"[security] {warn}")
    if _use_shared_state():
        print(f"[security] PC control: {armed_status_label()} (shared across -i / tray / CLI)")
