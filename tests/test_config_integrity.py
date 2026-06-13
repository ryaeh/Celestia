"""Config/policy integrity: --trust-config baselines config.yaml AND the policy file,
and check_config_integrity detects modify / add / remove.

The policy file is watched even when absent, so creating one after trust (the
"malware adds itself to the app allowlist" threat) is flagged, not just edits.
"""

from __future__ import annotations

import pytest

import celestia_core.config as cfg
import celestia_core.security as sec


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    monkeypatch.setattr(sec, "ROOT", tmp_path)
    monkeypatch.setattr(cfg, "policy_path", lambda: tmp_path / "security.policy.yaml")
    monkeypatch.setattr(
        sec,
        "get",
        lambda key, default=None: {
            "security.integrity_store": "data/config.trust",
            "security.integrity_check": True,
        }.get(key, default),
    )
    (tmp_path / "config.yaml").write_text("model: x\n", encoding="utf-8")
    return tmp_path


def _policy(sandbox, text="app_allowlist: [code]\n"):
    (sandbox / "security.policy.yaml").write_text(text, encoding="utf-8")


def test_clean_after_trust_passes(sandbox):
    _policy(sandbox)
    sec.trust_config()
    assert sec.check_config_integrity() is None


def test_modified_policy_flagged(sandbox):
    _policy(sandbox)
    sec.trust_config()
    _policy(sandbox, "app_allowlist: [code, evil.exe]\n")  # tamper
    warn = sec.check_config_integrity()
    assert warn and "security.policy.yaml (modified)" in warn


def test_added_policy_flagged(sandbox):
    # No policy file at trust time → recorded as absent.
    sec.trust_config()
    assert sec.check_config_integrity() is None
    _policy(sandbox)  # malware creates one
    warn = sec.check_config_integrity()
    assert warn and "security.policy.yaml (added)" in warn


def test_removed_policy_flagged(sandbox):
    _policy(sandbox)
    sec.trust_config()
    (sandbox / "security.policy.yaml").unlink()
    warn = sec.check_config_integrity()
    assert warn and "security.policy.yaml (removed)" in warn


def test_modified_config_flagged(sandbox):
    _policy(sandbox)
    sec.trust_config()
    (sandbox / "config.yaml").write_text("model: tampered\n", encoding="utf-8")
    warn = sec.check_config_integrity()
    assert warn and "config.yaml (modified)" in warn


def test_trust_message_watches_absent_policy(sandbox):
    msg = sec.trust_config()
    assert "config.yaml" in msg
    assert "watching for creation" in msg
    assert "security.policy.yaml" in msg


def test_trust_store_records_null_for_absent(sandbox):
    import json

    sec.trust_config()
    data = json.loads((sandbox / "data" / "config.trust").read_text(encoding="utf-8"))
    assert data["files"]["security.policy.yaml"] is None
    assert data["files"]["config.yaml"] is not None


def test_check_disabled_returns_none(sandbox, monkeypatch):
    _policy(sandbox)
    sec.trust_config()
    _policy(sandbox, "tampered: true\n")
    monkeypatch.setattr(
        sec, "get",
        lambda key, default=None: False if key == "security.integrity_check" else (
            "data/config.trust" if key == "security.integrity_store" else default
        ),
    )
    assert sec.check_config_integrity() is None


def test_no_store_returns_none(sandbox):
    # Never trusted → nothing to compare against.
    assert sec.check_config_integrity() is None
