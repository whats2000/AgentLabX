from __future__ import annotations

import socket
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
import uvicorn

from tests.mock_llm_server import MockServerState, create_mock_app

if TYPE_CHECKING:
    from _pytest.monkeypatch import MonkeyPatch


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        addr: tuple[str, int] = s.getsockname()
        return addr[1]


@dataclass
class MockLLMService:
    """Handle returned by the mock_llm_server fixture."""

    base_url: str
    port: int
    state: MockServerState


@pytest.fixture()
def mock_llm_server() -> Iterator[MockLLMService]:
    """Start a real HTTP mock LLM server on a random port for the test."""
    port = _find_free_port()
    state = MockServerState()
    app = create_mock_app(state)

    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", ws="none")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    # Wait for server to be ready
    for _ in range(50):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                break
        except OSError:
            time.sleep(0.1)

    yield MockLLMService(
        base_url=f"http://127.0.0.1:{port}/v1",
        port=port,
        state=state,
    )

    server.should_exit = True
    thread.join(timeout=5)


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
