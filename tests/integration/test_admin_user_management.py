from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from agentlabx.config.settings import AppSettings
from agentlabx.server.app import create_app


@pytest.mark.asyncio
@pytest.mark.integration
async def test_admin_can_delete_another_user(
    tmp_workspace: Path, ephemeral_keyring: dict[tuple[str, str], str]
) -> None:
    settings = AppSettings(workspace=tmp_workspace)
    app = await create_app(settings)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.post(
                "/api/auth/register",
                json={
                    "display_name": "Admin",
                    "email": "admin@example.com",
                    "passphrase": "admin12345",
                },
            )
            assert r.status_code == 201
            await c.post(
                "/api/auth/login",
                json={"email": "admin@example.com", "passphrase": "admin12345"},
            )
            r = await c.post(
                "/api/settings/admin/users",
                json={
                    "display_name": "Bob",
                    "email": "bob@example.com",
                    "passphrase": "bob1234567",
                },
            )
            assert r.status_code == 201
            bob_id = r.json()["id"]

            r = await c.delete(f"/api/settings/admin/users/{bob_id}")
            assert r.status_code == 204

            r = await c.get("/api/settings/admin/users")
            ids = [u["id"] for u in r.json()]
            assert bob_id not in ids
    finally:
        await app.state.db.close()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_admin_cannot_delete_self(
    tmp_workspace: Path, ephemeral_keyring: dict[tuple[str, str], str]
) -> None:
    settings = AppSettings(workspace=tmp_workspace)
    app = await create_app(settings)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.post(
                "/api/auth/register",
                json={
                    "display_name": "Admin",
                    "email": "admin@example.com",
                    "passphrase": "admin12345",
                },
            )
            admin_id = r.json()["id"]
            await c.post(
                "/api/auth/login",
                json={"email": "admin@example.com", "passphrase": "admin12345"},
            )
            r = await c.delete(f"/api/settings/admin/users/{admin_id}")
            assert r.status_code == 400
            assert "cannot delete" in r.json()["detail"]
    finally:
        await app.state.db.close()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_admin_can_grant_then_revoke_admin_on_another_user(
    tmp_workspace: Path, ephemeral_keyring: dict[tuple[str, str], str]
) -> None:
    settings = AppSettings(workspace=tmp_workspace)
    app = await create_app(settings)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.post(
                "/api/auth/register",
                json={
                    "display_name": "Admin",
                    "email": "admin@example.com",
                    "passphrase": "admin12345",
                },
            )
            assert r.status_code == 201
            await c.post(
                "/api/auth/login",
                json={"email": "admin@example.com", "passphrase": "admin12345"},
            )
            r = await c.post(
                "/api/settings/admin/users",
                json={
                    "display_name": "Bob",
                    "email": "bob@example.com",
                    "passphrase": "bob1234567",
                },
            )
            bob_id = r.json()["id"]

            r = await c.post(
                f"/api/settings/admin/users/{bob_id}/capabilities",
                json={"capability": "admin"},
            )
            assert r.status_code == 204

            r = await c.get("/api/settings/admin/users")
            users = {u["id"]: u for u in r.json()}
            assert "admin" in users[bob_id]["capabilities"]

            r = await c.delete(
                f"/api/settings/admin/users/{bob_id}/capabilities/admin"
            )
            assert r.status_code == 204

            r = await c.get("/api/settings/admin/users")
            users = {u["id"]: u for u in r.json()}
            assert "admin" not in users[bob_id]["capabilities"]
    finally:
        await app.state.db.close()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_admin_cannot_revoke_own_admin(
    tmp_workspace: Path, ephemeral_keyring: dict[tuple[str, str], str]
) -> None:
    settings = AppSettings(workspace=tmp_workspace)
    app = await create_app(settings)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.post(
                "/api/auth/register",
                json={
                    "display_name": "Admin",
                    "email": "admin@example.com",
                    "passphrase": "admin12345",
                },
            )
            admin_id = r.json()["id"]
            await c.post(
                "/api/auth/login",
                json={"email": "admin@example.com", "passphrase": "admin12345"},
            )
            r = await c.delete(
                f"/api/settings/admin/users/{admin_id}/capabilities/admin"
            )
            assert r.status_code == 400
            assert "cannot revoke" in r.json()["detail"]
    finally:
        await app.state.db.close()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_admin_cannot_delete_owner(
    tmp_workspace: Path, ephemeral_keyring: dict[tuple[str, str], str]
) -> None:
    settings = AppSettings(workspace=tmp_workspace)
    app = await create_app(settings)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as c:
            r = await c.post(
                "/api/auth/register",
                json={"display_name": "O", "email": "o@x.com", "passphrase": "p1234567"},
            )
            owner_id = r.json()["id"]
            await c.post(
                "/api/auth/login",
                json={"email": "o@x.com", "passphrase": "p1234567"},
            )
            r = await c.post(
                "/api/settings/admin/users",
                json={"display_name": "A2", "email": "a2@x.com", "passphrase": "p1234567"},
            )
            a2_id = r.json()["id"]
            await c.post(
                f"/api/settings/admin/users/{a2_id}/capabilities",
                json={"capability": "admin"},
            )
            await c.post("/api/auth/logout")
            await c.post(
                "/api/auth/login",
                json={"email": "a2@x.com", "passphrase": "p1234567"},
            )
            r = await c.delete(f"/api/settings/admin/users/{owner_id}")
            assert r.status_code == 400
            assert "owner" in r.json()["detail"]
            r = await c.delete(
                f"/api/settings/admin/users/{owner_id}/capabilities/admin"
            )
            assert r.status_code == 400
            assert "owner" in r.json()["detail"]
    finally:
        await app.state.db.close()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_owner_capability_cannot_be_granted_or_revoked(
    tmp_workspace: Path, ephemeral_keyring: dict[tuple[str, str], str]
) -> None:
    settings = AppSettings(workspace=tmp_workspace)
    app = await create_app(settings)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as c:
            r = await c.post(
                "/api/auth/register",
                json={"display_name": "O", "email": "o@x.com", "passphrase": "p1234567"},
            )
            owner_id = r.json()["id"]
            await c.post(
                "/api/auth/login",
                json={"email": "o@x.com", "passphrase": "p1234567"},
            )
            r = await c.post(
                "/api/settings/admin/users",
                json={"display_name": "U", "email": "u@x.com", "passphrase": "p1234567"},
            )
            u_id = r.json()["id"]
            r = await c.post(
                f"/api/settings/admin/users/{u_id}/capabilities",
                json={"capability": "owner"},
            )
            assert r.status_code == 400
            r = await c.delete(
                f"/api/settings/admin/users/{owner_id}/capabilities/owner"
            )
            assert r.status_code == 400
    finally:
        await app.state.db.close()
