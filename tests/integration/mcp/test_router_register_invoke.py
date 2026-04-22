"""Full ``/api/mcp/*`` round-trip via the FastAPI ASGI test client.

Covers:

* Register a user-scope echo server via REST, GET the server list,
  invoke the ``echo`` tool via the debug endpoint, DELETE, assert subsequent
  GET 404.
* Repeat as user B and verify isolation — A's server is invisible to B; the
  seeded admin-scope memory server IS visible.
* Try to register an admin-scope server as a non-admin user — assert 403.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from agentlabx.config.settings import AppSettings
from agentlabx.server.app import create_app

ECHO_COMMAND: list[str] = [sys.executable, "-m", "tests.fakes.echo_mcp_server"]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_full_register_invoke_delete_roundtrip(
    tmp_workspace: Path, ephemeral_keyring: dict[tuple[str, str], str]
) -> None:
    settings = AppSettings(workspace=tmp_workspace)
    app = await create_app(settings)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            # First user self-registers and becomes admin (owner).
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

            # Register a user-scope echo server via REST.
            r = await c.post(
                "/api/mcp/servers",
                json={
                    "name": "echo-user",
                    "scope": "user",
                    "transport": "stdio",
                    "command": ECHO_COMMAND,
                    "declared_capabilities": ["echo_default"],
                },
            )
            assert r.status_code == 201, r.text
            body = r.json()
            assert body["name"] == "echo-user"
            assert body["scope"] == "user"
            assert body["enabled"] is True
            assert any(t["tool_name"] == "echo" for t in body["tools"])
            server_id = body["id"]

            # GET listing — server visible with tools.
            r = await c.get("/api/mcp/servers")
            assert r.status_code == 200
            servers = r.json()
            mine = [s for s in servers if s["id"] == server_id]
            assert len(mine) == 1
            tool_names = {t["tool_name"] for t in mine[0]["tools"]}
            assert "echo" in tool_names
            assert "boom" in tool_names

            # GET /api/mcp/tools — flat aggregate
            r = await c.get("/api/mcp/tools")
            assert r.status_code == 200
            tools = r.json()
            assert any(t["server_id"] == server_id and t["tool_name"] == "echo" for t in tools)

            # Invoke echo via the debug endpoint.
            r = await c.post(
                f"/api/mcp/servers/{server_id}/tools/echo/invoke",
                json={"args": {"message": "hi-router"}},
            )
            assert r.status_code == 200, r.text
            payload = r.json()
            assert payload["is_error"] is False
            assert "hi-router" in payload["text"]

            # DELETE — subsequent GET 404
            r = await c.delete(f"/api/mcp/servers/{server_id}")
            assert r.status_code == 204
            r = await c.get(f"/api/mcp/servers/{server_id}")
            assert r.status_code == 404
    finally:
        await app.state.mcp_host.stop_all()
        await app.state.db.close()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_user_scope_isolation_and_admin_seeded_visible(
    tmp_workspace: Path, ephemeral_keyring: dict[tuple[str, str], str]
) -> None:
    settings = AppSettings(workspace=tmp_workspace)
    app = await create_app(settings)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            # Admin (Alice) self-registers; provisions Bob.
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

            # Alice registers a user-scope server.
            r = await c.post(
                "/api/mcp/servers",
                json={
                    "name": "alice-echo",
                    "scope": "user",
                    "transport": "stdio",
                    "command": ECHO_COMMAND,
                    "declared_capabilities": ["echo_default"],
                },
            )
            assert r.status_code == 201
            alice_server_id = r.json()["id"]

            # Alice provisions Bob via admin endpoint.
            r = await c.post(
                "/api/settings/admin/users",
                json={
                    "display_name": "Bob",
                    "email": "bob@example.com",
                    "passphrase": "bobpassx12",
                },
            )
            assert r.status_code == 201

            # Log out as Alice; log in as Bob.
            await c.post("/api/auth/logout")
            r = await c.post(
                "/api/auth/login",
                json={"email": "bob@example.com", "passphrase": "bobpassx12"},
            )
            assert r.status_code == 200

            # Bob lists servers — Alice's user-scope server NOT present;
            # admin-scope memory bundle IS present.
            r = await c.get("/api/mcp/servers")
            assert r.status_code == 200
            visible = r.json()
            assert all(s["id"] != alice_server_id for s in visible)
            scopes = {s["scope"] for s in visible}
            assert "admin" in scopes
            names = {s["name"] for s in visible}
            assert "memory" in names

            # Bob tries to register an admin-scope server — 403.
            r = await c.post(
                "/api/mcp/servers",
                json={
                    "name": "bob-admin-attempt",
                    "scope": "admin",
                    "transport": "stdio",
                    "command": ECHO_COMMAND,
                    "declared_capabilities": [],
                },
            )
            assert r.status_code == 403

            # Bob cannot GET Alice's server (404 — invisible).
            r = await c.get(f"/api/mcp/servers/{alice_server_id}")
            assert r.status_code == 404

            # Bob cannot DELETE Alice's server (404 — invisible).
            r = await c.delete(f"/api/mcp/servers/{alice_server_id}")
            assert r.status_code == 404
    finally:
        await app.state.mcp_host.stop_all()
        await app.state.db.close()
