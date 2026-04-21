"""Lifecycle + auth-gate coverage for the ``/api/mcp/*`` router.

Complements ``test_router_register_invoke.py`` with three regression tests
that the polish pass on Stage A3 Task 7 introduced:

* PATCH ``enabled=False`` actually stops the host handle (not just toggles
  the row), and PATCH ``enabled=True`` restarts it with a non-empty tools
  list.
* The startup schema-version pin loudly fails ``create_app`` when
  ``app_state.schema_version`` is mutated out from under the migrator.
* Calls to ``/api/mcp/*`` without a session cookie return 401, confirming
  the auth dependency is wired into every endpoint.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from agentlabx.config.settings import AppSettings
from agentlabx.db.migrations import CURRENT_SCHEMA_VERSION, apply_migrations
from agentlabx.db.session import DatabaseHandle
from agentlabx.mcp.protocol import ServerNotRunning
from agentlabx.server.app import create_app

ECHO_COMMAND: list[str] = [sys.executable, "-m", "tests.fakes.echo_mcp_server"]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_patch_enabled_round_trip_stops_and_restarts_host(
    tmp_workspace: Path, ephemeral_keyring: dict[tuple[str, str], str]
) -> None:
    settings = AppSettings(workspace=tmp_workspace)
    app = await create_app(settings)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.post(
                "/api/auth/register",
                json={
                    "display_name": "Alice",
                    "email": "alice@example.com",
                    "passphrase": "alicepass1",
                },
            )
            assert r.status_code == 201
            r = await c.post(
                "/api/auth/login",
                json={"email": "alice@example.com", "passphrase": "alicepass1"},
            )
            assert r.status_code == 200

            # Register a user-scope echo server (defaults to enabled=True).
            r = await c.post(
                "/api/mcp/servers",
                json={
                    "name": "echo-patch",
                    "scope": "user",
                    "transport": "stdio",
                    "command": ECHO_COMMAND,
                    "declared_capabilities": ["echo_default"],
                },
            )
            assert r.status_code == 201, r.text
            server_id = r.json()["id"]

            host = app.state.mcp_host
            # Sanity: server is currently running -- tools_for must succeed.
            assert host.tools_for(server_id)

            # PATCH enabled=False -> host should drop the handle.
            r = await c.patch(f"/api/mcp/servers/{server_id}", json={"enabled": False})
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["enabled"] is False
            assert body["tools"] == []
            with pytest.raises(ServerNotRunning):
                host.tools_for(server_id)

            # PATCH enabled=True -> host restarts and tools come back.
            r = await c.patch(f"/api/mcp/servers/{server_id}", json={"enabled": True})
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["enabled"] is True
            tool_names = {t["tool_name"] for t in body["tools"]}
            assert "echo" in tool_names
            # And the host knows about it again.
            assert host.tools_for(server_id)
    finally:
        await app.state.mcp_host.stop_all()
        await app.state.db.close()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_unauthenticated_request_returns_401(
    tmp_workspace: Path, ephemeral_keyring: dict[tuple[str, str], str]
) -> None:
    settings = AppSettings(workspace=tmp_workspace)
    app = await create_app(settings)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            # No login / no session cookie -> auth dependency must reject.
            r = await c.get("/api/mcp/servers")
            assert r.status_code == 401
            r = await c.get("/api/mcp/tools")
            assert r.status_code == 401
            r = await c.post(
                "/api/mcp/servers",
                json={
                    "name": "echo-anon",
                    "scope": "user",
                    "transport": "stdio",
                    "command": ECHO_COMMAND,
                    "declared_capabilities": [],
                },
            )
            assert r.status_code == 401
    finally:
        await app.state.mcp_host.stop_all()
        await app.state.db.close()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_assert_schema_version_pinned_raises_on_drift(
    tmp_workspace: Path,
) -> None:
    """The boot pin guard must surface schema drift as a ``RuntimeError``.

    We pre-seed the DB up to ``CURRENT_SCHEMA_VERSION``, then mutate the
    ``app_state.schema_version`` row to a different value and call the pin
    guard directly. ``apply_migrations`` itself rejects newer-than-current
    versions earlier in the boot sequence (before the pin runs), so we test
    the pin in isolation against a smaller-than-current value to prove the
    contract: any divergence -> ``RuntimeError``.
    """

    from agentlabx.server.app import _assert_schema_version_pinned

    settings = AppSettings(workspace=tmp_workspace)
    db = DatabaseHandle(settings.db_path)
    await db.connect()
    await apply_migrations(db)
    # Mutate the persisted version *under* the migrator. The pin guard reads
    # this row directly and compares against the in-code constant.
    poisoned = max(CURRENT_SCHEMA_VERSION - 1, 0)
    async with db.session() as session:
        await session.execute(
            text("UPDATE app_state SET value = :v WHERE key = 'schema_version'"),
            {"v": str(poisoned)},
        )
        await session.commit()

    try:
        with pytest.raises(RuntimeError) as exc_info:
            await _assert_schema_version_pinned(db)
        message = str(exc_info.value)
        assert "schema_version" in message
        assert str(CURRENT_SCHEMA_VERSION) in message
    finally:
        await db.close()
