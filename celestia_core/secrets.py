"""Load .env and HuggingFace token before model downloads."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def bootstrap() -> None:
    """Call once at startup."""
    env_path = ROOT / ".env"
    if env_path.exists():
        try:
            from dotenv import load_dotenv

            load_dotenv(env_path, override=False)
        except ImportError:
            pass

    # Quieter HF cache on Windows
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    try:
        from celestia_core.config import get, load_config

        load_config()
        token = get("app.hf_token") or token
    except Exception:
        pass

    if token:
        os.environ["HF_TOKEN"] = token.strip()
        os.environ["HUGGING_FACE_HUB_TOKEN"] = token.strip()
