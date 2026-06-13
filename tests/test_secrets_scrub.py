"""Secrets are scrubbed before anything is written to memory/graph.

Covers the pure ``scrub_secrets`` pattern set, the config-gated wrapper, and the
``store.add`` backstop that strips secrets on the vector-store write path.
"""

from __future__ import annotations

import pytest

import skills.memory.scrub as scrub
import skills.memory.store as store


# --- pattern coverage -------------------------------------------------------

def test_openai_key_redacted():
    text = "my key is sk-abcdefghijklmnopqrstuvwxyz0123 ok"
    out, found = scrub.scrub_secrets(text)
    assert "sk-abcdefghijklmnopqrstuvwxyz0123" not in out
    assert "[REDACTED:api_key]" in out
    assert found == ["api_key"]


def test_anthropic_key_redacted():
    out, found = scrub.scrub_secrets("token=sk-ant-api03-AbCdEf012345678901234567890123")
    assert "sk-ant" not in out
    assert found == ["api_key"]


def test_github_pat_redacted():
    out, found = scrub.scrub_secrets("export GH=ghp_0123456789abcdefghijklmnopqrstuvwxyz")
    assert "ghp_" not in out
    assert "api_key" in found


def test_aws_and_google_keys_redacted():
    out, found = scrub.scrub_secrets("AKIAIOSFODNN7EXAMPLE and AIza" + "B" * 35)
    assert "AKIAIOSFODNN7EXAMPLE" not in out
    assert found.count("api_key") == 2


def test_jwt_redacted():
    jwt = "eyJhbGciOiJIUzI1NiI.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N"
    out, found = scrub.scrub_secrets(f"Authorization: Bearer {jwt}")
    assert jwt not in out
    assert "jwt" in found


def test_private_key_block_redacted():
    pem = (
        "-----BEGIN RSA PRIVATE KEY-----\n"
        "MIIEowIBAAKCAQEA1234567890\nabcDEF==\n"
        "-----END RSA PRIVATE KEY-----"
    )
    out, found = scrub.scrub_secrets(f"here:\n{pem}\nthanks")
    assert "PRIVATE KEY" not in out
    assert found == ["private_key"]
    assert out.startswith("here:")


def test_password_assignment_redacts_value_keeps_name():
    out, found = scrub.scrub_secrets('password = "hunter2pass"')
    assert "hunter2pass" not in out
    assert "password" in out          # the field name survives
    assert found == ["credential"]


@pytest.mark.parametrize("phrase", ["api_key: sk_live_value_here", "client_secret=topsecretvalue"])
def test_various_credential_assignments(phrase):
    out, found = scrub.scrub_secrets(phrase)
    assert found  # something was redacted
    assert "[REDACTED:credential]" in out or "[REDACTED:api_key]" in out


def test_credit_card_luhn_valid_redacted():
    out, found = scrub.scrub_secrets("card 4111 1111 1111 1111 expires soon")
    assert "4111" not in out
    assert found == ["card"]


def test_non_luhn_long_number_kept():
    # A 16-digit order id that fails Luhn must NOT be redacted (false-positive guard).
    out, found = scrub.scrub_secrets("order 1234567812345678 shipped")  # fails Luhn
    assert "1234567812345678" in out
    assert "card" not in found


# --- false-positive guard ---------------------------------------------------

def test_normal_prose_untouched():
    # No explicit =/: assignment, so credential keywords in prose are left intact.
    text = "I forgot my password again and the project deadline is Friday."
    out, found = scrub.scrub_secrets(text)
    assert out == text
    assert found == []


def test_empty_and_clean_text():
    assert scrub.scrub_secrets("") == ("", [])
    assert scrub.scrub_secrets("just a normal sentence") == ("just a normal sentence", [])


# --- config gate ------------------------------------------------------------

def test_scrub_for_storage_respects_flag(monkeypatch):
    secret = "sk-abcdefghijklmnopqrstuvwxyz0123"
    monkeypatch.setattr(scrub, "get", lambda key, default=None: False)
    assert scrub.scrub_for_storage(secret) == secret  # disabled → passthrough
    monkeypatch.setattr(scrub, "get", lambda key, default=None: True)
    assert "[REDACTED:api_key]" in scrub.scrub_for_storage(secret)


# --- store.add backstop -----------------------------------------------------

class _FakeMem:
    def __init__(self):
        self.added: list[str] = []

    def add(self, content, **kwargs):
        self.added.append(content)
        return {"results": []}


def test_store_add_scrubs_before_persist(monkeypatch):
    fake = _FakeMem()
    monkeypatch.setattr(store, "_get_memory", lambda: fake)
    monkeypatch.setattr(scrub, "get", lambda key, default=None: True)  # scrub on
    store.add("remember my key sk-abcdefghijklmnopqrstuvwxyz0123", "u1", kind="fact")
    assert fake.added, "nothing was persisted"
    assert "sk-abcdefghijklmnopqrstuvwxyz0123" not in fake.added[0]
    assert "[REDACTED:api_key]" in fake.added[0]
