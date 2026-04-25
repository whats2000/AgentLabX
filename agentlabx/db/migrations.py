from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncConnection
from sqlalchemy.sql.schema import Table  # noqa: TC002 — used for cast below

from agentlabx.db.schema import AppState, Base, UserToken
from agentlabx.db.session import DatabaseHandle

CURRENT_SCHEMA_VERSION = 6


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


async def _migrate_v4_to_v5(conn: AsyncConnection) -> None:
    """Add the three Stage A3 tables: ``admin_configs`` (admin-scope credential
    slots, used by ``SlotResolver``), ``mcp_servers`` (MCP server registry,
    Task 4) and ``memory_entries`` (built-in memory server, Task 8).

    Bundling all three into a single migration keeps the DB at one consistent
    version after an A3 boot. DDL is raw SQL with ``IF NOT EXISTS`` guards so
    re-running the migration is a no-op (mirrors the v3→v4 precedent which
    checked ``PRAGMA table_info`` before mutating).
    """
    existing = await conn.execute(
        text("SELECT name FROM sqlite_master WHERE type IN ('table', 'index')")
    )
    present: set[str] = {row[0] for row in existing}

    if "admin_configs" not in present:
        await conn.execute(
            text(
                """
                CREATE TABLE admin_configs (
                    slot VARCHAR(128) PRIMARY KEY,
                    ciphertext BLOB NOT NULL,
                    created_at DATETIME NOT NULL
                )
                """
            )
        )

    if "mcp_servers" not in present:
        await conn.execute(
            text(
                """
                CREATE TABLE mcp_servers (
                    id VARCHAR(36) PRIMARY KEY,
                    owner_id VARCHAR(36) REFERENCES users(id) ON DELETE CASCADE,
                    name VARCHAR(128) NOT NULL,
                    scope VARCHAR(16) NOT NULL,
                    transport VARCHAR(16) NOT NULL,
                    command_json TEXT,
                    url VARCHAR(2048),
                    inprocess_key VARCHAR(128),
                    env_slot_refs_json TEXT NOT NULL,
                    declared_capabilities_json TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at DATETIME NOT NULL,
                    CONSTRAINT uq_mcp_servers_scope_owner_name
                        UNIQUE (scope, owner_id, name)
                )
                """
            )
        )
    if "idx_mcp_servers_owner" not in present:
        await conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_mcp_servers_owner "
                "ON mcp_servers (owner_id, enabled)"
            )
        )

    if "memory_entries" not in present:
        await conn.execute(
            text(
                """
                CREATE TABLE memory_entries (
                    id VARCHAR(36) PRIMARY KEY,
                    category VARCHAR(128) NOT NULL,
                    body TEXT NOT NULL,
                    source_run_id VARCHAR(36),
                    created_by VARCHAR(36) REFERENCES users(id) ON DELETE SET NULL,
                    created_at DATETIME NOT NULL
                )
                """
            )
        )
    if "idx_memory_entries_category" not in present:
        await conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_memory_entries_category "
                "ON memory_entries (category)"
            )
        )


async def _migrate_v5_to_v6(conn: AsyncConnection) -> None:
    """Add ``slot_env_overrides_json`` to ``mcp_servers``.

    Bundles whose upstream subprocess reads its API key from a fixed env-var
    name (e.g. ``SEMANTIC_SCHOLAR_API_KEY``) need to override the host's
    default ``AGENTLABX_SLOT_<UPPER>`` mapping per-slot. Stored as a JSON
    list of ``[slot_ref, env_var]`` pairs so the column is forward-compatible
    with future per-bundle policy fields. Pre-existing rows default to
    ``'[]'`` (no overrides) so the migration is non-breaking.
    """
    cols = await conn.execute(text("PRAGMA table_info(mcp_servers)"))
    present_cols: set[str] = {row[1] for row in cols}
    if "slot_env_overrides_json" not in present_cols:
        await conn.execute(
            text(
                "ALTER TABLE mcp_servers ADD COLUMN "
                "slot_env_overrides_json TEXT NOT NULL DEFAULT '[]'"
            )
        )


_MIGRATIONS: tuple[Migration, ...] = (
    Migration(from_version=1, to_version=2, name="add_email_column", apply=_migrate_v1_to_v2),
    Migration(from_version=2, to_version=3, name="add_user_tokens", apply=_migrate_v2_to_v3),
    Migration(from_version=3, to_version=4, name="drop_token_revoked", apply=_migrate_v3_to_v4),
    Migration(from_version=4, to_version=5, name="add_a3_tables", apply=_migrate_v4_to_v5),
    Migration(
        from_version=5,
        to_version=6,
        name="add_slot_env_overrides",
        apply=_migrate_v5_to_v6,
    ),
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
