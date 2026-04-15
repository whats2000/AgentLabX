from __future__ import annotations

from pathlib import Path

import pytest

from agentlabx.auth.default import DefaultAuther
from agentlabx.auth.protocol import AuthError
from agentlabx.db.migrations import apply_migrations
from agentlabx.db.session import DatabaseHandle


@pytest.mark.asyncio
async def test_register_and_authenticate_roundtrip(tmp_workspace: Path) -> None:
    handle = DatabaseHandle(tmp_workspace / "t.db")
    await handle.connect()
    try:
        await apply_migrations(handle)
        auther = DefaultAuther(handle)
        identity = await auther.register(
            display_name="Alice", passphrase="correct horse"
        )
        authed = await auther.authenticate(
            {"identity_id": identity.id, "passphrase": "correct horse"}
        )
        assert authed.id == identity.id
    finally:
        await handle.close()


@pytest.mark.asyncio
async def test_authenticate_wrong_passphrase_raises(tmp_workspace: Path) -> None:
    handle = DatabaseHandle(tmp_workspace / "t.db")
    await handle.connect()
    try:
        await apply_migrations(handle)
        auther = DefaultAuther(handle)
        identity = await auther.register(display_name="Bob", passphrase="right")
        with pytest.raises(AuthError):
            await auther.authenticate(
                {"identity_id": identity.id, "passphrase": "wrong"}
            )
    finally:
        await handle.close()


@pytest.mark.asyncio
async def test_first_registered_is_admin(tmp_workspace: Path) -> None:
    handle = DatabaseHandle(tmp_workspace / "t.db")
    await handle.connect()
    try:
        await apply_migrations(handle)
        auther = DefaultAuther(handle)
        first = await auther.register(display_name="Admin", passphrase="p")
        second = await auther.register(display_name="User", passphrase="q")
        assert "admin" in first.capabilities
        assert "admin" not in second.capabilities
    finally:
        await handle.close()
