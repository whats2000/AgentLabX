"""End-to-end dispatcher tests against the real echo stdio MCP server.

Wires :class:`MCPHost` + :class:`ToolDispatcher` + :class:`AlwaysAllow`
against ``tests/fakes/echo_mcp_server.py`` (a real subprocess) and exercises
the happy-path ``mcp.tool.called`` and the failure-path ``mcp.tool.error``
event with the payload's ``error_type`` populated from the underlying
exception class.
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
from agentlabx.mcp.dispatcher import AlwaysAllow, ToolDispatcher
from agentlabx.mcp.host import MCPHost
from agentlabx.mcp.protocol import (
    MCPServerSpec,
    RegisteredServer,
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


async def test_dispatcher_resolve_invoke_emits_called_event(
    host: MCPHost, event_recorder: tuple[EventBus, list[Event]]
) -> None:
    bus, events = event_recorder
    started = await host.start(_registered(_echo_spec()), owner_id=None)
    try:
        dispatcher = ToolDispatcher(host, bus, AlwaysAllow())

        # echo declares its own capability override (`echo_speak`) via the
        # x-agentlabx-capabilities metadata key in inputSchema.
        server, tool = await dispatcher.resolve_capability("echo_speak", [started])
        assert server.id == started.id
        assert tool.tool_name == "echo"

        result = await dispatcher.invoke(
            stage="stageA",
            agent="agentA",
            capability="echo_speak",
            server_id=started.id,
            tool=tool.tool_name,
            args={"message": "hello-e2e"},
        )

        assert result.is_error is False
        called = [e for e in events if e.kind == "mcp.tool.called"]
        assert len(called) == 1
        payload = called[0].payload
        assert payload["server_id"] == started.id
        assert payload["tool"] == "echo"
        assert payload["capability"] == "echo_speak"
        assert payload["result_text"] == "hello-e2e"
        assert payload["args"] == {"message": "hello-e2e"}
    finally:
        await host.stop(started.id)


async def test_dispatcher_invoke_boom_emits_error_event_with_error_type(
    host: MCPHost, event_recorder: tuple[EventBus, list[Event]]
) -> None:
    bus, events = event_recorder
    started = await host.start(_registered(_echo_spec()), owner_id=None)
    try:
        dispatcher = ToolDispatcher(host, bus, AlwaysAllow())

        with pytest.raises(ToolExecutionFailed):
            await dispatcher.invoke(
                stage="stageA",
                agent="agentA",
                capability="default_cap",
                server_id=started.id,
                tool="boom",
                args={},
            )

        err = [e for e in events if e.kind == "mcp.tool.error"]
        assert len(err) == 1
        payload = err[0].payload
        assert payload["server_id"] == started.id
        assert payload["tool"] == "boom"
        assert payload["capability"] == "default_cap"
        assert "error_type" in payload
        # underlying exception class name surfaces verbatim
        error_type = payload["error_type"]
        assert isinstance(error_type, str)
        assert error_type  # non-empty
    finally:
        await host.stop(started.id)
