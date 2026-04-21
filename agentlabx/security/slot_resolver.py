"""Slot-aware credential resolver.

Where ``agentlabx.llm.key_resolver.KeyResolver`` is *model-aware* (it asks
LiteLLM which provider owns a model and looks up the user's key for that
provider), ``SlotResolver`` is *slot-aware*: callers pass a slot name directly,
and the resolver decrypts whichever ciphertext is currently bound to it.

It supports both user scope (``owner_id`` is a user UUID) and admin scope
(``owner_id is None``). For admin scope it walks a fixed precedence:

1. The ``admin_configs`` row for the slot (table created by Stage A3 task 3 —
   tolerated as absent here so Task 3 can introduce it).
2. The OS process environment variable ``AGENTLABX_SLOT_<SLOT_UPPER>``.

Returns ``None`` when the slot has no value in any source.
"""

from __future__ import annotations

import os

from sqlalchemy import select, text
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentlabx.db.schema import UserConfig
from agentlabx.security.fernet_store import FernetStore

# SQL kept at module scope so we don't pay the ``text(...)`` cost per call.
# Raw SQL is used because the ``admin_configs`` ORM model is added by Stage A3
# Task 3; we tolerate the table being absent until then.
_ADMIN_LOOKUP_SQL = text("SELECT ciphertext FROM admin_configs WHERE slot = :slot")


class SlotResolver:
    """Resolve a named credential slot to a plaintext string, or ``None`` if unset.

    Construction takes a ``FernetStore`` (for ciphertext decryption) and an
    ``async_sessionmaker`` (so the resolver does not need the full
    ``DatabaseHandle`` and can be reused in non-FastAPI call sites such as
    background MCP launches).
    """

    def __init__(
        self,
        fernet_store: FernetStore,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._crypto = fernet_store
        self._sessionmaker = session_factory

    async def resolve(self, *, owner_id: str | None, slot: str) -> str | None:
        """Return the plaintext value for ``slot``, or ``None`` if unset.

        ``owner_id is None`` selects admin scope, which falls back to the
        ``AGENTLABX_SLOT_<SLOT_UPPER>`` environment variable if no
        ``admin_configs`` row exists (or if the table itself is absent).
        """
        if owner_id is not None:
            return await self._resolve_user(owner_id=owner_id, slot=slot)
        return await self._resolve_admin(slot=slot)

    async def _resolve_user(self, *, owner_id: str, slot: str) -> str | None:
        async with self._sessionmaker() as session:
            row = (
                await session.execute(
                    select(UserConfig).where(
                        UserConfig.user_id == owner_id,
                        UserConfig.slot == slot,
                    )
                )
            ).scalar_one_or_none()
        if row is None:
            return None
        return self._crypto.decrypt(row.ciphertext).decode("utf-8")

    async def _resolve_admin(self, *, slot: str) -> str | None:
        ciphertext = await self._lookup_admin_ciphertext(slot)
        if ciphertext is not None:
            return self._crypto.decrypt(ciphertext).decode("utf-8")
        env_name = f"AGENTLABX_SLOT_{slot.upper()}"
        return os.environ.get(env_name)

    async def _lookup_admin_ciphertext(self, slot: str) -> bytes | None:
        """Look up an ``admin_configs`` row, tolerating the table being absent.

        Stage A3 Task 3 introduces the ``admin_configs`` migration. Until then
        SQLite raises ``OperationalError("no such table")`` (other backends
        raise ``ProgrammingError``); we treat both as "no admin row" and let
        the caller fall through to the env-var path.
        """
        try:
            async with self._sessionmaker() as session:
                result = await session.execute(_ADMIN_LOOKUP_SQL, {"slot": slot})
                row = result.first()
        except (OperationalError, ProgrammingError):
            return None
        if row is None:
            return None
        ciphertext = row[0]
        if not isinstance(ciphertext, bytes | bytearray | memoryview):
            return None
        return bytes(ciphertext)
