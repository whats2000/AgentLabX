from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from _pytest.monkeypatch import MonkeyPatch


@pytest.fixture()
def tmp_workspace(tmp_path: Path) -> Iterator[Path]:
    """A throwaway workspace directory per test."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    yield workspace


@pytest.fixture()
def ephemeral_keyring(monkeypatch: MonkeyPatch) -> Iterator[dict[tuple[str, str], str]]:
    """Replace the system keyring with an in-memory dict so tests do not touch the OS."""
    store: dict[tuple[str, str], str] = {}

    import keyring
    from keyring.backend import KeyringBackend

    class InMemoryKeyring(KeyringBackend):
        priority: int = 1

        def get_password(self, service: str, username: str) -> str | None:
            return store.get((service, username))

        def set_password(self, service: str, username: str, password: str) -> None:
            store[(service, username)] = password

        def delete_password(self, service: str, username: str) -> None:
            store.pop((service, username), None)

    previous = keyring.get_keyring()
    keyring.set_keyring(InMemoryKeyring())  # type: ignore[no-untyped-call]
    try:
        yield store
    finally:
        keyring.set_keyring(previous)
