"""Integration tests for :class:`MCPHost` against the echo stdio fake.

Boots ``tests/fakes/echo_mcp_server.py`` as a real subprocess, drives a
real :class:`mcp.ClientSession`, and asserts that:

* ``list_tools()`` surfaces ``echo`` and ``boom``.
* ``call("echo", {"message": "hi"})`` returns a ``ToolCallResult`` whose
  first content item is a :class:`TextContent` with ``text == "hi"``.
* ``call("boom", {})`` raises :class:`ToolExecutionFailed` with a non-None
  ``underlying``.
* The capability metadata key ``x-agentlabx-capabilities`` survives the SDK
  round-trip and overrides the server-level declaration on a per-tool
  basis.
* ``stop`` followed by ``start`` again with the same id succeeds.
* ``mcp.server.started`` and ``mcp.server.stopped`` are emitted on the bus.
"""

from __future__ import annotations

import sys
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from agentlabx.db.schema import Base
from agentlabx.db.session import DatabaseHandle
from agentlabx.events.bus import Event, EventBus
from agentlabx.mcp.host import MCPHost
from agentlabx.mcp.protocol import (
    MCPServerSpec,
    RegisteredServer,
    TextContent,
    ToolExecutionFailed,
)
from agentlabx.mcp.registry import ServerRegistry
from agentlabx.security.fernet_store import FernetStore
from agentlabx.security.slot_resolver import SlotResolver

ECHO_LAUNCH_COMMAND: tuple[str, ...] = (
    sys.executable,
    "-m",
    "tests.fakes.echo_mcp_server",
)


@pytest.fixture()
async def db(tmp_path: Path) -> AsyncIterator[DatabaseHandle]:
    handle = DatabaseHandle(tmp_path / "test.db")
    await handle.connect()
    async with handle.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield handle
    finally:
        await handle.close()


@pytest.fixture()
def fernet_store() -> FernetStore:
    from cryptography.fernet import Fernet

    return FernetStore(key=Fernet.generate_key())


@pytest.fixture()
def event_recorder() -> tuple[EventBus, list[Event]]:
    bus = EventBus()
    events: list[Event] = []

    async def _record(event: Event) -> None:
        events.append(event)

    bus.subscribe("*", _record)
    return bus, events


@pytest.fixture()
async def host(
    db: DatabaseHandle,
    fernet_store: FernetStore,
    event_recorder: tuple[EventBus, list[Event]],
) -> MCPHost:
    bus, _ = event_recorder
    factory = async_sessionmaker(db.engine, expire_on_commit=False)
    registry = ServerRegistry(factory)
    resolver = SlotResolver(fernet_store, factory)
    return MCPHost(
        registry=registry,
        slot_resolver=resolver,
        event_bus=bus,
        inprocess_factories={},
    )


def _echo_spec() -> MCPServerSpec:
    return MCPServerSpec(
        name="echo-fake",
        scope="admin",
        transport="stdio",
        command=ECHO_LAUNCH_COMMAND,
        url=None,
        inprocess_key=None,
        env_slot_refs=(),
        declared_capabilities=("default_cap",),
    )


def _registered(spec: MCPServerSpec) -> RegisteredServer:
    return RegisteredServer(
        id="echo-id",
        spec=spec,
        owner_id=None,
        tools=(),
        started_at=None,
    )


async def test_start_lists_tools_and_emits_started(
    host: MCPHost, event_recorder: tuple[EventBus, list[Event]]
) -> None:
    _, events = event_recorder
    started = await host.start(_registered(_echo_spec()), owner_id=None)
    try:
        tool_names = {t.tool_name for t in started.tools}
        assert tool_names == {"echo", "boom"}
        assert started.started_at is not None
        kinds = [e.kind for e in events]
        assert "mcp.server.started" in kinds
    finally:
        await host.stop(started.id)


async def test_capability_metadata_overrides_server_declaration(
    host: MCPHost,
) -> None:
    started = await host.start(_registered(_echo_spec()), owner_id=None)
    try:
        by_name = {t.tool_name: t for t in started.tools}
        # echo tool declares ``x-agentlabx-capabilities: ["echo_speak"]`` in
        # its inputSchema — this overrides the server's ``("default_cap",)``.
        assert by_name["echo"].capabilities == ("echo_speak",)
        # boom does not declare overrides — inherits server-level caps.
        assert by_name["boom"].capabilities == ("default_cap",)
        # Confirm the metadata key actually round-trips through the SDK.
        assert by_name["echo"].input_schema.get("x-agentlabx-capabilities") == ["echo_speak"]
    finally:
        await host.stop(started.id)


async def test_call_echo_returns_text(host: MCPHost) -> None:
    started = await host.start(_registered(_echo_spec()), owner_id=None)
    try:
        result = await host.call(started.id, "echo", {"message": "hi"})
        assert result.is_error is False
        assert len(result.content) == 1
        first = result.content[0]
        assert isinstance(first, TextContent)
        assert first.text == "hi"
    finally:
        await host.stop(started.id)


async def test_call_boom_raises_tool_execution_failed(host: MCPHost) -> None:
    started = await host.start(_registered(_echo_spec()), owner_id=None)
    try:
        with pytest.raises(ToolExecutionFailed) as exc_info:
            await host.call(started.id, "boom", {})
        assert exc_info.value.tool == "boom"
        assert exc_info.value.underlying is not None
    finally:
        await host.stop(started.id)


async def test_stop_emits_stopped_then_restart_succeeds(
    host: MCPHost, event_recorder: tuple[EventBus, list[Event]]
) -> None:
    _, events = event_recorder
    spec = _echo_spec()
    record = _registered(spec)

    started_first = await host.start(record, owner_id=None)
    await host.stop(started_first.id)

    assert any(e.kind == "mcp.server.stopped" for e in events)

    started_second = await host.start(record, owner_id=None)
    try:
        # Re-entering start with the same id after stop must succeed.
        assert {t.tool_name for t in started_second.tools} == {"echo", "boom"}
    finally:
        await host.stop(started_second.id)
