"""Web skills: web_search and fetch_page (CC-113).

web_search  — searches DuckDuckGo (free, no API key)
fetch_page  — fetches a URL and returns readable plain text, capped at max_chars
"""

from __future__ import annotations

import json
from typing import Any

# ── Tool schemas ──────────────────────────────────────────────────────────────

WEB_TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": (
                "Search the web using DuckDuckGo. Use this for live information: "
                "game wikis, patch notes, news, documentation, stats, guides, prices. "
                "Returns a list of results with title, URL, and snippet."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query.",
                    },
                    "num_results": {
                        "type": "integer",
                        "description": "Number of results to return (default 5, max 10).",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_page",
            "description": (
                "Fetch and read the text content of a web page. "
                "Use this after web_search to read the full content of a specific URL — "
                "e.g. a wiki page, guide, or documentation page. "
                "Returns stripped readable text capped at max_chars."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The full URL to fetch.",
                    },
                    "max_chars": {
                        "type": "integer",
                        "description": "Maximum characters to return (default 3000).",
                    },
                },
                "required": ["url"],
            },
        },
    },
]


# ── Tool implementations ───────────────────────────────────────────────────────

_BLOCKED_HOSTS = frozenset(
    {
        "localhost",
        "127.0.0.1",
        "0.0.0.0",
        "::1",
        "169.254.169.254",  # AWS metadata
        "metadata.google.internal",
    }
)


def _is_safe_url(url: str) -> bool:
    """Reject private/loopback addresses to prevent SSRF."""
    from urllib.parse import urlparse

    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return False
    if host in _BLOCKED_HOSTS:
        return False
    if host.endswith(".local") or host.endswith(".internal"):
        return False
    # Block raw IPs that look like private ranges
    import re

    if re.match(r"^(10|172\.(1[6-9]|2\d|3[01])|192\.168)\.", host):
        return False
    return True


def web_search(query: str, num_results: int = 5) -> str:
    """Search DuckDuckGo and return JSON list of {title, url, snippet}."""
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        return json.dumps({"error": "duckduckgo-search not installed. Run: pip install duckduckgo-search"})

    num_results = min(max(1, int(num_results)), 10)
    try:
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=num_results):
                results.append(
                    {
                        "title": r.get("title", ""),
                        "url": r.get("href", ""),
                        "snippet": r.get("body", ""),
                    }
                )
        if not results:
            return json.dumps({"results": [], "note": "No results found."})
        return json.dumps({"results": results}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"Search failed: {e}"})


def fetch_page(url: str, max_chars: int = 3000) -> str:
    """Fetch a URL and return readable plain text, capped at max_chars."""
    if not _is_safe_url(url):
        return json.dumps({"error": f"URL blocked for security reasons: {url}"})

    max_chars = min(max(500, int(max_chars)), 8000)

    try:
        import httpx
    except ImportError:
        return json.dumps({"error": "httpx not installed. Run: pip install httpx"})

    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml",
        }
        with httpx.Client(follow_redirects=True, timeout=15) as client:
            resp = client.get(url, headers=headers)
        resp.raise_for_status()
        content_type = resp.headers.get("content-type", "")
        if "text/html" not in content_type and "text/plain" not in content_type:
            return json.dumps({"error": f"Unsupported content type: {content_type}"})
        raw_html = resp.text
    except Exception as e:
        return json.dumps({"error": f"Fetch failed: {e}"})

    # Convert HTML to readable plain text
    try:
        import html2text

        h = html2text.HTML2Text()
        h.ignore_links = False
        h.ignore_images = True
        h.ignore_tables = False
        h.body_width = 0  # no line wrapping
        text = h.handle(raw_html)
    except ImportError:
        # Fallback: strip tags with regex
        import re

        text = re.sub(r"<[^>]+>", " ", raw_html)
        text = re.sub(r"\s+", " ", text).strip()

    text = text[:max_chars]
    if len(text) == max_chars:
        text += "\n…(truncated)"

    return json.dumps({"url": url, "text": text}, ensure_ascii=False)
