from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from agentlabx.config.settings import AppSettings
from agentlabx.server.app import create_app


@pytest.mark.asyncio
@pytest.mark.integration
async def test_list_sessions_returns_current(
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
            r = await c.get("/api/auth/me/sessions")
            assert r.status_code == 200
            sessions = r.json()
            assert len(sessions) == 1
            assert sessions[0]["is_current"] is True
    finally:
        await app.state.db.close()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_revoke_current_session_logs_user_out(
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
            r = await c.get("/api/auth/me/sessions")
            sid = r.json()[0]["id"]
            r = await c.delete(f"/api/auth/me/sessions/{sid}")
            assert r.status_code == 204
            r = await c.get("/api/auth/me")
            assert r.status_code == 401
    finally:
        await app.state.db.close()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_revoke_other_session_keeps_current(
    tmp_workspace: Path, ephemeral_keyring: dict[tuple[str, str], str]
) -> None:
    """Two login-cookies for the same user → revoke the OTHER one via current session."""
    settings = AppSettings(workspace=tmp_workspace)
    app = await create_app(settings)
    try:
        async with (
            AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c_a,
            AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c_b,
        ):
            await c_a.post(
                "/api/auth/register",
                json={"display_name": "A", "email": "a@x.com", "passphrase": "p1234567"},
            )
            # session 1 on client A
            await c_a.post(
                "/api/auth/login",
                json={"email": "a@x.com", "passphrase": "p1234567"},
            )
            # session 2 on client B
            await c_b.post(
                "/api/auth/login",
                json={"email": "a@x.com", "passphrase": "p1234567"},
            )
            r = await c_a.get("/api/auth/me/sessions")
            sessions = r.json()
            assert len(sessions) == 2
            other = next(s for s in sessions if s["is_current"] is False)
            r = await c_a.delete(f"/api/auth/me/sessions/{other['id']}")
            assert r.status_code == 204
            # client A still works
            r = await c_a.get("/api/auth/me")
            assert r.status_code == 200
            # client B is now unauthenticated
            r = await c_b.get("/api/auth/me")
            assert r.status_code == 401
    finally:
        await app.state.db.close()
