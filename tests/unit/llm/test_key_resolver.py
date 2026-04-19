from __future__ import annotations

from pathlib import Path

import pytest

from agentlabx.db.schema import Base, User, UserConfig
from agentlabx.db.session import DatabaseHandle
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
    db: DatabaseHandle, crypto: FernetStore, user_id: str, provider: str, value: str
) -> None:
    await _ensure_user(db, user_id)
    ciphertext = crypto.encrypt(value.encode("utf-8"))
    async with db.session() as session:
        session.add(
            UserConfig(user_id=user_id, slot=f"user:key:{provider}", ciphertext=ciphertext)
        )
        await session.commit()


@pytest.mark.asyncio
async def test_resolve_returns_decrypted_key(
    db: DatabaseHandle, crypto: FernetStore
) -> None:
    # "anthropic" is the provider name litellm.get_llm_provider returns for claude models
    await _store_credential(db, crypto, "user-1", "anthropic", "sk-test-secret")
    resolver = KeyResolver(db=db, crypto=crypto, local_providers=("ollama",))
    key = await resolver.resolve(user_id="user-1", model="claude-sonnet-4-6")
    assert key == "sk-test-secret"


@pytest.mark.asyncio
async def test_resolve_raises_when_no_credential(
    db: DatabaseHandle, crypto: FernetStore
) -> None:
    resolver = KeyResolver(db=db, crypto=crypto, local_providers=("ollama",))
    with pytest.raises(NoCredentialError, match="anthropic"):
        await resolver.resolve(user_id="user-1", model="claude-sonnet-4-6")


@pytest.mark.asyncio
async def test_resolve_returns_none_for_local_provider(
    db: DatabaseHandle, crypto: FernetStore
) -> None:
    """Local providers (e.g. ollama) need no key."""
    resolver = KeyResolver(db=db, crypto=crypto, local_providers=("ollama",))
    key = await resolver.resolve(user_id="user-1", model="ollama/llama3")
    assert key is None


@pytest.mark.asyncio
async def test_resolve_isolates_users(
    db: DatabaseHandle, crypto: FernetStore
) -> None:
    await _store_credential(db, crypto, "user-A", "anthropic", "key-A")
    await _store_credential(db, crypto, "user-B", "anthropic", "key-B")
    resolver = KeyResolver(db=db, crypto=crypto, local_providers=("ollama",))
    assert await resolver.resolve(user_id="user-A", model="claude-sonnet-4-6") == "key-A"
    assert await resolver.resolve(user_id="user-B", model="claude-sonnet-4-6") == "key-B"
