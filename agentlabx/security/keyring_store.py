from __future__ import annotations

import secrets

import keyring
from cryptography.fernet import Fernet

KEYRING_SERVICE = "agentlabx"
_MASTER_KEY_NAME = "master_key"
_SESSION_SECRET_NAME = "session_secret"


def get_or_create_master_key() -> bytes:
    """Return the Fernet master key, generating + persisting one on first call."""
    stored = keyring.get_password(KEYRING_SERVICE, _MASTER_KEY_NAME)
    if stored is not None:
        return stored.encode("utf-8")
    key = Fernet.generate_key()
    keyring.set_password(KEYRING_SERVICE, _MASTER_KEY_NAME, key.decode("utf-8"))
    return key


def get_or_create_session_secret() -> bytes:
    """Return a stable secret for itsdangerous cookie signing."""
    stored = keyring.get_password(KEYRING_SERVICE, _SESSION_SECRET_NAME)
    if stored is not None:
        return stored.encode("utf-8")
    secret = secrets.token_urlsafe(48).encode("utf-8")
    keyring.set_password(KEYRING_SERVICE, _SESSION_SECRET_NAME, secret.decode("utf-8"))
    return secret
