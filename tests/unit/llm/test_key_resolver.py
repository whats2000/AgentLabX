from __future__ import annotations

from pathlib import Path

import pytest

from agentlabx.db.schema import Base, User, UserConfig
from agentlabx.db.session import DatabaseHandle
from agentlabx.llm.catalog import ModelEntry, ProviderCatalog, ProviderEntry
from agentlabx.llm.key_resolver import KeyResolver, NoCredentialError
from agentlabx.security.fernet_store import FernetStore

# Re-use A1 ephemeral_keyring fixture from conftest.py


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


@pytest.fixture()
def catalog() -> ProviderCatalog:
    return ProviderCatalog(
        providers=[
            ProviderEntry(
                name="provider-a",
                display_name="Provider A",
                env_var="PROVIDER_A_KEY",
                credential_slot="provider-a",
                models=[ModelEntry(id="provider-a/model-1", display_name="Model 1")],
            ),
            ProviderEntry(
                name="local-provider",
                display_name="Local Provider",
                env_var="",
                credential_slot="",
                models=[ModelEntry(id="local-provider/model-1", display_name="Local Model")],
            ),
        ]
    )


async def _ensure_user(db: DatabaseHandle, user_id: str) -> None:
    """Insert a minimal User row if it does not already exist."""
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


async def _store_credential(
    db: DatabaseHandle, crypto: FernetStore, user_id: str, slot: str, value: str
) -> None:
    await _ensure_user(db, user_id)
    ciphertext = crypto.encrypt(value.encode("utf-8"))
    async with db.session() as session:
        session.add(UserConfig(user_id=user_id, slot=f"user:key:{slot}", ciphertext=ciphertext))
        await session.commit()


@pytest.mark.asyncio
async def test_resolve_returns_decrypted_key(
    db: DatabaseHandle, crypto: FernetStore, catalog: ProviderCatalog
) -> None:
    await _store_credential(db, crypto, "user-1", "provider-a", "sk-test-secret")
    resolver = KeyResolver(db=db, crypto=crypto, catalog=catalog)
    key = await resolver.resolve(user_id="user-1", model="provider-a/model-1")
    assert key == "sk-test-secret"


@pytest.mark.asyncio
async def test_resolve_raises_when_no_credential(
    db: DatabaseHandle, crypto: FernetStore, catalog: ProviderCatalog
) -> None:
    resolver = KeyResolver(db=db, crypto=crypto, catalog=catalog)
    with pytest.raises(NoCredentialError, match="provider-a"):
        await resolver.resolve(user_id="user-1", model="provider-a/model-1")


@pytest.mark.asyncio
async def test_resolve_returns_none_for_no_credential_slot(
    db: DatabaseHandle, crypto: FernetStore, catalog: ProviderCatalog
) -> None:
    """Providers with empty credential_slot (e.g. local) need no key."""
    resolver = KeyResolver(db=db, crypto=crypto, catalog=catalog)
    key = await resolver.resolve(user_id="user-1", model="local-provider/model-1")
    assert key is None


@pytest.mark.asyncio
async def test_resolve_isolates_users(
    db: DatabaseHandle, crypto: FernetStore, catalog: ProviderCatalog
) -> None:
    await _store_credential(db, crypto, "user-A", "provider-a", "key-A")
    await _store_credential(db, crypto, "user-B", "provider-a", "key-B")
    resolver = KeyResolver(db=db, crypto=crypto, catalog=catalog)
    assert await resolver.resolve(user_id="user-A", model="provider-a/model-1") == "key-A"
    assert await resolver.resolve(user_id="user-B", model="provider-a/model-1") == "key-B"
