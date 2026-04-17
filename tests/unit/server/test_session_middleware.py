from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from agentlabx.auth.default import DefaultAuther
from agentlabx.auth.protocol import Identity
from agentlabx.db.migrations import apply_migrations
from agentlabx.db.schema import Session as SessionRow
from agentlabx.db.session import DatabaseHandle
from agentlabx.server.dependencies import current_identity, require_admin
from agentlabx.server.middleware import SessionConfig, install_session_middleware


@pytest.mark.asyncio
async def test_authenticated_request_sees_identity(tmp_workspace: Path) -> None:
    handle = DatabaseHandle(tmp_workspace / "t.db")
    await handle.connect()
    try:
        await apply_migrations(handle)
        default = DefaultAuther(handle)
        identity = await default.register(
            display_name="A", email="a@example.com", passphrase="p1234567"
        )

        app = FastAPI()
        cfg = SessionConfig(secret=b"x" * 48, secure=False)
        install_session_middleware(app, cfg=cfg, db=handle)

        @app.get("/whoami")
        async def whoami(who: Identity = Depends(current_identity)) -> dict[str, str]:
            return {"id": who.id}

        # create a session row and mint a signed cookie matching it
        session_id = "s1"
        async with handle.session() as session:
            session.add(
                SessionRow(
                    id=session_id,
                    user_id=identity.id,
                    expires_at=datetime.now(tz=timezone.utc) + timedelta(hours=1),
                )
            )
            await session.commit()

        from itsdangerous import URLSafeTimedSerializer

        cookie = URLSafeTimedSerializer(cfg.secret).dumps({"sid": session_id})

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/whoami", cookies={"agentlabx_session": cookie})
            assert response.status_code == 200
            assert response.json() == {"id": identity.id}
    finally:
        await handle.close()


@pytest.mark.asyncio
async def test_unauthenticated_request_returns_401(tmp_workspace: Path) -> None:
    handle = DatabaseHandle(tmp_workspace / "t.db")
    await handle.connect()
    try:
        await apply_migrations(handle)
        app = FastAPI()
        cfg = SessionConfig(secret=b"x" * 48, secure=False)
        install_session_middleware(app, cfg=cfg, db=handle)

        @app.get("/whoami")
        async def whoami(who: Identity = Depends(current_identity)) -> dict[str, str]:
            return {"id": who.id}

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/whoami")
            assert response.status_code == 401
    finally:
        await handle.close()


@pytest.mark.asyncio
async def test_require_admin_rejects_non_admin(tmp_workspace: Path) -> None:
    handle = DatabaseHandle(tmp_workspace / "t.db")
    await handle.connect()
    try:
        await apply_migrations(handle)
        default = DefaultAuther(handle)
        admin = await default.register(
            display_name="Admin", email="admin@example.com", passphrase="p1234567"
        )
        normal = await default.register(
            display_name="Normal", email="normal@example.com", passphrase="p1234567"
        )
        assert "admin" in admin.capabilities
        assert "admin" not in normal.capabilities

        app = FastAPI()
        cfg = SessionConfig(secret=b"x" * 48, secure=False)
        install_session_middleware(app, cfg=cfg, db=handle)

        @app.get("/admin-only")
        async def admin_only(_: Identity = Depends(require_admin)) -> dict[str, bool]:
            return {"ok": True}

        from itsdangerous import URLSafeTimedSerializer

        async with handle.session() as session:
            session.add(
                SessionRow(
                    id="s_normal",
                    user_id=normal.id,
                    expires_at=datetime.now(tz=timezone.utc) + timedelta(hours=1),
                )
            )
            await session.commit()

        cookie = URLSafeTimedSerializer(cfg.secret).dumps({"sid": "s_normal"})
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/admin-only", cookies={"agentlabx_session": cookie})
            assert response.status_code == 403
    finally:
        await handle.close()


@pytest.mark.asyncio
async def test_expired_normal_cookie_rejected_but_remember_me_accepted(
    tmp_workspace: Path,
) -> None:
    """C1 fix: itsdangerous rejects a normal cookie after max_age_seconds,
    but a remember-me cookie remains valid within remember_me_max_age_seconds."""
    handle = DatabaseHandle(tmp_workspace / "t.db")
    await handle.connect()
    try:
        await apply_migrations(handle)
        default = DefaultAuther(handle)
        identity = await default.register(
            display_name="A", email="a@example.com", passphrase="p1234567"
        )

        # Use a very short normal max_age (1s) so the cookie expires quickly,
        # but a long remember_me window (3600s).
        app = FastAPI()
        cfg = SessionConfig(
            secret=b"x" * 48,
            secure=False,
            max_age_seconds=1,
            remember_me_max_age_seconds=3600,
        )
        install_session_middleware(app, cfg=cfg, db=handle)

        @app.get("/whoami")
        async def whoami(who: Identity = Depends(current_identity)) -> dict[str, str]:
            return {"id": who.id}

        from itsdangerous import URLSafeTimedSerializer

        serializer = URLSafeTimedSerializer(cfg.secret)

        # Create two sessions: one normal, one remember-me
        async with handle.session() as session:
            session.add(
                SessionRow(
                    id="s_normal",
                    user_id=identity.id,
                    expires_at=datetime.now(tz=timezone.utc) + timedelta(hours=1),
                )
            )
            session.add(
                SessionRow(
                    id="s_remember",
                    user_id=identity.id,
                    expires_at=datetime.now(tz=timezone.utc) + timedelta(days=30),
                )
            )
            await session.commit()

        # Mint cookies — normal (rm=false) and remember-me (rm=true)
        normal_cookie = serializer.dumps({"sid": "s_normal", "rm": False})
        rm_cookie = serializer.dumps({"sid": "s_remember", "rm": True})

        # Wait for the normal cookie to expire at the itsdangerous level
        await asyncio.sleep(1.5)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            # Normal cookie should be rejected (itsdangerous max_age=1s expired)
            r = await client.get("/whoami", cookies={"agentlabx_session": normal_cookie})
            assert r.status_code == 401

            # Remember-me cookie should still work
            r = await client.get("/whoami", cookies={"agentlabx_session": rm_cookie})
            assert r.status_code == 200
            assert r.json()["id"] == identity.id
    finally:
        await handle.close()
