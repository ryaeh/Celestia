"""Optional n8n webhook notifications (automation.integrations)."""

from __future__ import annotations

import json
from typing import Any

import requests

from celestia_core.config import get


def _webhook_url() -> str | None:
    if not get("automation.n8n_enabled", False):
        return None
    url = (get("automation.n8n_url") or "").strip().rstrip("/")
    if not url:
        return None
    path = (get("automation.n8n_webhook_path") or "/webhook/celestia").strip()
    if not path.startswith("/"):
        path = "/" + path
    return url + path


def notify(event: str, **payload: Any) -> None:
    """Fire-and-forget POST to n8n; never raises to caller."""
    url = _webhook_url()
    if not url:
        return
    body = {"event": event, **payload}
    try:
        requests.post(url, json=body, timeout=5)
    except requests.RequestException:
        pass


def notify_security_mode(mode: str, *, source: str = "cli") -> None:
    notify("security_mode", mode=mode, source=source)
