"""Morning briefing skill (CC-59).

Provides the ``morning_briefing`` tool which returns a structured daily
summary: current date/time, pending tasks from memory, and optionally
live weather via web_search.
"""
from __future__ import annotations

import json
from typing import Any

BRIEFING_TOOL_SCHEMA: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "morning_briefing",
            "description": (
                "Fetch the user's morning briefing: today's date and time, "
                "pending tasks from long-term memory, and optionally current weather. "
                "Call this whenever the user says 'good morning', 'morning briefing', "
                "'daily summary', or asks what they have to do today."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": (
                            "City name for weather lookup. Leave empty to skip weather "
                            "or to use the default city from config."
                        ),
                    },
                },
            },
        },
    }
]


def morning_briefing(city: str = "") -> str:
    """Return a structured morning briefing string."""
    from datetime import datetime
    from celestia_core.config import get
    from skills.memory import store as memory

    now = datetime.now()
    date_line = now.strftime("%A, %B %d %Y — %H:%M")

    uid = get("app.user_id", "atlas_user")
    tasks = memory.get_entries_by_kind(uid, "task", limit=15)
    if tasks:
        task_lines = "\n".join(f"• {t['text']}" for t in tasks)
    else:
        task_lines = "No pending tasks."

    weather_section = ""
    target_city = city.strip() or get("ui.briefing_city", "")
    if target_city and get("skills.web.enabled", True):
        try:
            from skills.web.tools import web_search
            raw = web_search(f"current weather in {target_city} today")
            results = json.loads(raw)
            items = results.get("results", results) if isinstance(results, dict) else results
            if items and isinstance(items, list):
                snippet = items[0].get("snippet", items[0].get("body", ""))[:200]
                if snippet:
                    weather_section = f"\n\n**Weather ({target_city}):** {snippet}"
        except Exception:
            pass

    return (
        f"**{date_line}**{weather_section}\n\n"
        f"**Pending tasks:**\n{task_lines}"
    )
