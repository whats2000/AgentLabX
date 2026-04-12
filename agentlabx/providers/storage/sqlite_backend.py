"""SQLite storage backend using SQLAlchemy async."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from agentlabx.providers.storage.base import BaseStorageBackend
from agentlabx.providers.storage.models import (
    ArtifactRecord,
    Base,
    CheckpointRecord,
)


class SQLiteBackend(BaseStorageBackend):
    """Async SQLite backend.

    Stores pipeline state as JSON blobs in the checkpoints table.
    Stores artifacts as files on disk with metadata in the artifacts table.
    Paths are namespaced by session_id.
    """

    def __init__(self, *, database_url: str, artifacts_path: Path) -> None:
        self.database_url = database_url
        self.artifacts_path = Path(artifacts_path)
        self._engine = None
        self._session_factory: async_sessionmaker[AsyncSession] | None = None

    async def initialize(self) -> None:
        """Create database tables and artifacts directory."""
        self._engine = create_async_engine(self.database_url, echo=False)
        self._session_factory = async_sessionmaker(self._engine, expire_on_commit=False)
        self.artifacts_path.mkdir(parents=True, exist_ok=True)

        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def close(self) -> None:
        if self._engine:
            await self._engine.dispose()

    async def save_state(
        self, session_id: str, stage: str, state: dict[str, Any]
    ) -> None:
        if self._session_factory is None:
            msg = "Backend not initialized — call initialize() first"
            raise RuntimeError(msg)
        async with self._session_factory() as sess:
            # Delete existing checkpoint for this session+stage (overwrite semantics)
            await sess.execute(
                delete(CheckpointRecord).where(
                    CheckpointRecord.session_id == session_id,
                    CheckpointRecord.stage == stage,
                )
            )
            sess.add(CheckpointRecord(session_id=session_id, stage=stage, state_blob=state))
            await sess.commit()

    async def load_state(
        self, session_id: str, stage: str
    ) -> dict[str, Any] | None:
        if self._session_factory is None:
            return None
        async with self._session_factory() as sess:
            result = await sess.execute(
                select(CheckpointRecord)
                .where(
                    CheckpointRecord.session_id == session_id,
                    CheckpointRecord.stage == stage,
                )
                .order_by(CheckpointRecord.created_at.desc())
                .limit(1)
            )
            record = result.scalar_one_or_none()
            return record.state_blob if record else None

    async def save_artifact(
        self,
        session_id: str,
        artifact_type: str,
        name: str,
        data: bytes,
    ) -> str:
        if self._session_factory is None:
            msg = "Backend not initialized — call initialize() first"
            raise RuntimeError(msg)

        # Namespaced path: artifacts_path/session_id/artifact_type/uuid_name
        session_dir = self.artifacts_path / session_id / artifact_type
        session_dir.mkdir(parents=True, exist_ok=True)
        unique_name = f"{uuid.uuid4().hex[:8]}_{name}"
        file_path = session_dir / unique_name
        file_path.write_bytes(data)

        path_str = str(file_path)

        async with self._session_factory() as sess:
            sess.add(
                ArtifactRecord(
                    session_id=session_id,
                    artifact_type=artifact_type,
                    name=name,
                    path=path_str,
                    size_bytes=len(data),
                )
            )
            await sess.commit()

        return path_str

    async def load_artifact(self, path: str) -> bytes | None:
        file_path = Path(path)
        if not file_path.exists():
            return None
        return file_path.read_bytes()
