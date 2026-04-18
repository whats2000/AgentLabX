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
async def test_permanent_delete_removes_revoked_token(
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
            r = await c.post("/api/auth/me/tokens", json={"label": "disposable"})
            token_id = r.json()["id"]

            # Revoke first
            r = await c.delete(f"/api/auth/me/tokens/{token_id}")
            assert r.status_code == 204

            # Token still shows in list (soft-deleted)
            r = await c.get("/api/auth/me/tokens")
            ids = [t["id"] for t in r.json()]
            assert token_id in ids

            # Permanently delete
            r = await c.delete(f"/api/auth/me/tokens/{token_id}/permanently")
            assert r.status_code == 204

            # Now gone from list
            r = await c.get("/api/auth/me/tokens")
            ids = [t["id"] for t in r.json()]
            assert token_id not in ids
    finally:
        await app.state.db.close()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_permanent_delete_rejects_active_token(
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
            r = await c.post("/api/auth/me/tokens", json={"label": "active"})
            token_id = r.json()["id"]

            # Try to permanently delete without revoking first — should fail
            r = await c.delete(f"/api/auth/me/tokens/{token_id}/permanently")
            assert r.status_code == 400
            assert "revoked" in r.json()["detail"]
    finally:
        await app.state.db.close()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_refresh_token_deletes_old_issues_new(
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
            r = await c.post("/api/auth/me/tokens", json={"label": "my-token"})
            old_token = r.json()["token"]
            old_id = r.json()["id"]

            # Refresh — old token deleted, new one issued with same label
            r = await c.post(f"/api/auth/me/tokens/{old_id}/refresh")
            assert r.status_code == 201
            new_token = r.json()["token"]
            new_id = r.json()["id"]
            assert r.json()["label"] == "my-token"  # same label
            assert new_id != old_id
            assert new_token != old_token

            # Old token should be gone from the list (deleted, not just revoked)
            r = await c.get("/api/auth/me/tokens")
            ids = [t["id"] for t in r.json()]
            assert old_id not in ids
            assert new_id in ids

        # Old token should be rejected
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as c2:
            r = await c2.get("/api/auth/me", headers={"Authorization": f"Bearer {old_token}"})
            assert r.status_code == 401

        # New token should work
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as c3:
            r = await c3.get("/api/auth/me", headers={"Authorization": f"Bearer {new_token}"})
            assert r.status_code == 200
            assert r.json()["email"] == "a@x.com"
    finally:
        await app.state.db.close()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_refresh_rejects_already_revoked_token(
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
            r = await c.post("/api/auth/me/tokens", json={"label": "dead"})
            token_id = r.json()["id"]

            # Revoke it
            await c.delete(f"/api/auth/me/tokens/{token_id}")

            # Try to refresh — should fail
            r = await c.post(f"/api/auth/me/tokens/{token_id}/refresh")
            assert r.status_code == 400
            assert "revoked" in r.json()["detail"]
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
