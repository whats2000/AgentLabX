from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from agentlabx.config.settings import AppSettings
from agentlabx.db.schema import Session as SessionRow
from agentlabx.server.app import create_app
from agentlabx.server.rate_limit import LoginRateLimiter


@pytest.mark.asyncio
@pytest.mark.integration
async def test_register_refuses_second_self_signup(
    tmp_workspace: Path, ephemeral_keyring: dict[tuple[str, str], str]
) -> None:
    """C1: after the first user registers, a second public /register call returns 403."""
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
            r = await c.post(
                "/api/auth/register",
                json={
                    "display_name": "Bob",
                    "email": "bob@example.com",
                    "passphrase": "hunter2xy",
                },
            )
            assert r.status_code == 403
            assert "self-registration disabled" in r.json()["detail"]
    finally:
        await app.state.db.close()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_register_duplicate_email_via_admin_returns_409(
    tmp_workspace: Path, ephemeral_keyring: dict[tuple[str, str], str]
) -> None:
    """C1 follow-on: duplicate email detection is now admin-side only."""
    settings = AppSettings(workspace=tmp_workspace)
    app = await create_app(settings)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            # First user self-registers and becomes admin.
            r = await c.post(
                "/api/auth/register",
                json={
                    "display_name": "Alice",
                    "email": "alice@example.com",
                    "passphrase": "hunter2xy",
                },
            )
            assert r.status_code == 201
            # Log in as admin.
            r = await c.post(
                "/api/auth/login",
                json={"email": "alice@example.com", "passphrase": "hunter2xy"},
            )
            assert r.status_code == 200
            # Create bob via admin endpoint.
            r = await c.post(
                "/api/settings/admin/users",
                json={
                    "display_name": "Bob",
                    "email": "bob@example.com",
                    "passphrase": "bobpass12",
                },
            )
            assert r.status_code == 201
            # Try to create bob again — 409.
            r = await c.post(
                "/api/settings/admin/users",
                json={
                    "display_name": "Bob2",
                    "email": "bob@example.com",
                    "passphrase": "bobpass12",
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
async def test_passphrase_change_revokes_other_sessions(
    tmp_workspace: Path, ephemeral_keyring: dict[tuple[str, str], str]
) -> None:
    """I1: after passphrase change, other sessions are revoked; caller gets a fresh cookie."""
    settings = AppSettings(workspace=tmp_workspace)
    app = await create_app(settings)
    try:
        async with (
            AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c_a,
            AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c_b,
        ):
            # Register admin.
            await c_a.post(
                "/api/auth/register",
                json={"display_name": "A", "email": "a@x.com", "passphrase": "old123456"},
            )
            # Client A logs in.
            await c_a.post(
                "/api/auth/login",
                json={"email": "a@x.com", "passphrase": "old123456"},
            )
            # Client B logs in.
            await c_b.post(
                "/api/auth/login",
                json={"email": "a@x.com", "passphrase": "old123456"},
            )
            # Both clients can call /me.
            assert (await c_a.get("/api/auth/me")).status_code == 200
            assert (await c_b.get("/api/auth/me")).status_code == 200
            # Client A changes passphrase.
            r = await c_a.patch(
                "/api/auth/me/passphrase",
                json={"old_passphrase": "old123456", "new_passphrase": "new123456"},
            )
            assert r.status_code == 200
            # Client A gets a fresh cookie and can still call /me.
            assert (await c_a.get("/api/auth/me")).status_code == 200
            # Client B's old session is revoked — 401.
            assert (await c_b.get("/api/auth/me")).status_code == 401
    finally:
        await app.state.db.close()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_passphrase_change_revokes_tokens(
    tmp_workspace: Path, ephemeral_keyring: dict[tuple[str, str], str]
) -> None:
    """I1: personal tokens are revoked when passphrase changes."""
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
            r = await c.post("/api/auth/me/tokens", json={"label": "ci"})
            assert r.status_code == 201
            token = r.json()["token"]
            # Change passphrase.
            r = await c.patch(
                "/api/auth/me/passphrase",
                json={"old_passphrase": "old123456", "new_passphrase": "new123456"},
            )
            assert r.status_code == 200
        # Use old bearer token in a fresh client — should be 401.
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c2:
            r = await c2.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
            assert r.status_code == 401
    finally:
        await app.state.db.close()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_login_revokes_incoming_session_cookie(
    tmp_workspace: Path, ephemeral_keyring: dict[tuple[str, str], str]
) -> None:
    """I2: logging in with an existing cookie revokes the old session (s1) and issues s2."""
    settings = AppSettings(workspace=tmp_workspace)
    app = await create_app(settings)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            await c.post(
                "/api/auth/register",
                json={"display_name": "A", "email": "a@x.com", "passphrase": "p1234567"},
            )
            # First login → session s1.
            r = await c.post(
                "/api/auth/login",
                json={"email": "a@x.com", "passphrase": "p1234567"},
            )
            assert r.status_code == 200
            # Second login with same client (carries s1 cookie) → session s2, s1 revoked.
            r = await c.post(
                "/api/auth/login",
                json={"email": "a@x.com", "passphrase": "p1234567"},
            )
            assert r.status_code == 200
            # Only one non-revoked session should exist now.
            r = await c.get("/api/auth/me/sessions")
            assert r.status_code == 200
            sessions = r.json()
            assert len(sessions) == 1
            assert sessions[0]["is_current"] is True
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
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
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


@pytest.mark.asyncio
@pytest.mark.integration
async def test_remember_me_extends_session_lifetime(
    tmp_workspace: Path, ephemeral_keyring: dict[tuple[str, str], str]
) -> None:
    """Login with remember_me=true should issue a 30-day session instead of 12h."""
    settings = AppSettings(workspace=tmp_workspace)
    app = await create_app(settings)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            await c.post(
                "/api/auth/register",
                json={"display_name": "A", "email": "a@x.com", "passphrase": "p1234567"},
            )

            def _extract_max_age(response: object) -> int:
                from httpx import Response as HttpxResponse

                assert isinstance(response, HttpxResponse)
                for val in response.headers.get_list("set-cookie"):
                    if "agentlabx_session" in val:
                        for part in val.split(";"):
                            if part.strip().lower().startswith("max-age="):
                                return int(part.strip().split("=")[1])
                raise AssertionError("agentlabx_session cookie not found in Set-Cookie")

            # Normal login (remember_me=false) → 12h cookie
            r = await c.post(
                "/api/auth/login",
                json={"email": "a@x.com", "passphrase": "p1234567"},
            )
            assert r.status_code == 200
            normal_max_age = _extract_max_age(r)
            assert normal_max_age == settings.session_max_age_seconds

            # Remember-me login → 30-day cookie
            r = await c.post(
                "/api/auth/login",
                json={"email": "a@x.com", "passphrase": "p1234567", "remember_me": True},
            )
            assert r.status_code == 200
            remember_max_age = _extract_max_age(r)
            assert remember_max_age == settings.remember_me_max_age_seconds
            assert remember_max_age > normal_max_age

            # Verify DB session row: the most recent session should expire ~30 days from now
            db = app.state.db
            async with db.session() as session:
                rows = (
                    (
                        await session.execute(
                            select(SessionRow)
                            .where(SessionRow.revoked.is_(False))
                            .order_by(SessionRow.issued_at.desc())
                        )
                    )
                    .scalars()
                    .all()
                )
                latest = rows[0]
                expires_at = latest.expires_at
                if expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=timezone.utc)
                remaining = (expires_at - datetime.now(tz=timezone.utc)).total_seconds()
                # Should be close to 30 days (~2592000s), definitely more than 12h (43200s)
                assert remaining > 86400  # at least 1 day
    finally:
        await app.state.db.close()
