"""Unit tests for the in-process memory MCP server (Stage A3 Task 8).

These tests construct a real server, wire it to a real ``ClientSession`` via
``mcp.shared.memory.create_connected_server_and_client_session``, and exercise
each of the four tools end-to-end through the SDK. This is closer to the
production code path (in-process transport) than poking the registered
handlers directly, and it keeps the assertions about JSON-encoded
``TextContent`` results honest.

Note on fixtures: ``create_connected_server_and_client_session`` enters an
anyio cancel scope, which must be exited in the same task that entered it.
Using it inside a pytest-asyncio fixture and yielding the session into a
test causes ``RuntimeError: Attempted to exit cancel scope in a different
task`` because the fixture and test run in different anyio tasks. We
therefore expose an inline ``@asynccontextmanager`` helper that each test
enters in its own task. See Task 5's polish for the same pattern.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from mcp import ClientSession
from mcp.shared.exceptions import McpError
from mcp.shared.memory import create_connected_server_and_client_session
from mcp.types import TextContent
from sqlalchemy.ext.asyncio import async_sessionmaker

from agentlabx.db.schema import Base
from agentlabx.db.session import DatabaseHandle
from agentlabx.mcp.bundles import memory_server


@asynccontextmanager
async def _client(tmp_path: Path) -> AsyncIterator[ClientSession]:
    """Build a fresh DB + memory MCP server + connected client, in one task.

    Each test enters this in its own task to avoid cross-task cancel-scope
    errors from anyio.
    """

    handle = DatabaseHandle(tmp_path / "memory_unit.db")
    await handle.connect()
    try:
        async with handle.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        session_factory = async_sessionmaker(handle.engine, expire_on_commit=False)
        server = memory_server.build_server(session_factory)
        async with create_connected_server_and_client_session(server) as session:
            yield session
    finally:
        await handle.close()


def _decode_text_payload(content: list[TextContent]) -> object:
    """Extract the JSON-encoded payload from a single-TextContent result."""

    assert len(content) == 1, f"expected one TextContent, got {len(content)}"
    item = content[0]
    assert isinstance(item, TextContent)
    return json.loads(item.text)


async def _create_entry(
    client: ClientSession,
    *,
    category: str,
    body: str,
    source_run_id: str | None = None,
) -> str:
    result = await client.call_tool(
        "memory.create",
        {"category": category, "body": body, "source_run_id": source_run_id},
    )
    assert not result.isError
    payload = _decode_text_payload(list(result.content))  # type: ignore[arg-type]
    assert isinstance(payload, dict)
    entry_id = payload["id"]
    assert isinstance(entry_id, str) and entry_id
    return entry_id


# ---------------------------------------------------------------------------
# tools/list
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_tools_exposes_all_four_with_capability_metadata(
    tmp_path: Path,
) -> None:
    async with _client(tmp_path) as client:
        listing = await client.list_tools()
        by_name = {tool.name: tool for tool in listing.tools}
        assert set(by_name) == {
            "memory.create",
            "memory.get",
            "memory.search",
            "memory.delete",
        }
        assert by_name["memory.create"].inputSchema["x-agentlabx-capabilities"] == ["memory_write"]
        assert by_name["memory.delete"].inputSchema["x-agentlabx-capabilities"] == ["memory_write"]
        assert by_name["memory.get"].inputSchema["x-agentlabx-capabilities"] == ["memory_read"]
        assert by_name["memory.search"].inputSchema["x-agentlabx-capabilities"] == ["memory_read"]


# ---------------------------------------------------------------------------
# create + get
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_then_get_round_trips_entry(tmp_path: Path) -> None:
    async with _client(tmp_path) as client:
        entry_id = await _create_entry(client, category="note", body="hello world")
        result = await client.call_tool("memory.get", {"id": entry_id})
        assert not result.isError
        payload = _decode_text_payload(list(result.content))  # type: ignore[arg-type]
        assert isinstance(payload, dict)
        assert payload["id"] == entry_id
        assert payload["category"] == "note"
        assert payload["body"] == "hello world"
        assert payload["source_run_id"] is None
        assert isinstance(payload["created_at"], str)


@pytest.mark.asyncio
async def test_create_accepts_explicit_source_run_id(tmp_path: Path) -> None:
    async with _client(tmp_path) as client:
        entry_id = await _create_entry(
            client, category="note", body="linked", source_run_id="run-42"
        )
        result = await client.call_tool("memory.get", {"id": entry_id})
        payload = _decode_text_payload(list(result.content))  # type: ignore[arg-type]
        assert isinstance(payload, dict)
        assert payload["source_run_id"] == "run-42"


@pytest.mark.asyncio
async def test_get_unknown_id_surfaces_as_is_error(tmp_path: Path) -> None:
    async with _client(tmp_path) as client:
        result = await client.call_tool("memory.get", {"id": "no-such-id"})
        # Server-side ValueError -> SDK returns isError=True with the message text.
        assert result.isError
        payload_text = "".join(
            item.text for item in result.content if isinstance(item, TextContent)
        )
        assert "not found" in payload_text


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_substring_case_insensitive(tmp_path: Path) -> None:
    async with _client(tmp_path) as client:
        await _create_entry(client, category="note", body="The Quick Brown Fox")
        await _create_entry(client, category="note", body="lazy dog")
        result = await client.call_tool(
            "memory.search",
            {"query_text": "QUICK", "category_filter": None, "max_results": 10},
        )
        payload = _decode_text_payload(list(result.content))  # type: ignore[arg-type]
        assert isinstance(payload, list)
        bodies = [row["body"] for row in payload if isinstance(row, dict)]
        assert bodies == ["The Quick Brown Fox"]


@pytest.mark.asyncio
async def test_search_filters_by_category(tmp_path: Path) -> None:
    async with _client(tmp_path) as client:
        await _create_entry(client, category="alpha", body="match here")
        await _create_entry(client, category="beta", body="match here too")
        result = await client.call_tool(
            "memory.search",
            {"query_text": "match", "category_filter": "alpha", "max_results": 10},
        )
        payload = _decode_text_payload(list(result.content))  # type: ignore[arg-type]
        assert isinstance(payload, list)
        assert len(payload) == 1
        row = payload[0]
        assert isinstance(row, dict)
        assert row["category"] == "alpha"


@pytest.mark.asyncio
async def test_search_respects_max_results_request_cap(tmp_path: Path) -> None:
    async with _client(tmp_path) as client:
        for idx in range(5):
            await _create_entry(client, category="note", body=f"row {idx}")
        result = await client.call_tool(
            "memory.search",
            {"query_text": "row", "category_filter": None, "max_results": 2},
        )
        payload = _decode_text_payload(list(result.content))  # type: ignore[arg-type]
        assert isinstance(payload, list)
        assert len(payload) == 2


@pytest.mark.asyncio
async def test_search_orders_most_recent_first(tmp_path: Path) -> None:
    async with _client(tmp_path) as client:
        first = await _create_entry(client, category="note", body="alpha first")
        second = await _create_entry(client, category="note", body="beta second")
        third = await _create_entry(client, category="note", body="gamma third")
        result = await client.call_tool(
            "memory.search",
            {"query_text": "", "category_filter": "note", "max_results": 10},
        )
        payload = _decode_text_payload(list(result.content))  # type: ignore[arg-type]
        assert isinstance(payload, list)
        ids = [row["id"] for row in payload if isinstance(row, dict)]
        assert ids == [third, second, first]


@pytest.mark.asyncio
async def test_search_empty_query_returns_all_entries(tmp_path: Path) -> None:
    async with _client(tmp_path) as client:
        await _create_entry(client, category="note", body="entry one")
        await _create_entry(client, category="note", body="entry two")
        result = await client.call_tool(
            "memory.search",
            {"query_text": "", "category_filter": None, "max_results": 100},
        )
        payload = _decode_text_payload(list(result.content))  # type: ignore[arg-type]
        assert isinstance(payload, list)
        assert len(payload) == 2


@pytest.mark.asyncio
async def test_search_caps_oversized_max_results(tmp_path: Path) -> None:
    async with _client(tmp_path) as client:
        for idx in range(3):
            await _create_entry(client, category="note", body=f"row {idx}")
        # The schema declares a ``maximum`` of MAX_SEARCH_RESULTS on
        # ``max_results``. The MCP SDK does not currently validate this
        # client-side, but the server defensively clamps oversized requests
        # to ``MAX_SEARCH_RESULTS`` (see ``_handle_search``). Either the
        # SDK rejects with ``McpError`` *or* the server returns a clamped
        # (and therefore bounded) result set -- both honour the cap. We
        # accept either to keep the test resilient to an SDK upgrade that
        # starts enforcing ``maximum`` strictly.
        try:
            result = await client.call_tool(
                "memory.search",
                {
                    "query_text": "row",
                    "category_filter": None,
                    "max_results": memory_server.MAX_SEARCH_RESULTS + 1,
                },
            )
        except McpError:
            return  # SDK raised on the schema cap -- acceptable.
        if result.isError:
            # Server-side schema validation surfaced the cap as a tool error
            # (current SDK behaviour). Verify the message references the cap.
            payload_text = "".join(
                item.text for item in result.content if isinstance(item, TextContent)
            )
            assert str(memory_server.MAX_SEARCH_RESULTS) in payload_text
            return
        payload = _decode_text_payload(list(result.content))  # type: ignore[arg-type]
        assert isinstance(payload, list)
        assert len(payload) <= memory_server.MAX_SEARCH_RESULTS


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_removes_row_and_get_then_errors(tmp_path: Path) -> None:
    async with _client(tmp_path) as client:
        entry_id = await _create_entry(client, category="note", body="ephemeral")
        delete_result = await client.call_tool("memory.delete", {"id": entry_id})
        assert not delete_result.isError
        payload = _decode_text_payload(list(delete_result.content))  # type: ignore[arg-type]
        assert payload == {"deleted": True}

        follow_up = await client.call_tool("memory.get", {"id": entry_id})
        assert follow_up.isError
        follow_text = "".join(
            item.text for item in follow_up.content if isinstance(item, TextContent)
        )
        assert "not found" in follow_text


@pytest.mark.asyncio
async def test_delete_unknown_id_is_idempotent(tmp_path: Path) -> None:
    async with _client(tmp_path) as client:
        result = await client.call_tool("memory.delete", {"id": "ghost"})
        assert not result.isError
        payload = _decode_text_payload(list(result.content))  # type: ignore[arg-type]
        assert payload == {"deleted": False}


# ---------------------------------------------------------------------------
# Module-level invariants
# ---------------------------------------------------------------------------


def test_declared_capabilities_match_taxonomy() -> None:
    assert memory_server.DECLARED_CAPABILITIES == ("memory_read", "memory_write")


@pytest.mark.asyncio
async def test_build_server_factory_returns_independent_servers(
    tmp_path: Path,
) -> None:
    handle = DatabaseHandle(tmp_path / "memory_unit_factory.db")
    await handle.connect()
    try:
        async with handle.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        session_factory = async_sessionmaker(handle.engine, expire_on_commit=False)
        factory = memory_server.build_server_factory(session_factory)
        server_a = factory()
        server_b = factory()
        assert server_a is not server_b
        assert server_a.name == memory_server.SERVER_NAME
    finally:
        await handle.close()
