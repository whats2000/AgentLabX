from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import inspect
from sqlalchemy.engine import Connection

from agentlabx.db.schema import Base
from agentlabx.db.session import DatabaseHandle


@pytest.mark.asyncio
async def test_all_tables_created(tmp_workspace: Path) -> None:
    handle = DatabaseHandle(tmp_workspace / "t.db")
    await handle.connect()
    try:
        async with handle.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

            def _table_names(sync_conn: Connection) -> list[str]:
                return sorted(inspect(sync_conn).get_table_names())

            tables = await conn.run_sync(_table_names)
        assert tables == sorted(
            [
                "admin_configs",
                "app_state",
                "capabilities",
                "mcp_servers",
                "memory_entries",
                "oauth_tokens",
                "sessions",
                "user_configs",
                "user_tokens",
                "users",
            ]
        )
    finally:
        await handle.close()
