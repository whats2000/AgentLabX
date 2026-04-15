from __future__ import annotations

from dataclasses import dataclass
from typing import Self

from cryptography.fernet import Fernet, InvalidToken

from agentlabx.security.keyring_store import get_or_create_master_key


class InvalidCiphertextError(Exception):
    """Raised when decryption fails — bad key or tampered ciphertext."""


@dataclass(frozen=True)
class FernetStore:
    """Thin Fernet wrapper; constructs from an explicit key or the OS keyring."""

    key: bytes

    @classmethod
    def from_keyring(cls) -> Self:
        return cls(key=get_or_create_master_key())

    def encrypt(self, plaintext: bytes) -> bytes:
        return Fernet(self.key).encrypt(plaintext)

    def decrypt(self, ciphertext: bytes) -> bytes:
        try:
            return Fernet(self.key).decrypt(ciphertext)
        except InvalidToken as exc:
            raise InvalidCiphertextError("decryption failed") from exc
