from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from agentlabx.config.settings import AppSettings
from agentlabx.server.app import create_app


@pytest.mark.asyncio
@pytest.mark.integration
async def test_register_first_user_is_admin_and_login_works(
    tmp_workspace: Path, ephemeral_keyring: dict[tuple[str, str], str]
) -> None:
    settings = AppSettings(workspace=tmp_workspace)
    app = await create_app(settings)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.post(
                "/api/auth/register",
                json={"display_name": "Alice", "passphrase": "hunter2xy"},
            )
            assert r.status_code == 201
            identity = r.json()
            assert "admin" in identity["capabilities"]

            r = await c.post(
                "/api/auth/login",
                json={"identity_id": identity["id"], "passphrase": "hunter2xy"},
            )
            assert r.status_code == 200
            assert "agentlabx_session" in r.cookies

            r = await c.get("/api/auth/me")
            assert r.status_code == 200
            assert r.json()["id"] == identity["id"]

            r = await c.post("/api/auth/logout")
            assert r.status_code == 204

            r = await c.get("/api/auth/me")
            assert r.status_code == 401
    finally:
        await app.state.db.close()
