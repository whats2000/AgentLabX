from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from agentlabx.config.settings import AppSettings
from agentlabx.server.app import create_app


async def _bootstrap_and_login(
    client: AsyncClient,
) -> dict[str, str]:
    """Register admin + login, return cookies dict."""
    await client.post(
        "/api/auth/register",
        json={
            "display_name": "Admin",
            "email": "admin@test.com",
            "passphrase": "testpass123",
        },
    )
    r = await client.post(
        "/api/auth/login",
        json={"email": "admin@test.com", "passphrase": "testpass123"},
    )
    assert r.status_code == 200
    return dict(client.cookies)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_list_providers(
    tmp_workspace: Path,
    ephemeral_keyring: dict[tuple[str, str], str],
) -> None:
    settings = AppSettings(workspace=tmp_workspace)
    app = await create_app(settings)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            await _bootstrap_and_login(c)
            r = await c.get("/api/llm/providers")
            assert r.status_code == 200
            data = r.json()
            assert isinstance(data, list)
            assert len(data) > 0
            first = data[0]
            assert "name" in first
            assert "display_name" in first
            assert "models" in first
    finally:
        await app.state.db.close()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_list_models(
    tmp_workspace: Path,
    ephemeral_keyring: dict[tuple[str, str], str],
) -> None:
    settings = AppSettings(workspace=tmp_workspace)
    app = await create_app(settings)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            await _bootstrap_and_login(c)
            r = await c.get("/api/llm/models")
            assert r.status_code == 200
            data = r.json()
            assert isinstance(data, list)
            assert len(data) > 0
            first = data[0]
            assert "id" in first
            assert "display_name" in first
            assert "provider" in first
    finally:
        await app.state.db.close()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_list_providers_unauthenticated(
    tmp_workspace: Path,
    ephemeral_keyring: dict[tuple[str, str], str],
) -> None:
    settings = AppSettings(workspace=tmp_workspace)
    app = await create_app(settings)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.get("/api/llm/providers")
            assert r.status_code == 401
    finally:
        await app.state.db.close()
