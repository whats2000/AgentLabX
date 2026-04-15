from __future__ import annotations

import pytest

from agentlabx.security.fernet_store import FernetStore, InvalidCiphertextError


def test_encrypt_then_decrypt_roundtrip(
    ephemeral_keyring: dict[tuple[str, str], str],
) -> None:
    store = FernetStore.from_keyring()
    ciphertext = store.encrypt(b"sk-anthropic-secret-key")
    assert store.decrypt(ciphertext) == b"sk-anthropic-secret-key"


def test_ciphertext_is_not_plaintext(
    ephemeral_keyring: dict[tuple[str, str], str],
) -> None:
    store = FernetStore.from_keyring()
    ciphertext = store.encrypt(b"sk-anthropic-secret-key")
    assert b"sk-anthropic-secret-key" not in ciphertext


def test_decrypt_raises_on_tampered_ciphertext(
    ephemeral_keyring: dict[tuple[str, str], str],
) -> None:
    store = FernetStore.from_keyring()
    ciphertext = bytearray(store.encrypt(b"payload"))
    ciphertext[-1] ^= 0xFF  # flip a bit
    with pytest.raises(InvalidCiphertextError):
        store.decrypt(bytes(ciphertext))


def test_decrypt_raises_on_wrong_key(
    ephemeral_keyring: dict[tuple[str, str], str],
) -> None:
    from cryptography.fernet import Fernet

    store_a = FernetStore.from_keyring()
    ciphertext = store_a.encrypt(b"payload")
    bogus_key = Fernet.generate_key()
    store_b = FernetStore(key=bogus_key)
    with pytest.raises(InvalidCiphertextError):
        store_b.decrypt(ciphertext)
