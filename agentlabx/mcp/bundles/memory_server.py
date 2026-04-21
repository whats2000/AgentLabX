"""In-process MCP server backing AgentLabX's persistent ``memory_entries`` table.

The memory server exposes basic CRUD over the ``memory_entries`` table (Task 3
schema) as four tools:

* ``memory.create(category, body, source_run_id?)`` -> ``{"id": <uuid>}``
* ``memory.get(id)``                                 -> ``{"id", "category",
  "body", "source_run_id", "created_at"}``
* ``memory.search(query_text, category_filter?,
  max_results)``                                     -> ``[{...}, ...]``
* ``memory.delete(id)``                              -> ``{"deleted": <bool>}``

Stage A3 ships **basic CRUD only**; the curator-governance layer (endorsements,
freshness scoring, provenance lineage) is Stage C4 work and the tool
signatures here are forward-compatible with that addition. ``memory.search``'s
A3 implementation is plain SQLite ``LIKE``-based substring matching on
``body``; the Stage C4 vector index is purely additive.

----------------------------------------------------------------------
Result-shape convention
----------------------------------------------------------------------
The MCP wire format wraps every successful tool result in an iterable of
``ContentBlock``\\s. The agreed AgentLabX convention is: each tool returns a
single :class:`mcp.types.TextContent` whose ``text`` is the JSON encoding of
the tool-specific result payload. Callers that want the structured value
``json.loads`` the ``TextContent.text``. The host's ``_adapt_call_result``
preserves the encoded text verbatim as ``ToolCallResult.content[0].text``.

This convention is what every bundled in-process server in Stage A3 follows;
keeping it uniform keeps the dispatcher's downstream consumer logic simple.

----------------------------------------------------------------------
Empty-query / not-found behaviour
----------------------------------------------------------------------
* ``memory.search`` with an empty/whitespace ``query_text`` matches **all**
  entries (subject to ``category_filter`` and ``max_results``). This makes
  ``memory.search("", max_results=N)`` a useful "list latest N" operation.
* ``memory.search`` caps ``max_results`` at :data:`MAX_SEARCH_RESULTS`
  (currently ``100``) to bound result set size.
* ``memory.get`` of an unknown id raises :class:`ValueError` -- the SDK
  surfaces this as a ``CallToolResult`` with ``isError=True``, which the host
  re-raises as ``ToolExecutionFailed``. Callers should treat "not found" as a
  genuine error rather than a missing optional value.
* ``memory.delete`` of an unknown id is **not** an error; it returns
  ``{"deleted": false}`` so the caller can use it idempotently.

----------------------------------------------------------------------
Capability mapping
----------------------------------------------------------------------
Server-level declared capabilities are :data:`DECLARED_CAPABILITIES`
(``("memory_read", "memory_write")``). Per-tool overrides are advertised via
the ``x-agentlabx-capabilities`` ``inputSchema`` metadata key (Task 5):

* ``memory.search`` / ``memory.get``  -> ``["memory_read"]``
* ``memory.create`` / ``memory.delete`` -> ``["memory_write"]``

----------------------------------------------------------------------
Factory contract
----------------------------------------------------------------------
The launcher registry (``InProcessLauncher.factories``) stores no-arg
callables ``() -> Server``. To bind the SQLAlchemy session factory at host
startup, use :func:`build_server_factory`::

    factory = build_server_factory(session_factory)
    inprocess_factories = {"memory_server": factory}

The host's wiring (Task 7) calls ``factory()`` once per session open. Callers
who want a server directly (e.g. unit tests) can use :func:`build_server`.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable, Sequence
from datetime import datetime, timezone

from mcp.server import Server
from mcp.types import TextContent, Tool
from sqlalchemy import delete as sql_delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentlabx.db.schema import MemoryEntry

DECLARED_CAPABILITIES: tuple[str, ...] = ("memory_read", "memory_write")
"""Server-level declared capabilities, advertised to the host registry."""

MAX_SEARCH_RESULTS: int = 100
"""Hard upper bound on ``memory.search.max_results`` (request value is clamped)."""

SERVER_NAME: str = "agentlabx-memory"
"""Stable MCP server ``name`` advertised to clients."""

CAPABILITY_METADATA_KEY: str = "x-agentlabx-capabilities"
"""``inputSchema`` key recognised by :mod:`agentlabx.mcp.host` for per-tool override."""


def _create_schema() -> dict[str, object]:
    return {
        "type": "object",
        "properties": {
            "category": {"type": "string"},
            "body": {"type": "string"},
            "source_run_id": {"type": ["string", "null"]},
        },
        "required": ["category", "body"],
        "additionalProperties": False,
        CAPABILITY_METADATA_KEY: ["memory_write"],
    }


def _get_schema() -> dict[str, object]:
    return {
        "type": "object",
        "properties": {
            "id": {"type": "string"},
        },
        "required": ["id"],
        "additionalProperties": False,
        CAPABILITY_METADATA_KEY: ["memory_read"],
    }


def _search_schema() -> dict[str, object]:
    return {
        "type": "object",
        "properties": {
            "query_text": {"type": "string"},
            "category_filter": {"type": ["string", "null"]},
            "max_results": {
                "type": "integer",
                "minimum": 1,
                "maximum": MAX_SEARCH_RESULTS,
            },
        },
        "required": ["query_text", "max_results"],
        "additionalProperties": False,
        CAPABILITY_METADATA_KEY: ["memory_read"],
    }


def _delete_schema() -> dict[str, object]:
    return {
        "type": "object",
        "properties": {
            "id": {"type": "string"},
        },
        "required": ["id"],
        "additionalProperties": False,
        CAPABILITY_METADATA_KEY: ["memory_write"],
    }


TOOL_DESCRIPTORS: tuple[Tool, ...] = (
    Tool(
        name="memory.create",
        description=(
            "Create a memory entry. Returns the assigned id. The optional "
            "source_run_id is reserved for Stage B run linkage; pass null in A3."
        ),
        inputSchema=_create_schema(),
    ),
    Tool(
        name="memory.get",
        description=("Fetch a single memory entry by id. Raises if the entry does not exist."),
        inputSchema=_get_schema(),
    ),
    Tool(
        name="memory.search",
        description=(
            "Substring-search memory entries by body (case-insensitive, SQLite "
            "LIKE). Returns most-recent entries first, capped at "
            f"{MAX_SEARCH_RESULTS} results. Empty query_text matches all entries."
        ),
        inputSchema=_search_schema(),
    ),
    Tool(
        name="memory.delete",
        description=(
            "Delete a memory entry by id. Returns {deleted: bool}; deleting a "
            "non-existent id is not an error (returns {deleted: false})."
        ),
        inputSchema=_delete_schema(),
    ),
)


def _entry_to_dict(entry: MemoryEntry) -> dict[str, str | None]:
    """Serialise a :class:`MemoryEntry` row to the wire-shape result dict.

    ``created_at`` is rendered as an ISO-8601 string in UTC; the SQLAlchemy
    column is timezone-aware on write but SQLite returns naive datetimes on
    read, so we re-attach UTC defensively before formatting.
    """

    created_at = entry.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    return {
        "id": entry.id,
        "category": entry.category,
        "body": entry.body,
        "source_run_id": entry.source_run_id,
        "created_at": created_at.isoformat(),
    }


def _as_text(payload: object) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps(payload))]


async def _handle_create(
    session: AsyncSession,
    arguments: dict[str, object],
) -> dict[str, str]:
    category = arguments.get("category")
    body = arguments.get("body")
    if not isinstance(category, str) or not category:
        raise ValueError("memory.create requires a non-empty string 'category'")
    if not isinstance(body, str) or not body:
        raise ValueError("memory.create requires a non-empty string 'body'")
    raw_source = arguments.get("source_run_id")
    source_run_id: str | None
    if raw_source is None:
        source_run_id = None
    elif isinstance(raw_source, str):
        source_run_id = raw_source
    else:
        raise ValueError("memory.create 'source_run_id' must be a string or null")

    entry = MemoryEntry(
        id=str(uuid.uuid4()),
        category=category,
        body=body,
        source_run_id=source_run_id,
        created_by=None,
        created_at=datetime.now(tz=timezone.utc),
    )
    session.add(entry)
    await session.commit()
    return {"id": entry.id}


async def _handle_get(
    session: AsyncSession,
    arguments: dict[str, object],
) -> dict[str, str | None]:
    raw_id = arguments.get("id")
    if not isinstance(raw_id, str) or not raw_id:
        raise ValueError("memory.get requires a non-empty string 'id'")
    entry = await session.get(MemoryEntry, raw_id)
    if entry is None:
        raise ValueError(f"memory entry {raw_id!r} not found")
    return _entry_to_dict(entry)


async def _handle_search(
    session: AsyncSession,
    arguments: dict[str, object],
) -> list[dict[str, str | None]]:
    raw_query = arguments.get("query_text", "")
    if not isinstance(raw_query, str):
        raise ValueError("memory.search 'query_text' must be a string")
    raw_filter = arguments.get("category_filter")
    category_filter: str | None
    if raw_filter is None:
        category_filter = None
    elif isinstance(raw_filter, str):
        category_filter = raw_filter or None
    else:
        raise ValueError("memory.search 'category_filter' must be a string or null")
    raw_max = arguments.get("max_results")
    if not isinstance(raw_max, int) or isinstance(raw_max, bool) or raw_max < 1:
        raise ValueError("memory.search 'max_results' must be a positive integer")
    max_results = min(raw_max, MAX_SEARCH_RESULTS)

    stmt = select(MemoryEntry)
    query_text = raw_query.strip()
    if query_text:
        # Escape LIKE wildcards in the user-supplied substring so a literal
        # ``%`` or ``_`` in the query does not accidentally widen the match.
        escaped = query_text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        stmt = stmt.where(MemoryEntry.body.ilike(f"%{escaped}%", escape="\\"))
    if category_filter is not None:
        stmt = stmt.where(MemoryEntry.category == category_filter)
    stmt = stmt.order_by(MemoryEntry.created_at.desc()).limit(max_results)

    rows: Sequence[MemoryEntry] = (await session.execute(stmt)).scalars().all()
    return [_entry_to_dict(row) for row in rows]


async def _handle_delete(
    session: AsyncSession,
    arguments: dict[str, object],
) -> dict[str, bool]:
    raw_id = arguments.get("id")
    if not isinstance(raw_id, str) or not raw_id:
        raise ValueError("memory.delete requires a non-empty string 'id'")
    result = await session.execute(sql_delete(MemoryEntry).where(MemoryEntry.id == raw_id))
    await session.commit()
    rowcount: int | None = getattr(result, "rowcount", None)
    deleted = rowcount is not None and rowcount > 0
    return {"deleted": deleted}


def build_server(session_factory: async_sessionmaker[AsyncSession]) -> Server[object, object]:
    """Construct a configured ``Server`` bound to ``session_factory``.

    Each tool handler opens a fresh ``AsyncSession`` via ``session_factory()``
    so concurrent tool calls do not share a session; this matches the rest of
    AgentLabX's repository pattern.
    """

    server: Server[object, object] = Server(SERVER_NAME)

    @server.list_tools()  # type: ignore[no-untyped-call,untyped-decorator]
    async def list_tools() -> list[Tool]:
        return list(TOOL_DESCRIPTORS)

    @server.call_tool()  # type: ignore[untyped-decorator]
    async def call_tool(name: str, arguments: dict[str, object]) -> list[TextContent]:
        async with session_factory() as session:
            if name == "memory.create":
                return _as_text(await _handle_create(session, arguments))
            if name == "memory.get":
                return _as_text(await _handle_get(session, arguments))
            if name == "memory.search":
                return _as_text(await _handle_search(session, arguments))
            if name == "memory.delete":
                return _as_text(await _handle_delete(session, arguments))
            raise ValueError(f"unknown tool: {name}")

    return server


def build_server_factory(
    session_factory: async_sessionmaker[AsyncSession],
) -> Callable[[], Server[object, object]]:
    """Bind ``session_factory`` and return the no-arg factory the host expects.

    The host stores ``Callable[[], Server]`` values in its in-process launcher
    registry, so any session-factory binding has to happen at startup time.
    """

    def factory() -> Server[object, object]:
        return build_server(session_factory)

    return factory


__all__ = [
    "DECLARED_CAPABILITIES",
    "MAX_SEARCH_RESULTS",
    "SERVER_NAME",
    "TOOL_DESCRIPTORS",
    "build_server",
    "build_server_factory",
]
