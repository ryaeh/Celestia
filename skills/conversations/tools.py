"""LLM tool: search the user's past chat sessions (Feature 03 / #86).

Read-only keyword recall over stored sessions. The heavy lifting lives in
``celestia_core.shell_chat.search_sessions``; this module only defines the tool
schema and formats the result for the model. shell_chat is imported lazily inside
the handler to avoid the registry → shell_chat → agent → registry import cycle.
"""

from __future__ import annotations

CONVERSATION_TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "search_conversations",
            "description": (
                "Search the user's past chat sessions by keyword to recall earlier "
                "discussions. Use when the user refers to something you talked about "
                "before ('what did we decide about…', 'last week you mentioned…'). "
                "Returns matching past conversations with a snippet from each."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Keywords or phrase to look for in past chats.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max conversations to return (default 5).",
                    },
                },
                "required": ["query"],
            },
        },
    }
]


def search_conversations(query: str, limit: int = 5) -> str:
    from celestia_core.shell_chat import search_sessions

    q = (query or "").strip()
    if not q:
        return "Provide a search query."

    rows = search_sessions(q, limit=max(1, min(int(limit or 5), 10)))
    if not rows:
        return f'No past conversations mention "{q}".'

    lines = [f'Past conversations mentioning "{q}":']
    for r in rows:
        title = r.get("title") or "Untitled"
        when = r.get("when") or ""
        snippet = (r.get("snippet") or "").replace("\n", " ").strip()
        lines.append(f"- [{when}] {title}: {snippet}")
    return "\n".join(lines)
