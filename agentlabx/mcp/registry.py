"""Server registry — SQLite persistence for MCP server registrations.

The registry is the *only* path that mutates the ``mcp_servers`` table. It owns
serialisation between the typed :class:`MCPServerSpec` value object and the
JSON-encoded columns on the :class:`MCPServer` ORM row, plus per-user vs
admin-scope visibility queries.

Runtime concerns (live tool snapshots, ``ClientSession`` handles, started_at
timestamps) belong to :class:`MCPHost`. The registry returns
:class:`RegisteredServer` objects with ``tools=()`` and ``started_at=None`` —
the host fills those in when it starts a server.
"""

from __future__ import annotations

import json
import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentlabx.db.schema import MCPServer
from agentlabx.mcp.protocol import (
    MCPServerSpec,
    RegisteredServer,
    RegistrationConflict,
    Scope,
    Transport,
)

_VALID_SCOPES: frozenset[str] = frozenset({"user", "admin"})
_VALID_TRANSPORTS: frozenset[str] = frozenset({"stdio", "http", "inprocess"})


class ServerRegistry:
    """Persistence-layer CRUD over ``mcp_servers``.

    The registry is constructed with an ``async_sessionmaker`` rather than a
    ``DatabaseHandle`` so it can be reused in non-FastAPI call sites (background
    MCP launches, CLI commands) and so tests can supply a session factory built
    directly from a throwaway engine.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = session_factory

    async def register(self, spec: MCPServerSpec, owner_id: str | None) -> RegisteredServer:
        """Insert a new server row.

        Raises :class:`RegistrationConflict` on UNIQUE-constraint violation
        against ``(scope, owner_id, name)``. Any other ``IntegrityError`` (e.g.
        a foreign-key failure on a stale ``owner_id``) re-raises unchanged so
        the caller sees the real cause.
        """
        row = MCPServer(
            id=uuid.uuid4().hex,
            owner_id=owner_id,
            name=spec.name,
            scope=spec.scope,
            transport=spec.transport,
            command_json=_encode_optional_tuple(spec.command),
            url=spec.url,
            inprocess_key=spec.inprocess_key,
            env_slot_refs_json=json.dumps(list(spec.env_slot_refs)),
            declared_capabilities_json=json.dumps(list(spec.declared_capabilities)),
            slot_env_overrides_json=json.dumps([list(p) for p in spec.slot_env_overrides]),
            enabled=1,
        )
        async with self._sessionmaker() as session:
            session.add(row)
            try:
                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                if _is_unique_violation(exc):
                    raise RegistrationConflict(spec.name) from exc
                raise
        return _row_to_registered(row)

    async def list_visible_to(self, user_id: str) -> list[RegisteredServer]:
        """Return admin-scope rows + the user's own user-scope rows.

        Order is stable: admin-scope first, then alphabetical by name. Tests
        rely on this ordering — do not change it without updating them.
        """
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(MCPServer)
                .where((MCPServer.owner_id.is_(None)) | (MCPServer.owner_id == user_id))
                .order_by(MCPServer.scope.asc(), MCPServer.name.asc())
            )
            rows = result.scalars().all()
        return [_row_to_registered(r) for r in rows]

    async def get(self, server_id: str) -> RegisteredServer | None:
        async with self._sessionmaker() as session:
            row = await session.get(MCPServer, server_id)
        if row is None:
            return None
        return _row_to_registered(row)

    async def delete(
        self,
        server_id: str,
        requester_id: str,
        requester_is_admin: bool,
    ) -> bool:
        """Delete a row iff the requester is allowed to.

        Returns ``True`` only when a row was actually deleted; missing rows and
        permission denials both return ``False`` (the plan specifies "True iff
        a row was deleted" — callers needing to distinguish must check via
        :meth:`get` first).
        """
        async with self._sessionmaker() as session:
            row = await session.get(MCPServer, server_id)
            if row is None:
                return False
            if not _can_delete(row, requester_id, requester_is_admin):
                return False
            await session.delete(row)
            await session.commit()
        return True

    async def set_enabled(self, server_id: str, enabled: bool) -> None:
        """Set the ``enabled`` flag. No-op if the row is absent."""
        async with self._sessionmaker() as session:
            row = await session.get(MCPServer, server_id)
            if row is None:
                return
            row.enabled = 1 if enabled else 0
            await session.commit()

    async def get_enabled(self, server_id: str) -> bool | None:
        """Read the ``enabled`` flag for a server.

        Returns ``True`` / ``False`` for an existing row, or ``None`` when no
        such server exists. This is the read-side complement of
        :meth:`set_enabled` and exists so callers do not have to reach into
        :attr:`_sessionmaker` to perform a one-column lookup.
        """
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(MCPServer.enabled).where(MCPServer.id == server_id)
            )
            row = result.scalar_one_or_none()
        if row is None:
            return None
        return bool(row)

    async def set_startup_error(self, server_id: str, error: str | None) -> None:
        """Record (or clear) the most recent startup-failure reason.

        Pass ``error`` to populate, ``None`` to clear after a successful
        :meth:`MCPHost.start`. Truncates to 4 KiB so a runaway upstream
        stack-trace can't blow the row size out. No-op when the row is
        absent.
        """
        truncated = error[:4096] if error is not None else None
        async with self._sessionmaker() as session:
            row = await session.get(MCPServer, server_id)
            if row is None:
                return
            row.last_startup_error = truncated
            await session.commit()

    async def update_admin_spec(self, name: str, spec: MCPServerSpec) -> bool:
        """Overwrite the launch spec of an existing admin-scope row in place.

        Used by the boot-time seed loop so a code change to a bundle module
        (e.g. a renamed PyPI package, an added env-slot ref, a tweaked
        capability list) actually reaches the database — without a manual
        delete/re-register dance. The identity key ``(scope, owner_id, name)``
        is unchanged so the row id is preserved (downstream consumers that
        cached the id stay valid). Returns ``True`` when a row was updated,
        ``False`` if no admin row exists with that name.
        """
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(MCPServer).where(
                    MCPServer.scope == "admin",
                    MCPServer.owner_id.is_(None),
                    MCPServer.name == name,
                )
            )
            row = result.scalar_one_or_none()
            if row is None:
                return False
            row.transport = spec.transport
            row.command_json = _encode_optional_tuple(spec.command)
            row.url = spec.url
            row.inprocess_key = spec.inprocess_key
            row.env_slot_refs_json = json.dumps(list(spec.env_slot_refs))
            row.declared_capabilities_json = json.dumps(list(spec.declared_capabilities))
            row.slot_env_overrides_json = json.dumps([list(p) for p in spec.slot_env_overrides])
            await session.commit()
        return True

    async def find_admin_by_name(self, name: str) -> RegisteredServer | None:
        """Look up an admin-scope (``owner_id IS NULL``) row by ``name``.

        Used by the bundle-seeding loop on startup to detect whether the
        idempotent UPSERT should insert a fresh row or reconcile an existing
        one. Returns ``None`` when no matching admin row exists.
        """
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(MCPServer).where(
                    MCPServer.scope == "admin",
                    MCPServer.owner_id.is_(None),
                    MCPServer.name == name,
                )
            )
            row = result.scalar_one_or_none()
        if row is None:
            return None
        return _row_to_registered(row)

    async def list_enabled_ids(self) -> list[str]:
        """Return the ``id`` of every server row whose ``enabled`` flag is set.

        Used during boot to start every server that was enabled at the last
        shutdown. Order is the database's natural insertion order; callers
        that need a stable ordering must sort the result themselves.
        """
        async with self._sessionmaker() as session:
            result = await session.execute(select(MCPServer.id).where(MCPServer.enabled == 1))
            rows = result.scalars().all()
        return list(rows)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _can_delete(row: MCPServer, requester_id: str, requester_is_admin: bool) -> bool:
    if row.scope == "admin":
        return requester_is_admin
    # scope == "user"
    return requester_is_admin or row.owner_id == requester_id


# Empty-command stdio spec is rejected upstream by MCPServerSpec.__post_init__.
def _encode_optional_tuple(value: tuple[str, ...] | None) -> str | None:
    if value is None:
        return None
    return json.dumps(list(value))


def _decode_optional_tuple(value: str | None) -> tuple[str, ...] | None:
    if value is None:
        return None
    decoded = json.loads(value)
    if not isinstance(decoded, list):
        raise ValueError(f"expected JSON list in column, got {type(decoded).__name__}")
    return tuple(_require_str(item) for item in decoded)


def _decode_required_tuple(value: str) -> tuple[str, ...]:
    decoded = json.loads(value)
    if not isinstance(decoded, list):
        raise ValueError(f"expected JSON list in column, got {type(decoded).__name__}")
    return tuple(_require_str(item) for item in decoded)


def _decode_pair_tuple(value: str | None) -> tuple[tuple[str, str], ...]:
    """Decode a JSON ``[[a, b], [c, d], ...]`` payload into a tuple of pairs.

    Used for ``slot_env_overrides_json``. ``None`` and ``"[]"`` both decode to
    the empty tuple, keeping the v5→v6 default-value column friendly.
    """
    if value is None or value == "":
        return ()
    decoded = json.loads(value)
    if not isinstance(decoded, list):
        raise ValueError(f"expected JSON list in column, got {type(decoded).__name__}")
    out: list[tuple[str, str]] = []
    for item in decoded:
        if not isinstance(item, list) or len(item) != 2:
            raise ValueError(f"expected JSON pair (length 2), got {item!r}")
        out.append((_require_str(item[0]), _require_str(item[1])))
    return tuple(out)


def _require_str(item: object) -> str:
    if not isinstance(item, str):
        raise ValueError(f"expected JSON string element, got {type(item).__name__}")
    return item


def _coerce_scope(value: str) -> Scope:
    if value not in _VALID_SCOPES:
        raise ValueError(f"unknown scope {value!r} in mcp_servers row")
    # mypy: narrow str to the Literal alias.
    return "admin" if value == "admin" else "user"


def _coerce_transport(value: str) -> Transport:
    if value not in _VALID_TRANSPORTS:
        raise ValueError(f"unknown transport {value!r} in mcp_servers row")
    if value == "stdio":
        return "stdio"
    if value == "http":
        return "http"
    return "inprocess"


def _row_to_registered(row: MCPServer) -> RegisteredServer:
    spec = MCPServerSpec(
        name=row.name,
        scope=_coerce_scope(row.scope),
        transport=_coerce_transport(row.transport),
        command=_decode_optional_tuple(row.command_json),
        url=row.url,
        inprocess_key=row.inprocess_key,
        env_slot_refs=_decode_required_tuple(row.env_slot_refs_json),
        declared_capabilities=_decode_required_tuple(row.declared_capabilities_json),
        slot_env_overrides=_decode_pair_tuple(row.slot_env_overrides_json),
    )
    return RegisteredServer(
        id=row.id,
        spec=spec,
        owner_id=row.owner_id,
        tools=(),
        started_at=None,
        last_startup_error=row.last_startup_error,
    )


def _is_unique_violation(exc: IntegrityError) -> bool:
    """Heuristic: distinguish UNIQUE failures from FK failures.

    SQLAlchemy does not expose a backend-agnostic typed reason; the safest
    portable check is a substring match on the underlying DBAPI message.
    SQLite (aiosqlite) and PostgreSQL surface the literal "UNIQUE" / "unique"
    in their error text for this constraint class. MySQL instead reports
    ``"Duplicate entry ... for key ..."`` — we accept either phrasing. We
    treat ambiguous IntegrityErrors as conflicts only when the message
    clearly mentions uniqueness or a duplicate key; everything else re-raises.
    """
    message = str(exc.orig) if exc.orig is not None else str(exc)
    lowered = message.lower()
    return "unique" in lowered or ("duplicate" in lowered and "key" in lowered)


__all__ = ["ServerRegistry"]
