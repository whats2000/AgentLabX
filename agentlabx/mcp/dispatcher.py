"""ToolDispatcher — capability-gated tool invocation with event tracing.

The dispatcher is the *only* path from a stage / agent to an MCP tool. It:

1. Resolves a requested capability to a concrete ``(server, tool)`` pair from
   a caller-supplied ``visible_servers`` set (the dispatcher itself never
   consults the registry — that keeps it pure for unit testing and lets the
   caller apply per-user / per-scope visibility upstream).
2. Checks the per-stage / per-agent allow-list via an
   :class:`AllowListProvider`. Stage A3 ships :class:`AlwaysAllow` as the
   no-op provider; Stage A8 will wire the real per-stage allow-list with a
   one-line constructor swap.
3. Invokes the tool through :class:`agentlabx.mcp.host.MCPHost`, passing
   ``args`` straight through.
4. Emits ``mcp.tool.refused`` / ``mcp.tool.called`` / ``mcp.tool.error``
   events on the bus with both argument-key and slot-value redaction
   applied to the payload before it leaves the dispatcher.

Pure dispatcher: the only side effects are the host call and the bus emit.
The dispatcher does not own the registry, does not own a session pool, and
does not log directly.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol, runtime_checkable

from agentlabx.core.json_types import JSONValue
from agentlabx.events.bus import Event, EventBus
from agentlabx.mcp.host import MCPHost
from agentlabx.mcp.protocol import (
    CapabilityRefused,
    CapabilityRequest,
    RegisteredServer,
    TextContent,
    ToolCallResult,
    ToolDescriptor,
    ToolExecutionFailed,
)
from agentlabx.mcp.redaction import redact_args, redact_text

# ---------------------------------------------------------------------------
# Allow-list seam — A8 will inject the real per-stage / per-agent provider.
# ---------------------------------------------------------------------------


@runtime_checkable
class AllowListProvider(Protocol):
    """Sync gate: returns ``True`` iff the request is permitted.

    Kept synchronous on purpose — A8 will back this with an in-memory map
    populated from the stage config. Anything that needs I/O belongs upstream,
    not here.
    """

    def allowed(self, request: CapabilityRequest) -> bool: ...


class AlwaysAllow:
    """A3 default: permits every request.

    Stage A8 swaps this for a config-driven implementation that consults the
    declared ``capabilities`` of the calling stage.
    """

    def allowed(self, request: CapabilityRequest) -> bool:  # noqa: ARG002
        return True


# ---------------------------------------------------------------------------
# Resolution helpers
# ---------------------------------------------------------------------------


def _resolution_sort_key(server: RegisteredServer) -> tuple[int, str]:
    # admin scope sorts before user scope (0 < 1); within a scope, by name.
    scope_rank = 0 if server.spec.scope == "admin" else 1
    return (scope_rank, server.spec.name)


# ---------------------------------------------------------------------------
# ToolDispatcher
# ---------------------------------------------------------------------------


class ToolDispatcher:
    """Capability-gated tool invocation surface backed by :class:`MCPHost`."""

    def __init__(
        self,
        host: MCPHost,
        event_bus: EventBus,
        allow_list_provider: AllowListProvider,
    ) -> None:
        self._host = host
        self._event_bus = event_bus
        self._allow_list = allow_list_provider

    # ------------------------------------------------------------------
    # Capability resolution
    # ------------------------------------------------------------------

    async def resolve_capability(
        self,
        capability: str,
        visible_servers: Iterable[RegisteredServer],
    ) -> tuple[RegisteredServer, ToolDescriptor]:
        """Return the first ``(server, tool)`` advertising ``capability``.

        Deterministic ordering: admin-scope servers sort before user-scope
        servers, and within a scope servers are sorted by name ascending.
        Within a server, tools are scanned in their snapshot order. Raises
        :class:`CapabilityRefused` (with ``stage=""`` / ``agent=""`` sentinels
        — the dispatcher caller does not have stage/agent context at resolve
        time) if no server provides the capability.
        """

        for server in sorted(visible_servers, key=_resolution_sort_key):
            for tool in server.tools:
                if capability in tool.capabilities:
                    return server, tool
        raise CapabilityRefused(stage="", agent="", capability=capability)

    # ------------------------------------------------------------------
    # Invocation
    # ------------------------------------------------------------------

    async def invoke(
        self,
        stage: str,
        agent: str,
        capability: str,
        server_id: str,
        tool: str,
        args: dict[str, JSONValue],
    ) -> ToolCallResult:
        """Run a single tool call through the gate, host, and event bus."""

        request = CapabilityRequest(stage_name=stage, agent_name=agent, capability=capability)
        redacted_args = redact_args(args)

        if not self._allow_list.allowed(request):
            await self._event_bus.emit(
                Event(
                    kind="mcp.tool.refused",
                    payload={
                        "stage": stage,
                        "agent": agent,
                        "capability": capability,
                        "server_id": server_id,
                        "tool": tool,
                    },
                )
            )
            raise CapabilityRefused(stage=stage, agent=agent, capability=capability)

        # ``slot_values_for`` propagates ``ServerNotRunning`` to the caller —
        # the dispatcher does not catch it; the host's preconditions are the
        # caller's responsibility.
        slot_values = self._host.slot_values_for(server_id)

        try:
            result = await self._host.call(server_id, tool, args)
        except ToolExecutionFailed as exc:
            await self._event_bus.emit(
                Event(
                    kind="mcp.tool.error",
                    payload={
                        "stage": stage,
                        "agent": agent,
                        "capability": capability,
                        "server_id": server_id,
                        "tool": tool,
                        "args": redacted_args,
                        "error_type": type(exc.underlying).__name__,
                    },
                )
            )
            raise

        result_text = "\n".join(c.text for c in result.content if isinstance(c, TextContent))
        redacted_text = redact_text(result_text, slot_values)
        await self._event_bus.emit(
            Event(
                kind="mcp.tool.called",
                payload={
                    "stage": stage,
                    "agent": agent,
                    "capability": capability,
                    "server_id": server_id,
                    "tool": tool,
                    "args": redacted_args,
                    "result_text": redacted_text,
                },
            )
        )
        return result


__all__ = [
    "AllowListProvider",
    "AlwaysAllow",
    "ToolDispatcher",
]
