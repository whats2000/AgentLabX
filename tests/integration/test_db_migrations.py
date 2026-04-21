"""Integration tests for the v4→v5 schema migration (Stage A3 Task 3).

The unit suite at ``tests/unit/db/test_migrations.py`` covers the migration
framework itself (fresh-DB stamping, idempotency, downgrade rejection, and the
v1→v3 paths). This module focuses on the new tables introduced by the A3
migration: ``admin_configs``, ``mcp_servers`` and ``memory_entries``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.engine import Connection

from agentlabx.db.migrations import CURRENT_SCHEMA_VERSION, apply_migrations
from agentlabx.db.schema import AppState, Base
from agentlabx.db.session import DatabaseHandle


async def _build_v4_db(handle: DatabaseHandle) -> None:
    """Construct a minimal v4 DB in-place: full v4 ORM schema (which is the
    current ``Base.metadata`` minus the A3 tables) with ``schema_version=4``.
    """
    async with handle.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Drop the A3 tables so the DB looks like it was created at v4.
        await conn.execute(text("DROP TABLE IF EXISTS memory_entries"))
        await conn.execute(text("DROP TABLE IF EXISTS mcp_servers"))
        await conn.execute(text("DROP TABLE IF EXISTS admin_configs"))
    async with handle.session() as session:
        session.add(AppState(key="schema_version", value="4"))
        await session.commit()


@pytest.mark.asyncio
async def test_v4_to_v5_creates_a3_tables_and_bumps_version(tmp_workspace: Path) -> None:
    handle = DatabaseHandle(tmp_workspace / "t.db")
    await handle.connect()
    try:
        await _build_v4_db(handle)

        async with handle.engine.connect() as conn:

            def _table_names(sync_conn: Connection) -> set[str]:
                return set(inspect(sync_conn).get_table_names())

            before = await conn.run_sync(_table_names)
        assert "admin_configs" not in before
        assert "mcp_servers" not in before
        assert "memory_entries" not in before

        await apply_migrations(handle)

        async with handle.engine.connect() as conn:
            after = await conn.run_sync(_table_names)
        assert "admin_configs" in after
        assert "mcp_servers" in after
        assert "memory_entries" in after

        # Each new table is queryable (covers basic column-shape sanity).
        async with handle.engine.connect() as conn:

            def _row_counts(sync_conn: Connection) -> tuple[int, int, int]:
                a = sync_conn.execute(text("SELECT COUNT(*) FROM admin_configs")).scalar_one()
                m = sync_conn.execute(text("SELECT COUNT(*) FROM mcp_servers")).scalar_one()
                e = sync_conn.execute(text("SELECT COUNT(*) FROM memory_entries")).scalar_one()
                return int(a), int(m), int(e)

            assert await conn.run_sync(_row_counts) == (0, 0, 0)

        async with handle.session() as session:
            row = (
                await session.execute(select(AppState).where(AppState.key == "schema_version"))
            ).scalar_one()
        assert row.value == str(CURRENT_SCHEMA_VERSION) == "5"
    finally:
        await handle.close()


@pytest.mark.asyncio
async def test_v4_to_v5_is_idempotent_when_tables_already_exist(tmp_workspace: Path) -> None:
    """The migration must no-op if the A3 tables were created out-of-band
    (mirrors the v3→v4 ``PRAGMA table_info`` guard pattern)."""
    handle = DatabaseHandle(tmp_workspace / "t.db")
    await handle.connect()
    try:
        await _build_v4_db(handle)
        # Pre-create one of the A3 tables before the migration runs.
        async with handle.engine.begin() as conn:
            await conn.execute(
                text(
                    "CREATE TABLE admin_configs ("
                    "slot VARCHAR(128) PRIMARY KEY, "
                    "ciphertext BLOB NOT NULL, "
                    "created_at DATETIME NOT NULL)"
                )
            )

        await apply_migrations(handle)  # must not raise "table already exists"

        async with handle.session() as session:
            row = (
                await session.execute(select(AppState).where(AppState.key == "schema_version"))
            ).scalar_one()
        assert row.value == str(CURRENT_SCHEMA_VERSION)
    finally:
        await handle.close()
