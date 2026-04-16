from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select

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
                await session.execute(select(AppState).where(AppState.key == "schema_version"))
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
        await apply_migrations(handle)  # no-op
        async with handle.session() as session:
            rows = (
                await session.execute(select(AppState).where(AppState.key == "schema_version"))
            ).scalars().all()
        assert len(rows) == 1
    finally:
        await handle.close()


@pytest.mark.asyncio
async def test_version_mismatch_raises(tmp_workspace: Path) -> None:
    """I6: if DB schema_version != CURRENT_SCHEMA_VERSION, apply_migrations raises."""
    handle = DatabaseHandle(tmp_workspace / "t.db")
    await handle.connect()
    try:
        await apply_migrations(handle)
        # Manually bump the stored version to a future value.
        async with handle.session() as session:
            existing = (
                await session.execute(select(AppState).where(AppState.key == "schema_version"))
            ).scalar_one()
            existing.value = "99"
            await session.commit()
        with pytest.raises(SchemaVersionMismatchError):
            await apply_migrations(handle)
    finally:
        await handle.close()
