"""URL allowlist matching and open-target resolution (github → https://github.com)."""

from __future__ import annotations

import re
from urllib.parse import urlparse

# Default TLD when allowlist entry is a bare label (e.g. `github`)
DEFAULT_TLD = "com"

_SITE_ALIASES: dict[str, str] = {
    "github": "https://github.com",
    "google": "https://google.com",
    "youtube": "https://youtube.com",
    "reddit": "https://reddit.com",
    "discord": "https://discord.com",
}

_DOMAIN = re.compile(
    r"\b((?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+(?:com|org|net|io|dev|co)(?:/[^\s]*)?)\b",
    re.I,
)


def url_host(url: str) -> str:
    u = url.strip()
    if not u.lower().startswith(("http://", "https://")):
        u = "https://" + u
    try:
        return (urlparse(u).hostname or "").lower()
    except Exception:
        return ""


def entry_hosts(entry: str) -> list[str]:
    """Hosts implied by one allowlist entry."""
    e = str(entry).strip().lower()
    if not e:
        return []
    if e.startswith("http://") or e.startswith("https://"):
        h = url_host(e)
        return [h] if h else []
    e = e.split("/")[0]
    if "." in e:
        return [e]
    return [f"{e}.{DEFAULT_TLD}"]


def host_matches_entry(host: str, entry: str) -> bool:
    """True if `host` is allowed by this allowlist entry (label or full host)."""
    host = host.lower().strip()
    if not host:
        return False
    for allowed in entry_hosts(entry):
        if host == allowed or host.endswith("." + allowed):
            return True
    return False


def host_matches_allowlist(host: str, allowlist: list[str]) -> bool:
    return any(host_matches_entry(host, str(e)) for e in allowlist if e)


def candidates_for_label(label: str, allowlist: list[str]) -> list[str]:
    """HTTPS URLs on the allowlist that match a bare label (e.g. github)."""
    label = label.lower().strip()
    if not label:
        return []
    urls: list[str] = []
    seen: set[str] = set()
    for entry in allowlist:
        for h in entry_hosts(str(entry)):
            if h.split(".")[0] == label:
                u = f"https://{h}"
                if u not in seen:
                    seen.add(u)
                    urls.append(u)
    return sorted(urls)


def resolve_label(label: str) -> tuple[str | None, str | None]:
    """
    Resolve a bare name or domain to a URL.
    Returns (url, user_message). message is set for ambiguity or scoped block hints.
    """
    from celestia_core.config import get
    from celestia_core.security import get_mode

    label = label.lower().strip()
    if not label:
        return None, None

    if re.fullmatch(r"[\w.-]+\.\w{2,}", label):
        return f"https://{label.split('/')[0]}", None

    allowlist = [str(x) for x in (get("security.url_allowlist") or []) if x]
    mode = get_mode()

    if mode == "scoped" and allowlist:
        cands = candidates_for_label(label, allowlist)
        if len(cands) > 1:
            opts = ", ".join(cands)
            return None, (
                f"Several allowed sites match '{label}': {opts}. "
                f"Pick one, e.g. open {cands[0]}"
            )
        if len(cands) == 1:
            return cands[0], None
        if label in _SITE_ALIASES:
            return None, (
                f"Blocked: '{label}' is not on url_allowlist. "
                "Add it to security.policy.yaml (e.g. github or github.com)."
            )

    if label in _SITE_ALIASES:
        return _SITE_ALIASES[label], None

    cands = candidates_for_label(label, allowlist)
    if len(cands) == 1:
        return cands[0], None
    if len(cands) > 1:
        opts = ", ".join(cands)
        return None, f"Several sites match '{label}': {opts}. Say which, e.g. open {cands[0]}"

    return None, None


def resolve_open_target(target: str, *, open_command: bool = False) -> tuple[str | None, str | None]:
    """
    Resolve text to a URL for open_url.
    open_command=True: `open github` / `open github.com` (no extra phrasing required).
  """
    t = target.strip()
    if not t:
        return None, None

    m_url = re.search(r"https?://[^\s'\"<>]+", t, re.I)
    if m_url:
        return m_url.group(0).rstrip(".,;)'\"]"), None

    m = _DOMAIN.search(t)
    if m:
        return f"https://{m.group(1).lower().rstrip('/')}", None

    if open_command:
        token = t.split()[0].lower()
        if len(t.split()) == 1:
            return resolve_label(token)

    low = t.lower()
    for alias in _SITE_ALIASES:
        if re.search(rf"\b{re.escape(alias)}\b", low):
            return resolve_label(alias)

    if open_command:
        return None, None

    return None, None
