from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent  # project root (celestia/)
_config: dict[str, Any] | None = None


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
