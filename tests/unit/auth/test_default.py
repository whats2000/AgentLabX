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
        await auther.register(display_name="Bob", email="bob@example.com", passphrase="right1234")
        with pytest.raises(AuthError):
            await auther.authenticate({"email": "bob@example.com", "passphrase": "wrong"})
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


@pytest.mark.asyncio
async def test_update_display_name(tmp_workspace: Path) -> None:
    handle = DatabaseHandle(tmp_workspace / "t.db")
    await handle.connect()
    try:
        await apply_migrations(handle)
        a = DefaultAuther(handle)
        ident = await a.register(display_name="Alice", email="a@x.com", passphrase="p1234567")
        updated = await a.update_display_name(identity_id=ident.id, new_display_name="Alice II")
        assert updated.display_name == "Alice II"
    finally:
        await handle.close()


@pytest.mark.asyncio
async def test_update_email_with_correct_passphrase(tmp_workspace: Path) -> None:
    handle = DatabaseHandle(tmp_workspace / "t.db")
    await handle.connect()
    try:
        await apply_migrations(handle)
        a = DefaultAuther(handle)
        ident = await a.register(display_name="A", email="old@x.com", passphrase="p1234567")
        updated = await a.update_email(
            identity_id=ident.id, new_email="new@x.com", passphrase="p1234567"
        )
        assert updated.email == "new@x.com"
        # login with new email works, old email fails
        logged = await a.authenticate({"email": "new@x.com", "passphrase": "p1234567"})
        assert logged.id == ident.id
        with pytest.raises(AuthError):
            await a.authenticate({"email": "old@x.com", "passphrase": "p1234567"})
    finally:
        await handle.close()


@pytest.mark.asyncio
async def test_update_email_with_wrong_passphrase_raises(tmp_workspace: Path) -> None:
    handle = DatabaseHandle(tmp_workspace / "t.db")
    await handle.connect()
    try:
        await apply_migrations(handle)
        a = DefaultAuther(handle)
        ident = await a.register(display_name="A", email="a@x.com", passphrase="right1234")
        with pytest.raises(AuthError):
            await a.update_email(
                identity_id=ident.id, new_email="new@x.com", passphrase="wrong1234"
            )
    finally:
        await handle.close()


@pytest.mark.asyncio
async def test_update_email_to_existing_raises_conflict(tmp_workspace: Path) -> None:
    handle = DatabaseHandle(tmp_workspace / "t.db")
    await handle.connect()
    try:
        await apply_migrations(handle)
        a = DefaultAuther(handle)
        ident_a = await a.register(display_name="A", email="a@x.com", passphrase="p1234567")
        await a.register(display_name="B", email="b@x.com", passphrase="p1234567")
        with pytest.raises(EmailAlreadyRegisteredError):
            await a.update_email(identity_id=ident_a.id, new_email="b@x.com", passphrase="p1234567")
    finally:
        await handle.close()


@pytest.mark.asyncio
async def test_update_passphrase_rotates_credential(tmp_workspace: Path) -> None:
    handle = DatabaseHandle(tmp_workspace / "t.db")
    await handle.connect()
    try:
        await apply_migrations(handle)
        a = DefaultAuther(handle)
        ident = await a.register(display_name="A", email="a@x.com", passphrase="old123456")
        await a.update_passphrase(
            identity_id=ident.id, old_passphrase="old123456", new_passphrase="new123456"
        )
        # new works
        logged = await a.authenticate({"email": "a@x.com", "passphrase": "new123456"})
        assert logged.id == ident.id
        # old fails
        with pytest.raises(AuthError):
            await a.authenticate({"email": "a@x.com", "passphrase": "old123456"})
    finally:
        await handle.close()


@pytest.mark.asyncio
async def test_update_passphrase_wrong_old_raises(tmp_workspace: Path) -> None:
    handle = DatabaseHandle(tmp_workspace / "t.db")
    await handle.connect()
    try:
        await apply_migrations(handle)
        a = DefaultAuther(handle)
        ident = await a.register(display_name="A", email="a@x.com", passphrase="right1234")
        with pytest.raises(AuthError):
            await a.update_passphrase(
                identity_id=ident.id, old_passphrase="wrong1234", new_passphrase="whatever1"
            )
    finally:
        await handle.close()


@pytest.mark.asyncio
async def test_first_registered_gets_owner_and_admin(tmp_workspace: Path) -> None:
    handle = DatabaseHandle(tmp_workspace / "t.db")
    await handle.connect()
    try:
        await apply_migrations(handle)
        a = DefaultAuther(handle)
        first = await a.register(display_name="O", email="o@x.com", passphrase="p1234567")
        second = await a.register(display_name="U", email="u@x.com", passphrase="p1234567")
        assert "admin" in first.capabilities
        assert "owner" in first.capabilities
        assert "admin" not in second.capabilities
        assert "owner" not in second.capabilities
    finally:
        await handle.close()


@pytest.mark.asyncio
async def test_reset_passphrase_by_email(tmp_workspace: Path) -> None:
    from agentlabx.auth.default import reset_passphrase_by_email

    handle = DatabaseHandle(tmp_workspace / "t.db")
    await handle.connect()
    try:
        await apply_migrations(handle)
        a = DefaultAuther(handle)
        ident = await a.register(display_name="O", email="o@x.com", passphrase="old123456")
        updated = await reset_passphrase_by_email(
            handle, email="O@X.com  ", new_passphrase="new123456"
        )
        assert updated.id == ident.id
        with pytest.raises(AuthError):
            await a.authenticate({"email": "o@x.com", "passphrase": "old123456"})
        authed = await a.authenticate({"email": "o@x.com", "passphrase": "new123456"})
        assert authed.id == ident.id
    finally:
        await handle.close()


@pytest.mark.asyncio
async def test_reset_passphrase_revokes_sessions_and_tokens(tmp_workspace: Path) -> None:
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import select

    from agentlabx.auth.default import reset_passphrase_by_email
    from agentlabx.auth.token import TokenAuther
    from agentlabx.db.schema import Session as SessionRow

    handle = DatabaseHandle(tmp_workspace / "t.db")
    await handle.connect()
    try:
        await apply_migrations(handle)
        a = DefaultAuther(handle)
        ident = await a.register(display_name="O", email="o@x.com", passphrase="old123456")
        async with handle.session() as session:
            session.add(
                SessionRow(
                    id="s_test",
                    user_id=ident.id,
                    expires_at=datetime.now(tz=timezone.utc) + timedelta(hours=1),
                )
            )
            await session.commit()
        ta = TokenAuther(handle)
        issued = await ta.issue(identity_id=ident.id, label="t1")
        await reset_passphrase_by_email(handle, email="o@x.com", new_passphrase="new123456")
        async with handle.session() as session:
            row = (
                await session.execute(select(SessionRow).where(SessionRow.id == "s_test"))
            ).scalar_one()
            assert row.revoked is True
        with pytest.raises(AuthError):
            await ta.authenticate({"token": issued.token})
    finally:
        await handle.close()
