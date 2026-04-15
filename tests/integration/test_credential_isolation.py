# tests/integration/test_credential_isolation.py
from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from agentlabx.config.settings import AppSettings
from agentlabx.server.app import create_app


@pytest.mark.asyncio
@pytest.mark.integration
async def test_user_b_cannot_see_user_a_credentials(
    tmp_workspace: Path, ephemeral_keyring: dict[tuple[str, str], str]
) -> None:
    settings = AppSettings(workspace=tmp_workspace)
    app = await create_app(settings)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            # Admin (first) creates itself and a second user.
            r = await c.post(
                "/api/auth/register",
                json={
                    "display_name": "Admin",
                    "email": "admin@example.com",
                    "passphrase": "admin12345",
                },
            )
            assert r.status_code == 201
            admin_id = r.json()["id"]

            r = await c.post(
                "/api/auth/login",
                json={"email": "admin@example.com", "passphrase": "admin12345"},
            )
            assert r.status_code == 200

            r = await c.put(
                "/api/settings/credentials/openai",
                json={"value": "sk-user-a-secret"},
            )
            assert r.status_code == 204

            r = await c.post(
                "/api/settings/admin/users",
                json={
                    "display_name": "Bob",
                    "email": "bob@example.com",
                    "passphrase": "bob123456",
                },
            )
            assert r.status_code == 201
            bob_id = r.json()["id"]
            assert r.json()["email"] == "bob@example.com"

            await c.post("/api/auth/logout")

            r = await c.post(
                "/api/auth/login",
                json={"email": "bob@example.com", "passphrase": "bob123456"},
            )
            assert r.status_code == 200

            # Bob asks for his own credentials: empty list.
            r = await c.get("/api/settings/credentials")
            assert r.status_code == 200
            assert r.json() == []

            # Bob cannot reveal a slot he never created (even if Admin owns a slot by that name).
            r = await c.get("/api/settings/credentials/openai/reveal")
            assert r.status_code == 404

            # Bob cannot list all users (admin-only).
            r = await c.get("/api/settings/admin/users")
            assert r.status_code == 403

            # Bob cannot grant himself admin capability.
            r = await c.post(
                f"/api/settings/admin/users/{bob_id}/capabilities",
                json={"capability": "admin"},
            )
            assert r.status_code == 403

            # Suppress unused variable warning
            _ = admin_id
    finally:
        await app.state.db.close()
