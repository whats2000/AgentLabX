from __future__ import annotations

from sqlalchemy import select

from agentlabx.db.schema import AppState, Base
from agentlabx.db.session import DatabaseHandle

CURRENT_SCHEMA_VERSION = 1


async def apply_migrations(handle: DatabaseHandle) -> None:
    """Create tables + record schema_version on first run; no-op thereafter."""
    async with handle.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with handle.session() as session:
        existing = (
            await session.execute(select(AppState).where(AppState.key == "schema_version"))
        ).scalar_one_or_none()
        if existing is None:
            session.add(AppState(key="schema_version", value=str(CURRENT_SCHEMA_VERSION)))
            await session.commit()
