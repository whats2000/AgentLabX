"""Unit tests for :class:`ToolDispatcher` gating + tracing.

These tests use a hand-rolled :class:`FakeHost` (a structural stand-in for
:class:`MCPHost`) and a custom :class:`AllowListProvider` so the dispatcher
can be exercised in complete isolation from the MCP SDK and any real
subprocesses. The dispatcher itself only depends on the host's
``slot_values_for`` and ``call`` methods plus the event bus, so a duck-typed
fake (cast to ``MCPHost`` at the constructor boundary) is sufficient.
"""

from __future__ import annotations

from typing import cast

import pytest

from agentlabx.core.json_types import JSONValue
from agentlabx.events.bus import Event, EventBus
from agentlabx.mcp.dispatcher import (
    AllowListProvider,
    AlwaysAllow,
    ToolDispatcher,
)
from agentlabx.mcp.host import MCPHost
from agentlabx.mcp.protocol import (
    CapabilityRefused,
    CapabilityRequest,
    MCPServerSpec,
    RegisteredServer,
    Scope,
    TextContent,
    ToolCallResult,
    ToolDescriptor,
    ToolExecutionFailed,
)

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeHost:
    """Structural stand-in for :class:`MCPHost`.

    The dispatcher only invokes ``slot_values_for`` (sync) and ``call``
    (async), so we expose exactly those two methods. ``calls`` records every
    invocation for assertion. ``raise_on_call`` lets a test inject a
    ``ToolExecutionFailed`` to drive the error path.
    """

    def __init__(
        self,
        *,
        slot_values: tuple[str, ...] = (),
        result: ToolCallResult | None = None,
        raise_on_call: BaseException | None = None,
    ) -> None:
        self._slot_values = slot_values
        self._result = result or ToolCallResult(content=(), is_error=False, structured=None)
        self._raise = raise_on_call
        self.calls: list[tuple[str, str, dict[str, JSONValue]]] = []

    def slot_values_for(self, server_id: str) -> tuple[str, ...]:  # noqa: ARG002
        return self._slot_values

    async def call(self, server_id: str, tool: str, args: dict[str, JSONValue]) -> ToolCallResult:
        self.calls.append((server_id, tool, args))
        if self._raise is not None:
            raise self._raise
        return self._result


class DenyCapability:
    """Allow-list provider that denies one named capability and allows the rest."""

    def __init__(self, denied: str) -> None:
        self._denied = denied

    def allowed(self, request: CapabilityRequest) -> bool:
        return request.capability != self._denied


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _spec(name: str, scope: Scope = "admin") -> MCPServerSpec:
    return MCPServerSpec(
        name=name,
        scope=scope,
        transport="inprocess",
        command=None,
        url=None,
        inprocess_key=name,
        env_slot_refs=(),
        declared_capabilities=(),
    )


def _server(
    *,
    server_id: str,
    name: str,
    scope: Scope,
    tools: tuple[ToolDescriptor, ...],
) -> RegisteredServer:
    spec = _spec(name, scope=scope)
    return RegisteredServer(
        id=server_id,
        spec=spec,
        owner_id=None if scope == "admin" else "user-1",
        tools=tools,
        started_at=None,
    )


def _tool(*, server_name: str, tool_name: str, capabilities: tuple[str, ...]) -> ToolDescriptor:
    return ToolDescriptor(
        server_name=server_name,
        tool_name=tool_name,
        description="",
        input_schema={},
        capabilities=capabilities,
    )


def _record_bus() -> tuple[EventBus, list[Event]]:
    bus = EventBus()
    events: list[Event] = []

    async def _record(event: Event) -> None:
        events.append(event)

    bus.subscribe("*", _record)
    return bus, events


def _make_dispatcher(
    host: FakeHost, allow_list: AllowListProvider
) -> tuple[ToolDispatcher, EventBus, list[Event]]:
    bus, events = _record_bus()
    # ``ToolDispatcher`` only calls duck-typed methods on the host; the cast
    # is safe in the unit-test context where we deliberately avoid the MCP
    # SDK. Production code never goes through this path.
    dispatcher = ToolDispatcher(cast(MCPHost, host), bus, allow_list)
    return dispatcher, bus, events


# ---------------------------------------------------------------------------
# resolve_capability
# ---------------------------------------------------------------------------


async def test_resolve_capability_returns_first_admin_then_user_then_by_name() -> None:
    """Admin scope sorts before user; within scope, by name asc."""

    host = FakeHost()
    dispatcher, _, _ = _make_dispatcher(host, AlwaysAllow())

    admin_z = _server(
        server_id="z",
        name="zeta",
        scope="admin",
        tools=(_tool(server_name="zeta", tool_name="t", capabilities=("cap",)),),
    )
    admin_a = _server(
        server_id="a",
        name="alpha",
        scope="admin",
        tools=(_tool(server_name="alpha", tool_name="t", capabilities=("cap",)),),
    )
    user_a = _server(
        server_id="u",
        name="aaa",
        scope="user",
        tools=(_tool(server_name="aaa", tool_name="t", capabilities=("cap",)),),
    )

    server, tool = await dispatcher.resolve_capability("cap", [user_a, admin_z, admin_a])
    assert server.id == "a"  # alpha (admin, name asc) wins
    assert tool.tool_name == "t"


async def test_resolve_capability_no_match_raises_capability_refused() -> None:
    host = FakeHost()
    dispatcher, _, _ = _make_dispatcher(host, AlwaysAllow())
    with pytest.raises(CapabilityRefused) as exc_info:
        await dispatcher.resolve_capability("missing", [])
    assert exc_info.value.capability == "missing"
    # Sentinel: dispatcher resolve has no stage/agent context.
    assert exc_info.value.stage == ""
    assert exc_info.value.agent == ""


# ---------------------------------------------------------------------------
# invoke — gating
# ---------------------------------------------------------------------------


async def test_invoke_denied_emits_refused_event_and_raises() -> None:
    host = FakeHost()
    dispatcher, _, events = _make_dispatcher(host, DenyCapability("forbidden"))

    with pytest.raises(CapabilityRefused) as exc_info:
        await dispatcher.invoke(
            stage="stage-1",
            agent="agent-x",
            capability="forbidden",
            server_id="srv",
            tool="tool",
            args={},
        )

    assert exc_info.value.stage == "stage-1"
    assert exc_info.value.agent == "agent-x"
    assert exc_info.value.capability == "forbidden"

    # Host must NOT have been called.
    assert host.calls == []

    refused = [e for e in events if e.kind == "mcp.tool.refused"]
    assert len(refused) == 1
    payload = refused[0].payload
    assert payload == {
        "stage": "stage-1",
        "agent": "agent-x",
        "capability": "forbidden",
        "server_id": "srv",
        "tool": "tool",
    }


async def test_invoke_allowed_emits_called_with_redacted_args() -> None:
    host = FakeHost(
        result=ToolCallResult(content=(TextContent(text="ok"),), is_error=False, structured=None),
    )
    dispatcher, _, events = _make_dispatcher(host, AlwaysAllow())

    args: dict[str, JSONValue] = {"prompt": "hello", "api_key": "sk-secret-123"}
    result = await dispatcher.invoke(
        stage="stage-1",
        agent="agent-x",
        capability="cap",
        server_id="srv",
        tool="tool",
        args=args,
    )

    assert isinstance(result.content[0], TextContent)
    assert result.content[0].text == "ok"

    # Host received the *unredacted* args (it needs the real key to call out).
    assert host.calls == [("srv", "tool", {"prompt": "hello", "api_key": "sk-secret-123"})]

    called = [e for e in events if e.kind == "mcp.tool.called"]
    assert len(called) == 1
    payload = called[0].payload
    assert payload["args"] == {"prompt": "hello", "api_key": "***"}
    assert payload["result_text"] == "ok"
    assert payload["stage"] == "stage-1"
    assert payload["agent"] == "agent-x"
    assert payload["capability"] == "cap"
    assert payload["server_id"] == "srv"
    assert payload["tool"] == "tool"


async def test_invoke_allowed_redacts_slot_values_in_result_text() -> None:
    host = FakeHost(
        slot_values=("super-secret-token",),
        result=ToolCallResult(
            content=(
                TextContent(text="leaked super-secret-token in line one"),
                TextContent(text="and again: super-secret-token"),
            ),
            is_error=False,
            structured=None,
        ),
    )
    dispatcher, _, events = _make_dispatcher(host, AlwaysAllow())

    await dispatcher.invoke(
        stage="s",
        agent="a",
        capability="c",
        server_id="srv",
        tool="t",
        args={},
    )

    called = [e for e in events if e.kind == "mcp.tool.called"]
    assert len(called) == 1
    text = called[0].payload["result_text"]
    assert isinstance(text, str)
    assert "super-secret-token" not in text
    assert text.count("***") == 2


async def test_invoke_tool_execution_failed_emits_error_event_and_reraises() -> None:
    underlying = ValueError("kaboom")
    host = FakeHost(raise_on_call=ToolExecutionFailed("srv", "tool", underlying))
    dispatcher, _, events = _make_dispatcher(host, AlwaysAllow())

    with pytest.raises(ToolExecutionFailed):
        await dispatcher.invoke(
            stage="s",
            agent="a",
            capability="c",
            server_id="srv",
            tool="tool",
            args={"token": "abc"},
        )

    err = [e for e in events if e.kind == "mcp.tool.error"]
    assert len(err) == 1
    payload = err[0].payload
    assert payload["error_type"] == "ValueError"
    assert payload["args"] == {"token": "***"}
    # No traceback / underlying message in the payload.
    assert "kaboom" not in str(payload)
