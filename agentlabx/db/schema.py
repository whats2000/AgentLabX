from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    auther_name: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    configs: Mapped[list[UserConfig]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    tokens: Mapped[list[OAuthToken]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    capabilities: Mapped[list[Capability]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    sessions: Mapped[list[Session]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    tokens_v2: Mapped[list[UserToken]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class UserConfig(Base):
    __tablename__ = "user_configs"
    __table_args__ = (UniqueConstraint("user_id", "slot", name="uq_user_configs_user_slot"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    slot: Mapped[str] = mapped_column(String(128), nullable=False)
    ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    user: Mapped[User] = relationship(back_populates="configs")


class OAuthToken(Base):
    __tablename__ = "oauth_tokens"
    __table_args__ = (
        UniqueConstraint("user_id", "provider", name="uq_oauth_tokens_user_provider"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    access_ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    refresh_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    user: Mapped[User] = relationship(back_populates="tokens")


class AppState(Base):
    __tablename__ = "app_state"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(512), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    user: Mapped[User] = relationship(back_populates="sessions")


class UserToken(Base):
    __tablename__ = "user_tokens"
    __table_args__ = (UniqueConstraint("token_hash", name="uq_user_tokens_hash"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)  # uuid
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)  # sha256 hex
    label: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship(back_populates="tokens_v2")


class AdminConfig(Base):
    """Admin-scope credential storage, keyed by slot name.

    The Stage A3 ``SlotResolver`` queries ``SELECT ciphertext FROM admin_configs
    WHERE slot = :slot`` directly via raw SQL, so the column shape here is fixed
    by that contract. Future admin-settings endpoints can use this ORM model
    instead of dropping into raw SQL.
    """

    __tablename__ = "admin_configs"

    slot: Mapped[str] = mapped_column(String(128), primary_key=True)
    ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class MCPServer(Base):
    """An MCP server registration (stdio / http / inprocess transport).

    ``owner_id IS NULL`` denotes admin scope; otherwise it is the owning user's
    UUID. ``(scope, owner_id, name)`` is unique per scope so users cannot collide
    on names within their own namespace and admins cannot register two admin
    servers with the same name.
    """

    __tablename__ = "mcp_servers"
    __table_args__ = (
        UniqueConstraint("scope", "owner_id", "name", name="uq_mcp_servers_scope_owner_name"),
        Index("idx_mcp_servers_owner", "owner_id", "enabled"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)  # uuid
    owner_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    scope: Mapped[str] = mapped_column(String(16), nullable=False)  # 'user' | 'admin'
    transport: Mapped[str] = mapped_column(String(16), nullable=False)  # 'stdio'|'http'|'inprocess'
    command_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    inprocess_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    env_slot_refs_json: Mapped[str] = mapped_column(Text, nullable=False)
    declared_capabilities_json: Mapped[str] = mapped_column(Text, nullable=False)
    # JSON list of [slot_ref, env_var_name] pairs. Empty list when no
    # overrides are declared. Migration v5→v6 added this column with
    # default '[]' for backward compatibility with pre-A3-patch rows.
    slot_env_overrides_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="[]", server_default="[]"
    )
    # Last ``ServerStartupFailed.reason`` recorded against this row, or
    # NULL when the row last started cleanly. Cleared on successful
    # ``host.start``; populated on failure so the UI can surface why a
    # row is grey without spelunking the audit log. Migration v6→v7.
    last_startup_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class MemoryEntry(Base):
    """A single memory note authored by a user (Task 8 ``memory_server``).

    ``source_run_id`` is reserved for Stage B which links memories back to the
    run that produced them; for now it is always ``NULL``. ``created_by`` uses
    ``ON DELETE SET NULL`` so deleting a user does not orphan their memories.
    """

    __tablename__ = "memory_entries"
    __table_args__ = (Index("idx_memory_entries_category", "category"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)  # uuid
    category: Mapped[str] = mapped_column(String(128), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    source_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class Capability(Base):
    __tablename__ = "capabilities"
    __table_args__ = (UniqueConstraint("user_id", "capability", name="uq_capabilities_user_name"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    capability: Mapped[str] = mapped_column(String(64), nullable=False)
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    user: Mapped[User] = relationship(back_populates="capabilities")
