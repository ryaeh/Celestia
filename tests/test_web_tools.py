"""Tests for skills.web.tools — web_search and fetch_page.

All external calls are mocked so these run fully offline.
"""
from __future__ import annotations

import json
import pytest


# ---------------------------------------------------------------------------
# _is_safe_url
# ---------------------------------------------------------------------------

def test_safe_url_blocks_localhost():
    from skills.web.tools import _is_safe_url
    assert not _is_safe_url("http://localhost/")
    assert not _is_safe_url("http://127.0.0.1/")
    assert not _is_safe_url("http://0.0.0.0/")


def test_safe_url_blocks_private_ranges():
    from skills.web.tools import _is_safe_url
    assert not _is_safe_url("http://192.168.1.1/")
    assert not _is_safe_url("http://10.0.0.1/")
    assert not _is_safe_url("http://172.16.0.1/")


def test_safe_url_allows_public():
    from skills.web.tools import _is_safe_url
    assert _is_safe_url("https://deepwoken.wiki.gg/wiki/Weapons")
    assert _is_safe_url("https://www.google.com/")


def test_safe_url_requires_http_scheme():
    from skills.web.tools import _is_safe_url
    assert not _is_safe_url("ftp://example.com/")
    assert not _is_safe_url("file:///etc/passwd")


# ---------------------------------------------------------------------------
# web_search
# ---------------------------------------------------------------------------

def test_web_search_returns_results(monkeypatch):
    """web_search should call DDGS.text and return JSON results."""
    fake_results = [
        {"title": "Deepwoken Wiki", "href": "https://deepwoken.wiki.gg", "body": "Curved Blade of Winds stats"},
    ]

    class FakeDDGS:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def text(self, *a, **kw): return fake_results

    import duckduckgo_search as ddg_mod
    monkeypatch.setattr(ddg_mod, "DDGS", FakeDDGS)

    from skills.web.tools import web_search
    result = web_search("curved blade of winds deepwoken")
    parsed = json.loads(result)
    # The response is wrapped: {"results": [...]} or a flat list depending on implementation
    items = parsed.get("results", parsed) if isinstance(parsed, dict) else parsed
    assert isinstance(items, list)
    assert items[0]["title"] == "Deepwoken Wiki"


def test_web_search_empty_query():
    from skills.web.tools import web_search
    result = web_search("")
    assert "error" in result.lower() or result.startswith("[") or result.startswith("{")


# ---------------------------------------------------------------------------
# fetch_page
# ---------------------------------------------------------------------------

def test_fetch_page_blocks_local():
    from skills.web.tools import fetch_page
    result = fetch_page("http://localhost:8765/secret")
    assert "blocked" in result.lower() or "error" in result.lower()


def test_fetch_page_blocks_ftp():
    from skills.web.tools import fetch_page
    result = fetch_page("ftp://example.com/file.txt")
    assert "blocked" in result.lower() or "error" in result.lower()


def test_fetch_page_returns_text(monkeypatch):
    """fetch_page should strip HTML and return plain text."""
    import skills.web.tools as wt

    class FakeResp:
        status_code = 200
        headers = {"content-type": "text/html; charset=utf-8"}
        text = "<html><body><h1>Curved Blade of Winds</h1><p>Requires 75 Agility.</p></body></html>"
        def raise_for_status(self): pass

    class FakeClient:
        def __init__(self, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def get(self, url, **kw): return FakeResp()

    # Patch httpx.Client in the web tools module + bypass SSRF check
    monkeypatch.setattr(wt.httpx, "Client", FakeClient)
    monkeypatch.setattr(wt, "_is_safe_url", lambda url: True)

    result = wt.fetch_page("https://deepwoken.wiki.gg/wiki/Weapons")
    assert "Curved Blade" in result or "Agility" in result
