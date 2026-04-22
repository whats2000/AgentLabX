"""Reproduce the live-server invoke hang via real Uvicorn HTTP.

The pure ASGI ``httpx.ASGITransport`` test in
``test_router_register_invoke.py`` exercises the same FastAPI app but does
NOT go through Uvicorn's HTTP server. The cross-task scheduling boundary
introduced by Uvicorn + Starlette's ``BaseHTTPMiddleware`` (each request
runs inside an inner anyio task group) is what makes ``host.call`` hang
when the call hand-off uses ``asyncio`` primitives instead of ``anyio``
ones — anyio's cancel scopes don't traverse the asyncio.Future boundary
cleanly across that task hierarchy.

This test boots the full FastAPI app under a real Uvicorn server on a
loopback port, registers a stdio echo MCP server via REST, and POSTs an
invoke. With the broken impl the POST hangs forever; with the anyio fix
it returns within seconds.
"""

from __future__ import annotations

import socket
import sys
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import cast

import httpx
import pytest
import uvicorn
from fastapi import FastAPI

from agentlabx.config.settings import AppSettings
from agentlabx.server.app import create_app_for_uvicorn

ECHO_COMMAND: list[str] = [sys.executable, "-m", "tests.fakes.echo_mcp_server"]


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        addr: tuple[str, int] = s.getsockname()
        return addr[1]


class _UvicornHandle:
    def __init__(self, app: FastAPI, port: int) -> None:
        self.app = app
        self.port = port
        self.base_url = f"http://127.0.0.1:{port}"
        self._server: uvicorn.Server | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        config = uvicorn.Config(
            self.app,
            host="127.0.0.1",
            port=self.port,
            log_level="warning",
            ws="none",
            lifespan="on",
        )
        server = uvicorn.Server(config)
        self._server = server
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        self._thread = thread
        # Wait for readiness.
        for _ in range(100):
            try:
                with socket.create_connection(("127.0.0.1", self.port), timeout=0.1):
                    return
            except OSError:
                time.sleep(0.1)
        raise RuntimeError("uvicorn server did not become ready in time")

    def stop(self) -> None:
        if self._server is not None:
            self._server.should_exit = True
        if self._thread is not None:
            self._thread.join(timeout=10)


@pytest.fixture()
def live_app(
    tmp_workspace: Path, ephemeral_keyring: dict[tuple[str, str], str]
) -> Iterator[_UvicornHandle]:
    del ephemeral_keyring  # fixture used for its keyring side effect only
    settings = AppSettings(workspace=tmp_workspace)
    # Use the production code path: ``create_app_for_uvicorn`` defers all
    # async wiring to the Uvicorn lifespan, so MCP owner tasks live on the
    # same loop that handles requests. This is exactly what the CLI does.
    app = create_app_for_uvicorn(settings)
    handle = _UvicornHandle(app=app, port=_find_free_port())
    handle.start()
    try:
        yield handle
    finally:
        handle.stop()


@pytest.mark.integration
def test_invoke_echo_through_full_uvicorn_stack(live_app: _UvicornHandle) -> None:
    """POSTing an invoke through real Uvicorn must not hang.

    Reproduces the production-mode hang that pure-ASGI tests miss. Hard
    timeout of 15s — under a broken cross-task hand-off this hangs
    indefinitely; under a correct one this returns in well under a second.
    """

    base = live_app.base_url
    with httpx.Client(base_url=base, timeout=15.0) as client:
        # Self-register first user (becomes admin).
        r = client.post(
            "/api/auth/register",
            json={
                "display_name": "Alice",
                "email": "alice@example.com",
                "passphrase": "alicepass1",
            },
        )
        assert r.status_code == 201, r.text
        r = client.post(
            "/api/auth/login",
            json={"email": "alice@example.com", "passphrase": "alicepass1"},
        )
        assert r.status_code == 200, r.text

        r = client.post(
            "/api/mcp/servers",
            json={
                "name": "echo-uvicorn",
                "scope": "user",
                "transport": "stdio",
                "command": ECHO_COMMAND,
                "declared_capabilities": ["echo_default"],
            },
        )
        assert r.status_code == 201, r.text
        server_id = cast(str, r.json()["id"])

        # The hang reproducer — POST /invoke through the BaseHTTPMiddleware
        # task group. Must return well within the 15s client timeout.
        r = client.post(
            f"/api/mcp/servers/{server_id}/tools/echo/invoke",
            json={"args": {"message": "hi-uvicorn"}},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["is_error"] is False
        assert "hi-uvicorn" in body["text"]


@pytest.mark.integration
def test_invoke_inprocess_memory_through_full_uvicorn_stack(
    live_app: _UvicornHandle,
) -> None:
    """In-process memory bundle invoke through real Uvicorn must not hang.

    The original live-curl repro targets the seeded admin-scope memory
    bundle (transport=inprocess). This is a harder hang case than stdio
    because the in-process MCP transport uses anyio memory-object streams
    end-to-end with no subprocess pipe boundary in between, so any
    asyncio.Future-based cross-task hand-off is more likely to deadlock
    against anyio's task-affine cancel scopes.
    """

    base = live_app.base_url
    with httpx.Client(base_url=base, timeout=15.0) as client:
        r = client.post(
            "/api/auth/register",
            json={
                "display_name": "Alice",
                "email": "alice@example.com",
                "passphrase": "alicepass1",
            },
        )
        assert r.status_code == 201, r.text
        r = client.post(
            "/api/auth/login",
            json={"email": "alice@example.com", "passphrase": "alicepass1"},
        )
        assert r.status_code == 200, r.text

        # Find the seeded admin-scope memory bundle. This is the exact
        # path the live-curl repro hits — the server was auto-started
        # during Uvicorn's lifespan bootstrap.
        r = client.get("/api/mcp/servers")
        assert r.status_code == 200
        memory = next(
            (s for s in r.json() if s["name"] == "memory" and s["scope"] == "admin"),
            None,
        )
        assert memory is not None, "memory bundle should be seeded admin-scope"
        memory_id = cast(str, memory["id"])

        # Invoke memory.create — this is the live-curl repro path. With
        # the broken asyncio.Queue + asyncio.Future hand-off this hangs
        # forever; with the anyio memory-object-stream hand-off it
        # returns within ~1s.
        r = client.post(
            f"/api/mcp/servers/{memory_id}/tools/memory.create/invoke",
            json={
                "args": {
                    "category": "smoke",
                    "body": "hello",
                    "source_run_id": None,
                }
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["is_error"] is False, body
