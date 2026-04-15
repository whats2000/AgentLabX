from __future__ import annotations

from pathlib import Path

import pytest

from agentlabx.auth.default import DefaultAuther
from agentlabx.auth.protocol import AuthError, EmailAlreadyRegisteredError
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
            display_name="Alice", email="alice@example.com", passphrase="hunter2xy"
        )
        assert identity.email == "alice@example.com"
        authed = await auther.authenticate(
            {"email": "alice@example.com", "passphrase": "hunter2xy"}
        )
        assert authed.id == identity.id
        assert authed.email == "alice@example.com"
    finally:
        await handle.close()


@pytest.mark.asyncio
async def test_authenticate_wrong_passphrase_raises(tmp_workspace: Path) -> None:
    handle = DatabaseHandle(tmp_workspace / "t.db")
    await handle.connect()
    try:
        await apply_migrations(handle)
        auther = DefaultAuther(handle)
        await auther.register(
            display_name="Bob", email="bob@example.com", passphrase="right1234"
        )
        with pytest.raises(AuthError):
            await auther.authenticate(
                {"email": "bob@example.com", "passphrase": "wrong"}
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
        first = await auther.register(
            display_name="Admin", email="admin@example.com", passphrase="p1234567"
        )
        second = await auther.register(
            display_name="User", email="user@example.com", passphrase="q1234567"
        )
        assert "admin" in first.capabilities
        assert "admin" not in second.capabilities
    finally:
        await handle.close()


@pytest.mark.asyncio
async def test_email_is_unique(tmp_workspace: Path) -> None:
    handle = DatabaseHandle(tmp_workspace / "t.db")
    await handle.connect()
    try:
        await apply_migrations(handle)
        auther = DefaultAuther(handle)
        await auther.register(display_name="A", email="same@example.com", passphrase="p1234567")
        with pytest.raises(EmailAlreadyRegisteredError):
            await auther.register(display_name="B", email="same@example.com", passphrase="p1234567")
    finally:
        await handle.close()


@pytest.mark.asyncio
async def test_email_normalization_is_canonical(tmp_workspace: Path) -> None:
    handle = DatabaseHandle(tmp_workspace / "t.db")
    await handle.connect()
    try:
        await apply_migrations(handle)
        auther = DefaultAuther(handle)
        await auther.register(display_name="A", email="same@example.com", passphrase="p1234567")
        with pytest.raises(EmailAlreadyRegisteredError):
            await auther.register(
                display_name="B", email="  SAME@Example.com  ", passphrase="p1234567"
            )
        # And login with any case/whitespace works against the canonical row:
        ident = await auther.authenticate(
            {"email": "  Same@Example.COM  ", "passphrase": "p1234567"}
        )
        assert ident.email == "same@example.com"
    finally:
        await handle.close()
