"""SQLAlchemy ORM models for SQLite storage."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class SessionRecord(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(String, index=True)
    topic: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String)
    pipeline_config: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))


class CheckpointRecord(Base):
    __tablename__ = "checkpoints"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String, index=True)
    stage: Mapped[str] = mapped_column(String)
    state_blob: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))


class ArtifactRecord(Base):
    __tablename__ = "artifacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String, index=True)
    artifact_type: Mapped[str] = mapped_column(String)
    name: Mapped[str] = mapped_column(String)
    path: Mapped[str] = mapped_column(String, unique=True)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
