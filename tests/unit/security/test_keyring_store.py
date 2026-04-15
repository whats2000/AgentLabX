from __future__ import annotations

from agentlabx.security.keyring_store import (
    KEYRING_SERVICE,
    get_or_create_master_key,
    get_or_create_session_secret,
)


def test_master_key_is_stable_across_calls(
    ephemeral_keyring: dict[tuple[str, str], str],
) -> None:
    first = get_or_create_master_key()
    second = get_or_create_master_key()
    assert first == second
    assert (KEYRING_SERVICE, "master_key") in ephemeral_keyring


def test_session_secret_is_stable_across_calls(
    ephemeral_keyring: dict[tuple[str, str], str],
) -> None:
    first = get_or_create_session_secret()
    second = get_or_create_session_secret()
    assert first == second
    assert (KEYRING_SERVICE, "session_secret") in ephemeral_keyring


def test_master_key_and_session_secret_are_independent(
    ephemeral_keyring: dict[tuple[str, str], str],
) -> None:
    master = get_or_create_master_key()
    session = get_or_create_session_secret()
    assert master != session


def test_master_key_has_fernet_shape(
    ephemeral_keyring: dict[tuple[str, str], str],
) -> None:
    from cryptography.fernet import Fernet

    master = get_or_create_master_key()
    # Fernet keys are 32 url-safe base64 bytes → raises on malformed.
    Fernet(master)
