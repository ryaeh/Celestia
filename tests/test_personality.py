"""Tests for celestia_core/personality.py.

Validates:
- build_system_prompt() returns a non-empty string.
- The cache hit path works (second call returns same object).
- invalidate_prompt_cache() forces a rebuild.
- The base prompt contains the app display name.
"""

import pytest

from celestia_core import personality
from celestia_core.personality import build_system_prompt, invalidate_prompt_cache


@pytest.fixture(autouse=True)
def clear_cache():
    """Start every test with a warm cache and clean up after."""
    invalidate_prompt_cache()
    yield
    invalidate_prompt_cache()


def test_returns_nonempty_string():
    prompt = build_system_prompt()
    assert isinstance(prompt, str)
    assert len(prompt) > 50


def test_contains_app_name(monkeypatch):
    """The base template injects the display name."""
    monkeypatch.setattr("celestia_core.personality.get", lambda key, default=None: {
        "personality.active": "default",
        "app.display_name": "TestBot",
    }.get(key, default))
    invalidate_prompt_cache()
    prompt = build_system_prompt()
    assert "TestBot" in prompt


def test_cache_returns_same_object():
    """Repeated calls must return the identical cached string (no rebuild)."""
    first = build_system_prompt()
    second = build_system_prompt()
    assert first is second  # same object proves cache hit, not just equal content


def test_invalidate_clears_cache():
    """After invalidation the cache entry is gone."""
    _ = build_system_prompt()
    active = personality.get("personality.active", "default") or "default"
    assert active in personality._PROMPT_CACHE

    invalidate_prompt_cache()
    assert personality._PROMPT_CACHE == {}


def test_rebuild_after_invalidation():
    """Rebuilding after invalidation should return an equivalent prompt."""
    first = build_system_prompt()
    invalidate_prompt_cache()
    second = build_system_prompt()
    assert first == second
    assert second is not first  # different object — genuinely rebuilt
