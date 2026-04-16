from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from agentlabx.config.settings import AppSettings
from agentlabx.server.app import create_app
from agentlabx.server.rate_limit import LoginRateLimiter


@pytest.mark.asyncio
@pytest.mark.integration
async def test_register_duplicate_email_returns_409(
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
                    "email": "dup@example.com",
                    "passphrase": "hunter2xy",
                },
            )
            assert r.status_code == 201
            r = await c.post(
                "/api/auth/register",
                json={
                    "display_name": "Bob",
                    "email": "dup@example.com",
                    "passphrase": "hunter2xy",
                },
            )
            assert r.status_code == 409
            assert "already registered" in r.json()["detail"]
    finally:
        await app.state.db.close()


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
                json={
                    "display_name": "Alice",
                    "email": "alice@example.com",
                    "passphrase": "hunter2xy",
                },
            )
            assert r.status_code == 201
            identity = r.json()
            assert "admin" in identity["capabilities"]
            assert identity["email"] == "alice@example.com"

            r = await c.post(
                "/api/auth/login",
                json={"email": "alice@example.com", "passphrase": "hunter2xy"},
            )
            assert r.status_code == 200
            assert "agentlabx_session" in r.cookies

            r = await c.get("/api/auth/me")
            assert r.status_code == 200
            assert r.json()["id"] == identity["id"]
            assert r.json()["email"] == "alice@example.com"

            r = await c.post("/api/auth/logout")
            assert r.status_code == 204

            r = await c.get("/api/auth/me")
            assert r.status_code == 401
    finally:
        await app.state.db.close()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_update_display_name_via_api(
    tmp_workspace: Path, ephemeral_keyring: dict[tuple[str, str], str]
) -> None:
    settings = AppSettings(workspace=tmp_workspace)
    app = await create_app(settings)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            await c.post(
                "/api/auth/register",
                json={"display_name": "A", "email": "a@x.com", "passphrase": "p1234567"},
            )
            await c.post(
                "/api/auth/login",
                json={"email": "a@x.com", "passphrase": "p1234567"},
            )
            r = await c.patch(
                "/api/auth/me/display-name",
                json={"display_name": "A2"},
            )
            assert r.status_code == 200
            assert r.json()["display_name"] == "A2"
    finally:
        await app.state.db.close()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_update_email_requires_passphrase(
    tmp_workspace: Path, ephemeral_keyring: dict[tuple[str, str], str]
) -> None:
    settings = AppSettings(workspace=tmp_workspace)
    app = await create_app(settings)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            await c.post(
                "/api/auth/register",
                json={"display_name": "A", "email": "a@x.com", "passphrase": "p1234567"},
            )
            await c.post(
                "/api/auth/login",
                json={"email": "a@x.com", "passphrase": "p1234567"},
            )
            r = await c.patch(
                "/api/auth/me/email",
                json={"new_email": "b@x.com", "passphrase": "wrongpass"},
            )
            assert r.status_code == 401
            r = await c.patch(
                "/api/auth/me/email",
                json={"new_email": "b@x.com", "passphrase": "p1234567"},
            )
            assert r.status_code == 200
            assert r.json()["email"] == "b@x.com"
    finally:
        await app.state.db.close()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_update_passphrase_via_api(
    tmp_workspace: Path, ephemeral_keyring: dict[tuple[str, str], str]
) -> None:
    settings = AppSettings(workspace=tmp_workspace)
    app = await create_app(settings)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            await c.post(
                "/api/auth/register",
                json={"display_name": "A", "email": "a@x.com", "passphrase": "old123456"},
            )
            await c.post(
                "/api/auth/login",
                json={"email": "a@x.com", "passphrase": "old123456"},
            )
            r = await c.patch(
                "/api/auth/me/passphrase",
                json={"old_passphrase": "wrong12345", "new_passphrase": "whatever1"},
            )
            assert r.status_code == 401
            r = await c.patch(
                "/api/auth/me/passphrase",
                json={"old_passphrase": "old123456", "new_passphrase": "new123456"},
            )
            assert r.status_code == 200
            # log out and log in with new passphrase
            await c.post("/api/auth/logout")
            r = await c.post(
                "/api/auth/login",
                json={"email": "a@x.com", "passphrase": "new123456"},
            )
            assert r.status_code == 200
    finally:
        await app.state.db.close()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_repeated_failed_logins_trigger_429(
    tmp_workspace: Path, ephemeral_keyring: dict[tuple[str, str], str]
) -> None:
    settings = AppSettings(workspace=tmp_workspace)
    app = await create_app(settings)
    # Shrink the limiter for the test
    app.state.login_limiter = LoginRateLimiter(
        max_failures=3, window_seconds=60, lockout_seconds=30
    )
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as c:
            await c.post(
                "/api/auth/register",
                json={"display_name": "A", "email": "a@x.com", "passphrase": "p1234567"},
            )
            # 3 failed attempts → last one triggers 429
            for i in range(3):
                r = await c.post(
                    "/api/auth/login",
                    json={"email": "a@x.com", "passphrase": "wrong"},
                )
                if i < 2:
                    assert r.status_code == 401
                else:
                    assert r.status_code == 429
                    assert "Retry-After" in r.headers
            # even correct passphrase is locked out
            r = await c.post(
                "/api/auth/login",
                json={"email": "a@x.com", "passphrase": "p1234567"},
            )
            assert r.status_code == 429
    finally:
        await app.state.db.close()
