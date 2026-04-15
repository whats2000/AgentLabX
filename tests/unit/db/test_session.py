from __future__ import annotations

from pathlib import Path

import pytest

from agentlabx.db.session import DatabaseHandle


@pytest.mark.asyncio
async def test_connect_creates_db_file(tmp_workspace: Path) -> None:
    db_path = tmp_workspace / "test.db"
    assert not db_path.exists()
    handle = DatabaseHandle(db_path)
    await handle.connect()
    assert db_path.exists()
    await handle.close()


@pytest.mark.asyncio
async def test_session_roundtrips_a_trivial_query(tmp_workspace: Path) -> None:
    from sqlalchemy import text

    handle = DatabaseHandle(tmp_workspace / "t.db")
    await handle.connect()
    try:
        async with handle.session() as session:
            result = await session.execute(text("SELECT 1"))
            assert result.scalar() == 1
    finally:
        await handle.close()
