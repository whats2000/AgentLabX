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

import asyncio
import contextlib
import sys
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from agentlabx.db.schema import Base
from agentlabx.db.session import DatabaseHandle
from agentlabx.events.bus import Event, EventBus
from agentlabx.mcp.host import MCPHost, _Handle
from agentlabx.mcp.protocol import (
    MCPServerSpec,
    RegisteredServer,
    ServerNotRunning,
    ServerStartupFailed,
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


# ---------------------------------------------------------------------------
# Concurrent-start race regression (reviewer I-2)
# ---------------------------------------------------------------------------


async def test_concurrent_start_same_id_only_one_wins(
    host: MCPHost, event_recorder: tuple[EventBus, list[Event]]
) -> None:
    """Two ``start`` calls racing on the same id: one wins, one raises.

    Without the per-id lock both calls would pass the ``id in _handles``
    guard, both would spawn subprocesses, and the second to finish would
    overwrite the dict slot — orphaning the first subprocess. With the
    lock, exactly one ``start`` succeeds, the other raises
    ``ServerStartupFailed``, and the host's ``_handles`` slot reflects the
    winner. We also assert ``mcp.server.started`` was emitted exactly once.
    """

    _, events = event_recorder
    record = _registered(_echo_spec())

    # We deliberately keep the WINNING start in the test's own task (so its
    # anyio-backed exit scope can be cleanly torn down later from the same
    # task). The LOSING start is dispatched as a background task. Both
    # contend on the per-id lock; the loser must observe the handle slot
    # already filled and raise ``ServerStartupFailed``.
    loser_task: asyncio.Task[RegisteredServer] = asyncio.create_task(
        host.start(record, owner_id=None)
    )
    # Yield once so the loser_task gets a chance to acquire the lock first
    # if scheduling allows, then call start ourselves.
    await asyncio.sleep(0)
    winner_outcome: RegisteredServer | BaseException
    try:
        winner_outcome = await host.start(record, owner_id=None)
    except ServerStartupFailed as exc:
        winner_outcome = exc

    loser_outcome: RegisteredServer | BaseException
    try:
        loser_outcome = await loser_task
    except ServerStartupFailed as exc:
        loser_outcome = exc

    outcomes = [winner_outcome, loser_outcome]
    successes = [r for r in outcomes if isinstance(r, RegisteredServer)]
    failures = [r for r in outcomes if isinstance(r, BaseException)]

    # Determine which call won, so we can stop it from the same task that
    # started it (anyio cancel scopes are task-affine).
    winner_won = isinstance(winner_outcome, RegisteredServer)

    try:
        assert len(successes) == 1, f"expected exactly one success, got {outcomes!r}"
        assert len(failures) == 1, f"expected exactly one failure, got {outcomes!r}"
        assert isinstance(failures[0], ServerStartupFailed)
        winner = successes[0]
        assert host._handles[winner.id].tools == winner.tools  # noqa: SLF001
        # Only one ``mcp.server.started`` was emitted — the loser never
        # launched a subprocess.
        started_events = [e for e in events if e.kind == "mcp.server.started"]
        assert len(started_events) == 1
    finally:
        if winner_won:
            # Safe to stop from the test task.
            await host.stop(successes[0].id)
        # If the background task won, we cannot cleanly aclose its anyio
        # scope from this task. Drop the handle so other tests don't see
        # leftover state; the subprocess will be reaped by GC / process
        # exit. (In practice the test's first-to-acquire-the-lock is
        # almost always the test task because of the ``await sleep(0)``
        # above, so this branch is rarely taken.)
        elif successes:
            host._handles.pop(successes[0].id, None)  # noqa: SLF001


# ---------------------------------------------------------------------------
# stop_all fault-tolerance (reviewer I-3)
# ---------------------------------------------------------------------------


async def test_stop_all_tolerates_broken_handle_and_emits_stop_failed(
    host: MCPHost, event_recorder: tuple[EventBus, list[Event]]
) -> None:
    """``stop_all`` must not abort on a single broken ``aclose``.

    We install three synthetic handles (no real subprocesses) so this test
    stays deterministic and avoids anyio cancel-scope task-affinity quirks
    that come with real stdio sessions. One handle's ``aclose`` raises;
    the other two close cleanly. ``stop_all`` must (a) not propagate the
    failure, (b) still tear down the healthy handles, and (c) emit a
    ``mcp.server.stop_failed`` event for the broken one.
    """

    _, events = event_recorder

    @contextlib.asynccontextmanager
    async def _raises_on_exit() -> AsyncIterator[None]:
        try:
            yield None
        finally:
            raise RuntimeError("synthetic aclose failure")

    @contextlib.asynccontextmanager
    async def _clean() -> AsyncIterator[None]:
        yield None

    async def _install(name: str, *, broken: bool) -> None:
        stack = contextlib.AsyncExitStack()
        await stack.enter_async_context(_raises_on_exit() if broken else _clean())
        host._handles[name] = _Handle(  # noqa: SLF001
            session=None,  # type: ignore[arg-type]
            tools=(),
            exit_stack=stack,
            slot_values=(),
        )

    await _install("healthy-a", broken=False)
    await _install("broken", broken=True)
    await _install("healthy-b", broken=False)

    # Must not raise.
    await host.stop_all()

    # All handles removed from the registry.
    assert host._handles == {}  # noqa: SLF001

    # The broken handle produced exactly one stop_failed event with the
    # expected error metadata. Healthy handles produced ``mcp.server.stopped``.
    stop_failed = [e for e in events if e.kind == "mcp.server.stop_failed"]
    stopped = [e for e in events if e.kind == "mcp.server.stopped"]
    assert len(stop_failed) == 1
    assert {e.payload["server_id"] for e in stopped} == {"healthy-a", "healthy-b"}

    payload = stop_failed[0].payload
    assert payload["server_id"] == "broken"
    assert payload["error_type"] == "RuntimeError"
    reason = payload["reason"]
    assert isinstance(reason, str)
    assert "synthetic aclose failure" in reason


async def test_stop_all_completes_with_no_handles(host: MCPHost) -> None:
    """Empty ``stop_all`` is a no-op and never raises."""

    await host.stop_all()  # no exception


# ---------------------------------------------------------------------------
# "Not running" coverage (reviewer M-6)
# ---------------------------------------------------------------------------


async def test_call_unknown_server_raises_not_running(host: MCPHost) -> None:
    with pytest.raises(ServerNotRunning):
        await host.call("nonexistent", "x", {})


def test_tools_for_unknown_server_raises_not_running(host: MCPHost) -> None:
    with pytest.raises(ServerNotRunning):
        host.tools_for("nonexistent")


def test_slot_values_for_unknown_server_raises_not_running(host: MCPHost) -> None:
    with pytest.raises(ServerNotRunning):
        host.slot_values_for("nonexistent")


async def test_stop_unknown_server_raises_not_running(host: MCPHost) -> None:
    with pytest.raises(ServerNotRunning):
        await host.stop("nonexistent")
