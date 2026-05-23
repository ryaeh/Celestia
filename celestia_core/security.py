"""Armed/safe/scoped modes, tool audit log, config integrity."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from celestia_core.config import ROOT, get, load_config

Mode = Literal["safe", "scoped", "armed"]

PC_TOOLS_ALWAYS_OK = frozenset({"get_system_status", "list_processes"})
PC_TOOLS_SCOPED_BLOCK = frozenset({"run_powershell", "open_url"})
PC_TOOLS_SCOPE_CHECK = frozenset({"open_path", "file_read"})
PC_TOOLS_SAFE_BLOCK = frozenset({"run_powershell", "open_path", "open_url", "file_read"})

_session_mode: Mode | None = None


def _state_path() -> Path:
    return ROOT / "data" / "security_state.json"


def _use_shared_state() -> bool:
    if get("security.shared_armed_state", True):
        return True
    return bool(get("security.persist_armed_state", False))


def _read_state() -> dict[str, Any]:
    path = _state_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8")) or {}
    except (json.JSONDecodeError, OSError):
        return {}


def _write_state(data: dict[str, Any]) -> None:
    data["updated"] = _now_iso()
    _state_path().parent.mkdir(parents=True, exist_ok=True)
    _state_path().write_text(json.dumps(data, indent=2), encoding="utf-8")


def _default_mode() -> Mode:
    m = (get("security.mode", "safe") or "safe").lower()
    if m in ("safe", "scoped", "armed"):
        return m  # type: ignore
    return "safe"


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


def set_mode(mode: str) -> None:
    global _session_mode
    m = mode.lower()
    if m not in ("safe", "scoped", "armed"):
        raise ValueError(f"Invalid mode: {mode}")
    mode = m  # type: ignore
    if _use_shared_state():
        _write_state({"mode": mode, "armed": mode == "armed"})
        _session_mode = None
    else:
        _session_mode = mode  # type: ignore


def is_armed() -> bool:
    return get_mode() == "armed"


def set_armed(value: bool, *, persist: bool | None = None) -> None:
    set_mode("armed" if value else "safe")


def toggle_armed() -> bool:
    if get_mode() == "armed":
        set_mode("safe")
        return False
    set_mode("armed")
    return True


def armed_status_label() -> str:
    m = get_mode()
    if m == "armed":
        return "ARMED"
    if m == "scoped":
        return "scoped (allowlist)"
    return "safe"


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
        if name in PC_TOOLS_SCOPED_BLOCK:
            return (
                "Blocked in scoped mode (needs armed): PowerShell and URLs. "
                "Type arm for full access, or use allowlisted open_path only."
            )
        if name in PC_TOOLS_SCOPE_CHECK:
            from celestia_core.scope import check_file_read, check_open_path

            path = str(args.get("path", ""))
            if name == "file_read":
                return check_file_read(path)
            return check_open_path(path)
        return None

    if mode == "armed" and name == "file_read":
        from celestia_core.scope import check_file_read

        return check_file_read(str(args.get("path", "")))

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
    if name == "memory_add":
        return str(arguments.get("content", ""))[:80]
    if name == "memory_search":
        return str(arguments.get("query", ""))[:80]
    return json.dumps(arguments, ensure_ascii=False)[:120]


def trust_config() -> str:
    path = _config_path()
    digest = _hash_file(path)
    store = _trust_path()
    store.parent.mkdir(parents=True, exist_ok=True)
    store.write_text(
        json.dumps({"path": str(path), "sha256": digest, "trusted_at": _now_iso()}, indent=2),
        encoding="utf-8",
    )
    return f"Trusted config: {path.name} ({digest[:16]}…)"


def check_config_integrity() -> str | None:
    if not get("security.integrity_check", True):
        return None
    store = _trust_path()
    if not store.exists():
        return None
    try:
        data = json.loads(store.read_text(encoding="utf-8"))
        expected = data.get("sha256", "")
    except (json.JSONDecodeError, OSError):
        return "Config integrity store is corrupt — run --trust-config"
    path = _config_path()
    if not path.exists():
        return "config.yaml missing"
    current = _hash_file(path)
    if current != expected:
        msg = (
            f"Warning: {path.name} changed since last --trust-config. "
            "Review edits, then run: python run_celestia.py --trust-config"
        )
        _append_jsonl(
            _security_events_path(),
            {"ts": _now_iso(), "event": "config_integrity_mismatch", "file": path.name},
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
