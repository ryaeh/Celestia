from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent  # project root (celestia/)
POLICY_FILE = "security.policy.yaml"
_config: dict[str, Any] | None = None


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
    cfg = load_config()
    node: Any = cfg
    for part in path.split("."):
        if not isinstance(node, dict):
            return default
        node = node.get(part)
        if node is None:
            return default
    return node
