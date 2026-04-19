from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncConnection
from sqlalchemy.sql.schema import Table  # noqa: TC002 — used for cast below

from agentlabx.db.schema import AppState, Base, UserToken
from agentlabx.db.session import DatabaseHandle

CURRENT_SCHEMA_VERSION = 4


class SchemaVersionMismatchError(Exception):
    """Raised when the stored schema version is newer than the code supports."""


@dataclass(frozen=True)
class Migration:
    from_version: int
    to_version: int
    name: str
    apply: Callable[[AsyncConnection], Awaitable[None]]


async def _migrate_v1_to_v2(conn: AsyncConnection) -> None:
    """Add `email` column to `users` with a unique index. Existing rows get a
    placeholder email derived from their id so the NOT NULL + UNIQUE invariants
    are satisfied; the owner should reset these via the `reset-passphrase` CLI
    or via admin user-management."""
    await conn.execute(text("ALTER TABLE users ADD COLUMN email VARCHAR(320)"))
    await conn.execute(
        text("UPDATE users SET email = id || '@migrated.local' WHERE email IS NULL OR email = ''")
    )
    await conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_users_email ON users (email)"))


async def _migrate_v2_to_v3(conn: AsyncConnection) -> None:
    """Create the `user_tokens` table. Uses the ORM model's own DDL so the
    migration cannot drift from the schema declaration."""
    tbl: Table = UserToken.__table__  # type: ignore[assignment]
    await conn.run_sync(lambda sync_conn: tbl.create(sync_conn, checkfirst=True))


async def _migrate_v3_to_v4(conn: AsyncConnection) -> None:
    """Drop the `revoked` column from `user_tokens` — tokens are now hard-deleted
    on revoke (GitHub model). Delete any currently-revoked rows first.

    The column may already be absent if v2→v3 ran against the current ORM model
    (which no longer declares `revoked`), so check before dropping.
    """
    columns = await conn.execute(text("PRAGMA table_info(user_tokens)"))
    col_names = [row[1] for row in columns]
    if "revoked" in col_names:
        await conn.execute(text("DELETE FROM user_tokens WHERE revoked = 1"))
        await conn.execute(text("ALTER TABLE user_tokens DROP COLUMN revoked"))


_MIGRATIONS: tuple[Migration, ...] = (
    Migration(from_version=1, to_version=2, name="add_email_column", apply=_migrate_v1_to_v2),
    Migration(from_version=2, to_version=3, name="add_user_tokens", apply=_migrate_v2_to_v3),
    Migration(from_version=3, to_version=4, name="drop_token_revoked", apply=_migrate_v3_to_v4),
)


async def apply_migrations(handle: DatabaseHandle) -> None:
    """Create tables + migrate the DB to `CURRENT_SCHEMA_VERSION`.

    - Fresh DB (no `schema_version` row) -> create_all + stamp current version.
    - Stored version < current -> apply each matching migration in order.
    - Stored version == current -> no-op.
    - Stored version > current -> raise `SchemaVersionMismatchError`.
    """
    # First-run path: try to read schema_version. If the row (or the table) is
    # missing, treat as fresh DB.
    async with handle.session() as session:
        try:
            stored = (
                await session.execute(select(AppState).where(AppState.key == "schema_version"))
            ).scalar_one_or_none()
            stored_version: int | None = int(stored.value) if stored is not None else None
        except Exception:
            stored_version = None

    if stored_version is None:
        # Fresh DB — create everything, record current version.
        async with handle.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with handle.session() as session:
            session.add(AppState(key="schema_version", value=str(CURRENT_SCHEMA_VERSION)))
            await session.commit()
        return

    if stored_version == CURRENT_SCHEMA_VERSION:
        return

    if stored_version > CURRENT_SCHEMA_VERSION:
        raise SchemaVersionMismatchError(
            f"database schema_version={stored_version} is newer than code "
            f"CURRENT_SCHEMA_VERSION={CURRENT_SCHEMA_VERSION}. Downgrades are "
            f"not supported; upgrade the AgentLabX package or restore an "
            f"older DB backup."
        )

    # stored_version < CURRENT_SCHEMA_VERSION — walk forward.
    current = stored_version
    while current < CURRENT_SCHEMA_VERSION:
        migration = next((m for m in _MIGRATIONS if m.from_version == current), None)
        if migration is None:
            raise SchemaVersionMismatchError(
                f"no migration registered from version {current} to "
                f"{current + 1}. Either restore a known-version backup or "
                f"extend _MIGRATIONS in agentlabx/db/migrations.py."
            )
        async with handle.engine.begin() as conn:
            await migration.apply(conn)
        async with handle.session() as session:
            row = (
                await session.execute(select(AppState).where(AppState.key == "schema_version"))
            ).scalar_one()
            row.value = str(migration.to_version)
            await session.commit()
        current = migration.to_version
