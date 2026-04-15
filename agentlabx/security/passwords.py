from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

_HASHER = PasswordHasher()


def hash_passphrase(passphrase: str) -> str:
    """Return an argon2id hash string including parameters + random salt."""
    return _HASHER.hash(passphrase)


def verify_passphrase(digest: str, passphrase: str) -> bool:
    """Constant-time verify; returns False on mismatch or invalid digest."""
    try:
        return _HASHER.verify(digest, passphrase)
    except VerifyMismatchError:
        return False
