from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from agentlabx.config.settings import AppSettings
from agentlabx.server.app import create_app


@pytest.mark.asyncio
@pytest.mark.integration
async def test_bearer_token_authenticates_on_me(
    tmp_workspace: Path, ephemeral_keyring: dict[tuple[str, str], str]
) -> None:
    settings = AppSettings(workspace=tmp_workspace)
    app = await create_app(settings)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as c:
            await c.post(
                "/api/auth/register",
                json={"display_name": "A", "email": "a@x.com", "passphrase": "p1234567"},
            )
            await c.post(
                "/api/auth/login",
                json={"email": "a@x.com", "passphrase": "p1234567"},
            )
            r = await c.post("/api/auth/me/tokens", json={"label": "ci"})
            token = r.json()["token"]
        # new client, no cookies, uses Authorization header
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as c2:
            r = await c2.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
            assert r.status_code == 200
            assert r.json()["email"] == "a@x.com"
    finally:
        await app.state.db.close()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_revoked_token_fails_bearer_auth(
    tmp_workspace: Path, ephemeral_keyring: dict[tuple[str, str], str]
) -> None:
    settings = AppSettings(workspace=tmp_workspace)
    app = await create_app(settings)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as c:
            await c.post(
                "/api/auth/register",
                json={"display_name": "A", "email": "a@x.com", "passphrase": "p1234567"},
            )
            await c.post(
                "/api/auth/login",
                json={"email": "a@x.com", "passphrase": "p1234567"},
            )
            r = await c.post("/api/auth/me/tokens", json={"label": "ci"})
            token = r.json()["token"]
            token_id = r.json()["id"]
            r = await c.delete(f"/api/auth/me/tokens/{token_id}")
            assert r.status_code == 204
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as c2:
            r = await c2.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
            assert r.status_code == 401
    finally:
        await app.state.db.close()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_list_tokens_returns_labels_without_plaintext(
    tmp_workspace: Path, ephemeral_keyring: dict[tuple[str, str], str]
) -> None:
    settings = AppSettings(workspace=tmp_workspace)
    app = await create_app(settings)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as c:
            await c.post(
                "/api/auth/register",
                json={"display_name": "A", "email": "a@x.com", "passphrase": "p1234567"},
            )
            await c.post(
                "/api/auth/login",
                json={"email": "a@x.com", "passphrase": "p1234567"},
            )
            await c.post("/api/auth/me/tokens", json={"label": "ci"})
            await c.post("/api/auth/me/tokens", json={"label": "deploy"})
            r = await c.get("/api/auth/me/tokens")
            assert r.status_code == 200
            labels = [t["label"] for t in r.json()]
            assert set(labels) == {"ci", "deploy"}
            # No "token" field should appear in list response
            for t in r.json():
                assert "token" not in t
    finally:
        await app.state.db.close()
