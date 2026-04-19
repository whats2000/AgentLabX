from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import text

from agentlabx.db.migrations import apply_migrations
from agentlabx.db.schema import Capability, Session, User, UserConfig, UserToken
from agentlabx.db.session import DatabaseHandle


@pytest.mark.asyncio
async def test_delete_user_cascades_to_child_rows(tmp_workspace: Path) -> None:
    """I5: FK cascades work because PRAGMA foreign_keys=ON is set on every connection."""
    handle = DatabaseHandle(tmp_workspace / "t.db")
    await handle.connect()
    try:
        await apply_migrations(handle)

        user_id = "test-user-cascade-001"
        now = datetime.now(tz=timezone.utc)

        async with handle.session() as session:
            session.add(
                User(
                    id=user_id,
                    display_name="Cascade User",
                    email="cascade@example.com",
                    auther_name="default",
                )
            )
            session.add(
                UserConfig(
                    user_id=user_id,
                    slot="test:slot",
                    ciphertext=b"fakehash",
                )
            )
            session.add(
                UserToken(
                    id="tok-001",
                    user_id=user_id,
                    token_hash="a" * 64,
                    label="ci",
                )
            )
            session.add(
                Session(
                    id="sess-001",
                    user_id=user_id,
                    expires_at=now + timedelta(hours=1),
                )
            )
            session.add(
                Capability(
                    user_id=user_id,
                    capability="admin",
                )
            )
            await session.commit()

        # Delete user via raw SQL (bypasses ORM cascade logic — exercises the PRAGMA).
        async with handle.engine.begin() as conn:
            await conn.execute(text(f"DELETE FROM users WHERE id = '{user_id}'"))

        # All FK-bound child rows must be gone.
        async with handle.session() as session:
            from sqlalchemy import select

            configs = (
                (await session.execute(select(UserConfig).where(UserConfig.user_id == user_id)))
                .scalars()
                .all()
            )
            assert configs == [], f"user_configs not cascade-deleted: {configs}"

            tokens = (
                (await session.execute(select(UserToken).where(UserToken.user_id == user_id)))
                .scalars()
                .all()
            )
            assert tokens == [], f"user_tokens not cascade-deleted: {tokens}"

            sessions = (
                (await session.execute(select(Session).where(Session.user_id == user_id)))
                .scalars()
                .all()
            )
            assert sessions == [], f"sessions not cascade-deleted: {sessions}"

            caps = (
                (await session.execute(select(Capability).where(Capability.user_id == user_id)))
                .scalars()
                .all()
            )
            assert caps == [], f"capabilities not cascade-deleted: {caps}"
    finally:
        await handle.close()
