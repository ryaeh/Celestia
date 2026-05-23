"""Direct 'open …' lines and URL detection for PC tools."""

from __future__ import annotations

import re

from celestia_core.url_policy import resolve_open_target

_OPEN_LINE = re.compile(r"^open\s+(.+)$", re.I)
_URL_IN_TEXT = re.compile(r"https?://[^\s'\"<>]+", re.I)


def extract_url(text: str) -> str | None:
    m = _URL_IN_TEXT.search(text)
    if not m:
        return None
    return m.group(0).rstrip(".,;)'\"]")


def _wants_open_in_browser(text: str) -> bool:
    low = text.lower()
    if re.search(r"\b(open|visit|browse|go to|launch)\b", low):
        return True
    if "browser" in low and re.search(r"\b(open|visit|go to)\b", low):
        return True
    return False


def resolve_browser_url(text: str) -> str | None:
    """Turn 'open github', 'github.com', or https://… into a full URL."""
    if not _wants_open_in_browser(text):
        return None
    url, _ = resolve_open_target(text, open_command=False)
    return url


def is_browser_open_request(text: str) -> bool:
    return resolve_browser_url(text) is not None and _wants_open_in_browser(text)


def is_primary_open_request(text: str) -> bool:
    """True when the message is mainly asking to open a URL or app (not mixed tasks)."""
    t = text.strip()
    if not t:
        return False

    if is_browser_open_request(t):
        rest = re.sub(
            r"https?://\S+|[\w.-]+\.(?:com|org|net|io|dev|co)\S*|\b(github|google|youtube)\b",
            "",
            t,
            flags=re.I,
        ).strip(" .,!?:;")
        if len(rest) <= 45:
            return True

    url = extract_url(t)
    if url:
        rest = t.replace(url, "").strip(" .,!?:;")
        if len(rest) <= 35:
            return True
        if re.match(
            r"^(please\s+)?((can|could)\s+you\s+)?(open|visit|go to|browse|launch)\b",
            rest,
            re.I,
        ):
            return True
        return False
    return bool(
        re.match(
            r"^(please\s+)?((can|could)\s+you\s+)?(open|launch|start)\s+[\w./\\-]+",
            t,
            re.I,
        )
    )


def handle_open_in_browser_request(text: str) -> str | None:
    """
    If the user asks to open a site in the browser: run open_url when allowed,
  or return an honest blocked message. Returns None if not a browser-open request.
    """
    if not is_browser_open_request(text):
        return None

    url, msg = resolve_open_target(text, open_command=False)
    if msg:
        return msg
    if not url:
        url = resolve_browser_url(text)
    if not url:
        return None

    from celestia_core import security
    from skills.pc_control.tools import execute_pc

    blocked = security.gate_pc_tool("open_url", {"url": url})
    if blocked:
        return security.preflight_reply_from_blocked(blocked)

    result = execute_pc("open_url", {"url": url})
    if result.startswith("Blocked:"):
        return security.preflight_reply_from_blocked(result)
    return f"I opened it in your browser. {result}"


def dispatch_open_line(line: str) -> str | None:
    """
    If line is ``open <target>``, run open_url or open_path.
    Returns result string, or None if not an open command.
    """
    m = _OPEN_LINE.match(line.strip())
    if not m:
        return None

    from celestia_core import security
    from skills.pc_control.tools import execute_pc

    target = m.group(1).strip()
    url, msg = resolve_open_target(target, open_command=True)
    if msg:
        return msg
    if not url:
        url = extract_url(target)
    if url:
        blocked = security.gate_pc_tool("open_url", {"url": url})
        return blocked or execute_pc("open_url", {"url": url})

    blocked = security.gate_pc_tool("open_path", {"path": target})
    return blocked or execute_pc("open_path", {"path": target})
