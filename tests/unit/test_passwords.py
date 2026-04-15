from __future__ import annotations

from agentlabx.security.passwords import hash_passphrase, verify_passphrase


def test_hash_verify_roundtrip() -> None:
    digest = hash_passphrase("correct horse battery staple")
    assert verify_passphrase(digest, "correct horse battery staple") is True


def test_verify_rejects_wrong_passphrase() -> None:
    digest = hash_passphrase("hunter2")
    assert verify_passphrase(digest, "hunter3") is False


def test_hash_is_not_plaintext() -> None:
    digest = hash_passphrase("my-secret")
    assert "my-secret" not in digest
    assert digest.startswith("$argon2")


def test_hash_is_unique_per_call_due_to_salt() -> None:
    assert hash_passphrase("same") != hash_passphrase("same")
