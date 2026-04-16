from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.engine import Connection

from agentlabx.db.migrations import (
    CURRENT_SCHEMA_VERSION,
    SchemaVersionMismatchError,
    apply_migrations,
)
from agentlabx.db.schema import AppState
from agentlabx.db.session import DatabaseHandle


@pytest.mark.asyncio
async def test_first_run_creates_schema_and_records_version(tmp_workspace: Path) -> None:
    handle = DatabaseHandle(tmp_workspace / "t.db")
    await handle.connect()
    try:
        await apply_migrations(handle)
        async with handle.session() as session:
            row = (
                await session.execute(
                    select(AppState).where(AppState.key == "schema_version")
                )
            ).scalar_one()
        assert row.value == str(CURRENT_SCHEMA_VERSION)
    finally:
        await handle.close()


@pytest.mark.asyncio
async def test_second_run_is_idempotent(tmp_workspace: Path) -> None:
    handle = DatabaseHandle(tmp_workspace / "t.db")
    await handle.connect()
    try:
        await apply_migrations(handle)
        await apply_migrations(handle)
        async with handle.session() as session:
            rows = (
                await session.execute(
                    select(AppState).where(AppState.key == "schema_version")
                )
            ).scalars().all()
        assert len(rows) == 1
    finally:
        await handle.close()


@pytest.mark.asyncio
async def test_downgrade_version_raises(tmp_workspace: Path) -> None:
    handle = DatabaseHandle(tmp_workspace / "t.db")
    await handle.connect()
    try:
        await apply_migrations(handle)
        async with handle.session() as session:
            row = (
                await session.execute(
                    select(AppState).where(AppState.key == "schema_version")
                )
            ).scalar_one()
            row.value = "99"
            await session.commit()
        with pytest.raises(SchemaVersionMismatchError):
            await apply_migrations(handle)
    finally:
        await handle.close()


async def _build_v2_db(handle: DatabaseHandle) -> None:
    """Construct a minimal v2 DB in-place: the v3 schema minus `user_tokens`,
    with schema_version recorded as 2."""
    from agentlabx.db.schema import Base

    async with handle.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Drop user_tokens so the DB looks like it was created at v2.
        await conn.execute(text("DROP TABLE IF EXISTS user_tokens"))
    async with handle.session() as session:
        session.add(AppState(key="schema_version", value="2"))
        await session.commit()


@pytest.mark.asyncio
async def test_v2_to_v3_migration_creates_user_tokens(tmp_workspace: Path) -> None:
    handle = DatabaseHandle(tmp_workspace / "t.db")
    await handle.connect()
    try:
        await _build_v2_db(handle)

        async with handle.engine.connect() as conn:
            def _has_user_tokens(sync_conn: Connection) -> bool:
                return "user_tokens" in inspect(sync_conn).get_table_names()

            assert await conn.run_sync(_has_user_tokens) is False

        await apply_migrations(handle)

        async with handle.engine.connect() as conn:
            def _has_user_tokens_after(sync_conn: Connection) -> bool:
                return "user_tokens" in inspect(sync_conn).get_table_names()

            assert await conn.run_sync(_has_user_tokens_after) is True

        async with handle.session() as session:
            row = (
                await session.execute(
                    select(AppState).where(AppState.key == "schema_version")
                )
            ).scalar_one()
        assert row.value == str(CURRENT_SCHEMA_VERSION)
    finally:
        await handle.close()


async def _build_v1_db(handle: DatabaseHandle) -> None:
    """Construct a minimal v1 DB: v3 schema minus `user_tokens` AND minus the
    `email` column on users. Done with raw SQL because v1's User shape isn't
    what the current model declares."""
    async with handle.engine.begin() as conn:
        await conn.execute(
            text(
                """
                CREATE TABLE users (
                    id VARCHAR(36) PRIMARY KEY,
                    display_name VARCHAR(128) NOT NULL,
                    auther_name VARCHAR(64) NOT NULL,
                    created_at DATETIME NOT NULL
                )
                """
            )
        )
        await conn.execute(
            text(
                """
                CREATE TABLE app_state (
                    key VARCHAR(64) PRIMARY KEY,
                    value VARCHAR(512) NOT NULL,
                    updated_at DATETIME NOT NULL
                )
                """
            )
        )
        # Insert a v1 user and stamp the schema version.
        await conn.execute(
            text(
                "INSERT INTO users (id, display_name, auther_name, created_at) "
                "VALUES ('u-legacy', 'Legacy', 'default', '2026-01-01 00:00:00')"
            )
        )
        await conn.execute(
            text(
                "INSERT INTO app_state (key, value, updated_at) "
                "VALUES ('schema_version', '1', '2026-01-01 00:00:00')"
            )
        )


@pytest.mark.asyncio
async def test_v1_to_v2_adds_email_column_with_placeholder(tmp_workspace: Path) -> None:
    handle = DatabaseHandle(tmp_workspace / "t.db")
    await handle.connect()
    try:
        await _build_v1_db(handle)

        # Confirm email column is absent before migration.
        async with handle.engine.connect() as conn:
            def _has_email_col(sync_conn: Connection) -> bool:
                cols = [c["name"] for c in inspect(sync_conn).get_columns("users")]
                return "email" in cols

            assert await conn.run_sync(_has_email_col) is False

        # Migrate all the way up to current.
        await apply_migrations(handle)

        # Email column exists and legacy user has a placeholder email.
        async with handle.engine.connect() as conn:
            def _user_rows(sync_conn: Connection) -> list[tuple[str, str]]:
                rs = sync_conn.execute(text("SELECT id, email FROM users"))
                return [(r[0], r[1]) for r in rs]

            rows = await conn.run_sync(_user_rows)
        assert rows == [("u-legacy", "u-legacy@migrated.local")]

        async with handle.session() as session:
            v = (
                await session.execute(
                    select(AppState).where(AppState.key == "schema_version")
                )
            ).scalar_one()
        assert v.value == str(CURRENT_SCHEMA_VERSION)
    finally:
        await handle.close()
