from __future__ import annotations

from sqlalchemy import select

from agentlabx.db.schema import AppState, Base
from agentlabx.db.session import DatabaseHandle

CURRENT_SCHEMA_VERSION = 3


class SchemaVersionMismatchError(Exception):
    """DB schema_version does not match the code's expected version."""


async def apply_migrations(handle: DatabaseHandle) -> None:
    """Create tables + record schema_version on first run.

    Raises SchemaVersionMismatchError if an existing DB has a different
    schema_version than CURRENT_SCHEMA_VERSION.
    """
    async with handle.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with handle.session() as session:
        existing = (
            await session.execute(select(AppState).where(AppState.key == "schema_version"))
        ).scalar_one_or_none()
        if existing is None:
            session.add(AppState(key="schema_version", value=str(CURRENT_SCHEMA_VERSION)))
            await session.commit()
            return
        if existing.value != str(CURRENT_SCHEMA_VERSION):
            raise SchemaVersionMismatchError(
                f"database schema_version={existing.value} but code expects "
                f"{CURRENT_SCHEMA_VERSION}. AgentLabX is in dev-stage and has no "
                f"in-place migration yet; delete the DB file at "
                f"{handle._db_path} to reset."
            )
