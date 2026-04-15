# tests/integration/test_admin_onboarding.py
from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from agentlabx.config.settings import AppSettings
from agentlabx.server.app import create_app


@pytest.mark.asyncio
@pytest.mark.integration
async def test_admin_onboarding_credential_survives_restart(
    tmp_workspace: Path, ephemeral_keyring: dict[tuple[str, str], str]
) -> None:
    settings = AppSettings(workspace=tmp_workspace)

    # --- first process incarnation ---
    app = await create_app(settings)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.post(
                "/api/auth/register",
                json={
                    "display_name": "Admin",
                    "email": "admin@example.com",
                    "passphrase": "hunter2xy",
                },
            )
            assert r.status_code == 201

            r = await c.post(
                "/api/auth/login",
                json={"email": "admin@example.com", "passphrase": "hunter2xy"},
            )
            assert r.status_code == 200

            r = await c.put(
                "/api/settings/credentials/anthropic",
                json={"value": "sk-anthropic-test-key"},
            )
            assert r.status_code == 204
    finally:
        await app.state.db.close()

    # --- second process incarnation, same workspace + same keyring ---
    app2 = await create_app(settings)
    try:
        async with AsyncClient(transport=ASGITransport(app=app2), base_url="http://test") as c:
            r = await c.post(
                "/api/auth/login",
                json={"email": "admin@example.com", "passphrase": "hunter2xy"},
            )
            assert r.status_code == 200

            r = await c.get("/api/settings/credentials/anthropic/reveal")
            assert r.status_code == 200
            assert r.json()["value"] == "sk-anthropic-test-key"
    finally:
        await app2.state.db.close()
