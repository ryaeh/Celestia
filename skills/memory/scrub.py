"""Secrets scrubbing — strip credentials before anything is written to memory/graph.

The "privacy-guardian lite" cheap-80% of Feature 08 (the full anomaly monitor is
descoped/late). A regex pass over text headed for long-term storage replaces
high-confidence, high-cost secrets — private keys, JWTs, prefixed API keys/tokens,
``password = ...`` style assignments, and Luhn-valid card numbers — with a stable
``[REDACTED:<kind>]`` placeholder.

Two layers use it:
- ``store.add`` scrubs every vector-store write (the universal backstop — covers
  direct saves, pin-to-memory, the ``memory_save`` tool).
- the consolidation / graph-extraction *excerpt* is scrubbed before it reaches the
  LLM prompt, so secrets never enter the model context or the knowledge graph.

Design bias: **few false positives over total recall.** We only redact patterns we
can identify with high confidence (known key prefixes, Luhn-checked cards), so normal
prose is left untouched. Catching everything is Feature 08's job, not this.
"""

from __future__ import annotations

import re

from celestia_core.config import get

_PLACEHOLDER = "[REDACTED:{kind}]"

# PEM private-key blocks (RSA/EC/OPENSSH/PGP …).
_PEM = re.compile(
    r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?-----END [A-Z0-9 ]*PRIVATE KEY-----",
    re.S,
)

# JSON Web Tokens: header.payload.signature, header/payload base64url-encoded JSON
# (both start with "eyJ"). Signature segment may be empty (alg=none) → allow 0+.
_JWT = re.compile(
    r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]*\b"
)

# Vendor API keys / tokens identified by their published prefix.
_KEY_PREFIXED = re.compile(
    r"(?:"
    r"sk-ant-[A-Za-z0-9_-]{20,}"          # Anthropic
    r"|sk-[A-Za-z0-9]{20,}"               # OpenAI & sk-style
    r"|gh[posru]_[A-Za-z0-9]{20,}"        # GitHub PAT/OAuth/refresh/server/user
    r"|github_pat_[A-Za-z0-9_]{20,}"      # GitHub fine-grained PAT
    r"|xox[baprs]-[A-Za-z0-9-]{10,}"      # Slack
    r"|AKIA[0-9A-Z]{16}"                  # AWS access key id
    r"|AIza[0-9A-Za-z_-]{35}"             # Google API key
    r")"
)

# name=value / name: value where the name signals a credential. Keeps the name,
# redacts only the value. Deliberately requires an explicit ``=``/``:`` (config,
# code, .env, JSON) — natural-language forms ("my password is …") are left alone
# to avoid mangling prose, per the false-positives-over-recall bias.
_ASSIGNMENT = re.compile(
    r"(?i)\b(password|passwd|pwd|secret|api[_-]?key|access[_-]?token|auth[_-]?token"
    r"|client[_-]?secret|bearer)\b"
    r"(\s*[:=]\s*)"
    r"(['\"]?)([^\s'\"]{4,})\3"
)

# Candidate card numbers: 13–19 digits, optionally grouped by spaces or dashes.
# Confirmed by Luhn before redacting (kills most false positives like long IDs).
_CARD = re.compile(r"\b(?:\d[ -]?){12,18}\d\b")


def _luhn_ok(digits: str) -> bool:
    total = 0
    # Double every second digit counting from the right: index i is doubled when
    # (len - i) is even, i.e. i has the same parity as len.
    parity = len(digits) % 2
    for i, ch in enumerate(digits):
        d = ord(ch) - 48
        if i % 2 == parity:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def scrub_secrets(text: str) -> tuple[str, list[str]]:
    """Redact secrets in *text*. Returns (scrubbed_text, kinds_found).

    Pure function — no config check. ``kinds_found`` lists one entry per redaction
    (e.g. ``["api_key", "card"]``), useful for audit/UI; callers that only want the
    text can ignore it.
    """
    if not text:
        return text, []

    found: list[str] = []

    def _redact(kind: str) -> str:
        found.append(kind)
        return _PLACEHOLDER.format(kind=kind)

    out = _PEM.sub(lambda m: _redact("private_key"), text)
    out = _JWT.sub(lambda m: _redact("jwt"), out)
    out = _KEY_PREFIXED.sub(lambda m: _redact("api_key"), out)

    def _assign_repl(m: re.Match) -> str:
        return f"{m.group(1)}{m.group(2)}{_redact('credential')}"

    out = _ASSIGNMENT.sub(_assign_repl, out)

    def _card_repl(m: re.Match) -> str:
        digits = re.sub(r"\D", "", m.group(0))
        if 13 <= len(digits) <= 19 and _luhn_ok(digits):
            return _redact("card")
        return m.group(0)

    out = _CARD.sub(_card_repl, out)

    return out, found


def scrub_for_storage(text: str) -> str:
    """Config-gated convenience: scrub if ``memory.scrub_secrets`` is on, else passthrough."""
    if not text or not get("memory.scrub_secrets", True):
        return text
    scrubbed, _found = scrub_secrets(text)
    return scrubbed
