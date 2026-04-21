from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text

from agentlabx.db.schema import Base, User, UserConfig
from agentlabx.db.session import DatabaseHandle
from agentlabx.security.fernet_store import FernetStore
from agentlabx.security.slot_resolver import SlotResolver

if TYPE_CHECKING:
    from _pytest.monkeypatch import MonkeyPatch


@pytest.fixture()
async def db(tmp_path: Path) -> DatabaseHandle:
    handle = DatabaseHandle(tmp_path / "test.db")
    await handle.connect()
    async with handle.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return handle


@pytest.fixture()
def crypto(ephemeral_keyring: dict[tuple[str, str], str]) -> FernetStore:
    return FernetStore.from_keyring()


async def _ensure_user(db: DatabaseHandle, user_id: str) -> None:
    async with db.session() as session:
        existing = await session.get(User, user_id)
        if existing is None:
            session.add(
                User(
                    id=user_id,
                    display_name=user_id,
                    email=f"{user_id}@example.com",
                    auther_name="test",
                )
            )
            await session.commit()


async def _store_user_credential(
    db: DatabaseHandle, crypto: FernetStore, *, user_id: str, slot: str, value: str
) -> None:
    await _ensure_user(db, user_id)
    ciphertext = crypto.encrypt(value.encode("utf-8"))
    async with db.session() as session:
        session.add(UserConfig(user_id=user_id, slot=slot, ciphertext=ciphertext))
        await session.commit()


def _make_resolver(db: DatabaseHandle, crypto: FernetStore) -> SlotResolver:
    # DatabaseHandle.session() yields sessions from its private sessionmaker;
    # the resolver needs the raw factory. Reach in via the tested API:
    from sqlalchemy.ext.asyncio import async_sessionmaker

    factory = async_sessionmaker(db.engine, expire_on_commit=False)
    return SlotResolver(crypto, factory)


@pytest.mark.asyncio
async def test_user_scope_returns_decrypted_value(db: DatabaseHandle, crypto: FernetStore) -> None:
    await _store_user_credential(
        db, crypto, user_id="u1", slot="user:key:anthropic", value="sk-secret"
    )
    resolver = _make_resolver(db, crypto)
    assert await resolver.resolve(owner_id="u1", slot="user:key:anthropic") == "sk-secret"


@pytest.mark.asyncio
async def test_user_scope_returns_none_when_slot_missing(
    db: DatabaseHandle, crypto: FernetStore
) -> None:
    await _ensure_user(db, "u1")
    resolver = _make_resolver(db, crypto)
    assert await resolver.resolve(owner_id="u1", slot="user:key:nope") is None


@pytest.mark.asyncio
async def test_user_scope_isolates_users(db: DatabaseHandle, crypto: FernetStore) -> None:
    await _store_user_credential(db, crypto, user_id="uA", slot="user:key:anthropic", value="key-A")
    await _store_user_credential(db, crypto, user_id="uB", slot="user:key:anthropic", value="key-B")
    resolver = _make_resolver(db, crypto)
    assert await resolver.resolve(owner_id="uA", slot="user:key:anthropic") == "key-A"
    assert await resolver.resolve(owner_id="uB", slot="user:key:anthropic") == "key-B"


@pytest.mark.asyncio
async def test_admin_scope_falls_back_to_env_when_admin_table_absent(
    db: DatabaseHandle, crypto: FernetStore, monkeypatch: MonkeyPatch
) -> None:
    """admin_configs table is added by Task 3; until then admin scope reads env."""
    monkeypatch.setenv("AGENTLABX_SLOT_FILESYSTEM_ROOT", "/tmp/agentlabx-test")
    resolver = _make_resolver(db, crypto)
    value = await resolver.resolve(owner_id=None, slot="filesystem_root")
    assert value == "/tmp/agentlabx-test"


@pytest.mark.asyncio
async def test_admin_scope_returns_none_when_no_source_set(
    db: DatabaseHandle, crypto: FernetStore, monkeypatch: MonkeyPatch
) -> None:
    monkeypatch.delenv("AGENTLABX_SLOT_NEVER_SET", raising=False)
    resolver = _make_resolver(db, crypto)
    assert await resolver.resolve(owner_id=None, slot="never_set") is None


@pytest.mark.asyncio
async def test_admin_scope_prefers_admin_configs_row_over_env(
    db: DatabaseHandle, crypto: FernetStore, monkeypatch: MonkeyPatch
) -> None:
    """Once Task 3 lands the admin_configs table the resolver picks it up
    automatically. Simulate that future state by creating the table by hand."""
    ciphertext = crypto.encrypt(b"db-value")
    async with db.engine.begin() as conn:
        await conn.execute(
            text(
                "CREATE TABLE admin_configs ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "slot TEXT NOT NULL UNIQUE, "
                "ciphertext BLOB NOT NULL"
                ")"
            )
        )
        await conn.execute(
            text("INSERT INTO admin_configs (slot, ciphertext) VALUES (:slot, :ct)"),
            {"slot": "shared_key", "ct": ciphertext},
        )

    monkeypatch.setenv("AGENTLABX_SLOT_SHARED_KEY", "env-value")
    resolver = _make_resolver(db, crypto)
    assert await resolver.resolve(owner_id=None, slot="shared_key") == "db-value"
