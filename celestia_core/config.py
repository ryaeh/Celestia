from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent  # project root (celestia/)
POLICY_FILE = "security.policy.yaml"
_config: dict[str, Any] | None = None

# ---------------------------------------------------------------------------
# UI runtime preferences — a flat JSON overlay on top of config.yaml.
# Written by the Settings UI; survives restarts; does NOT touch config.yaml.
# ---------------------------------------------------------------------------
_UI_PREFS_PATH = ROOT / "data" / "ui_prefs.json"

MUTABLE_PREF_KEYS: frozenset[str] = frozenset(
    {
        "voice.stt.model",
        "voice.stt.device",
        "voice.stt.compute_type",
        "voice.stt.noise_gate_threshold",
        "voice.stt.vad_filter",
        "voice.stt.silence_stop_seconds",
        "voice.tts.provider",
        "voice.reply_cap_voice",
        "ui.shell_ptt_max_seconds",
    }
)


def _load_ui_prefs() -> dict[str, Any]:
    if not _UI_PREFS_PATH.exists():
        return {}
    try:
        return json.loads(_UI_PREFS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def get_all_prefs() -> dict[str, Any]:
    return _load_ui_prefs()


def set_pref(key: str, value: Any) -> str:
    """Write a single mutable pref to data/ui_prefs.json."""
    if key not in MUTABLE_PREF_KEYS:
        return f"not allowed: {key}"
    prefs = _load_ui_prefs()
    prefs[key] = value
    _UI_PREFS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _UI_PREFS_PATH.write_text(json.dumps(prefs, indent=2), encoding="utf-8")
    # Force-unload the Whisper model so it reloads with the new settings.
    if key in ("voice.stt.model", "voice.stt.device", "voice.stt.compute_type"):
        try:
            from skills.stt.engine import force_unload
            force_unload()
        except Exception:
            pass
    return "ok"


def policy_path() -> Path:
    return ROOT / POLICY_FILE


def _merge_security_policy(cfg: dict[str, Any]) -> dict[str, Any]:
    """Merge security.policy.yaml into cfg['security'] (policy wins over config.yaml lists)."""
    path = policy_path()
    if not path.exists():
        return cfg
    with open(path, encoding="utf-8") as f:
        policy = yaml.safe_load(f) or {}
    if not isinstance(policy, dict):
        return cfg
    nested = policy.get("security")
    if isinstance(nested, dict):
        policy = {**policy, **nested}
    sec = cfg.setdefault("security", {})
    for key in ("workspaces", "app_allowlist", "url_allowlist", "allowed_executables"):
        if key in policy and policy[key] is not None:
            sec[key] = policy[key]
    return cfg


def load_config(reload: bool = False) -> dict[str, Any]:
    global _config
    if _config is not None and not reload:
        return _config

    for name in ("config.yaml", "config.example.yaml"):
        path = ROOT / name
        if path.exists():
            with open(path, encoding="utf-8") as f:
                _config = yaml.safe_load(f) or {}
            _config["_root"] = str(ROOT)
            _config = _merge_security_policy(_config)
            return _config

    raise FileNotFoundError(f"No config.yaml in {ROOT}")


def get(path: str, default: Any = None) -> Any:
    # UI prefs override config.yaml for mutable keys.
    if path in MUTABLE_PREF_KEYS:
        prefs = _load_ui_prefs()
        if path in prefs:
            return prefs[path]
    cfg = load_config()
    node: Any = cfg
    for part in path.split("."):
        if not isinstance(node, dict):
            return default
        node = node.get(part)
        if node is None:
            return default
    return node
