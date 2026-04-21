"""MCPHost — owns running MCP server handles, lifecycle, and tool snapshots.

The host is the only module that touches the MCP SDK's ``CallToolResult`` /
``Tool`` types. Downstream consumers (dispatcher, REST router, tests) only
ever see AgentLabX-native types from :mod:`agentlabx.mcp.protocol`.

Lifecycle, in one paragraph: :meth:`start` builds an
:class:`contextlib.AsyncExitStack`, enters the appropriate launcher's
context manager on the stack (which yields a live
:class:`mcp.ClientSession`), calls ``session.list_tools()``, snapshots the
descriptors with capabilities mapped per Step 4 of the A3 plan, stores the
stack + session in :attr:`_handles`, emits ``mcp.server.started``, and
returns a fresh :class:`RegisteredServer` with ``tools`` filled. :meth:`stop`
just ``await``s :meth:`AsyncExitStack.aclose` on the stored stack, which
tears down the session, the launcher, and any subprocess in dependency
order, then emits ``mcp.server.stopped``.
"""

from __future__ import annotations

import asyncio
import contextlib
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone

from mcp import ClientSession
from mcp.shared.exceptions import McpError
from mcp.types import (
    CallToolResult,
    ContentBlock,
    EmbeddedResource,
)
from mcp.types import (
    ImageContent as MCPImageContent,
)
from mcp.types import (
    TextContent as MCPTextContent,
)
from mcp.types import (
    TextResourceContents as MCPTextResourceContents,
)
from mcp.types import (
    Tool as MCPTool,
)

from agentlabx.core.json_types import JSONValue
from agentlabx.events.bus import Event, EventBus
from agentlabx.mcp.protocol import (
    ImageContent,
    MCPServerSpec,
    RegisteredServer,
    ResourceRefContent,
    ServerNotRunning,
    ServerStartupFailed,
    TextContent,
    ToolCallResult,
    ToolContentItem,
    ToolDescriptor,
    ToolExecutionFailed,
    ToolNotFound,
)
from agentlabx.mcp.registry import ServerRegistry
from agentlabx.mcp.transport import (
    InProcessLauncher,
    ServerFactory,
    StdioLauncher,
    StreamableHTTPLauncher,
    TransportOpenFailed,
)
from agentlabx.security.slot_resolver import SlotResolver

# ---------------------------------------------------------------------------
# Capability-mapping convention
# ---------------------------------------------------------------------------
#
# Each tool's ``inputSchema`` may carry an ``x-agentlabx-capabilities`` key
# whose value is a JSON list of strings. When present, that list overrides
# the server's ``declared_capabilities`` for the specific tool. When absent,
# the tool inherits the union of the server's declared caps.
#
# Verified at A3 Task 5 implementation time: the ``mcp`` SDK declares
# ``Tool.inputSchema: dict[str, Any]`` and round-trips arbitrary keys
# verbatim through ``tools/list``. The metadata key mechanism is therefore
# the canonical override path; the name-prefix fallback contemplated in the
# plan is not needed.

CAPABILITY_METADATA_KEY = "x-agentlabx-capabilities"

# Sanitiser shared with ``SlotResolver``'s admin-scope env-var path so that a
# slot ``foo:bar`` resolves consistently whether the source is the
# admin_configs row or the launched subprocess's environment.
_SLOT_ENV_SANITISE = re.compile(r"[^A-Z0-9_]")


def slot_to_env_var(slot: str) -> str:
    """Map a slot name to its conventional ``AGENTLABX_SLOT_<UPPER>`` env-var."""

    return f"AGENTLABX_SLOT_{_SLOT_ENV_SANITISE.sub('_', slot.upper())}"


@dataclass(slots=True)
class _Handle:
    """Internal per-server runtime state held by :class:`MCPHost`."""

    session: ClientSession
    tools: tuple[ToolDescriptor, ...]
    exit_stack: contextlib.AsyncExitStack
    slot_values: tuple[str, ...]


class MCPHost:
    """Owns the live :class:`ClientSession` for every running MCP server."""

    def __init__(
        self,
        registry: ServerRegistry,
        slot_resolver: SlotResolver,
        event_bus: EventBus,
        inprocess_factories: Mapping[str, ServerFactory],
    ) -> None:
        self._registry = registry
        self._slot_resolver = slot_resolver
        self._event_bus = event_bus
        # Shared reference: extending this mapping at the construction site
        # makes new bundles available to all subsequent in-process launches.
        self._inprocess_factories: Mapping[str, ServerFactory] = inprocess_factories
        self._handles: dict[str, _Handle] = {}
        # Per-server-id locks serialise concurrent ``start`` attempts on the
        # same id, preventing the race where two callers both pass the
        # ``server.id in self._handles`` guard, both spawn subprocesses, and
        # the second to finish silently overwrites the first — orphaning it.
        # Lock entries are intentionally retained after start completes;
        # they're tiny and reusing the same lock on a future start (after a
        # ``stop``) is harmless.
        self._start_locks: dict[str, asyncio.Lock] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self, server: RegisteredServer, owner_id: str | None) -> RegisteredServer:
        """Boot ``server``, snapshot its tools, and return an updated record.

        On any failure the partially-built ``AsyncExitStack`` is rolled back
        before re-raising, so a failed start never leaves a half-initialised
        subprocess or open transport behind.
        """

        lock = self._start_locks.setdefault(server.id, asyncio.Lock())
        async with lock:
            return await self._start_locked(server=server, owner_id=owner_id)

    async def _start_locked(
        self, *, server: RegisteredServer, owner_id: str | None
    ) -> RegisteredServer:
        if server.id in self._handles:
            raise ServerStartupFailed(
                spec=server.spec,
                reason=f"server {server.spec.name!r} is already running",
            )

        resolved_by_slot = await self._resolve_slot_map(spec=server.spec, owner_id=owner_id)
        # ``slot_values`` preserves spec-declared order so callers using it
        # for redaction get a stable, deterministic tuple.
        slot_values: tuple[str, ...] = tuple(
            resolved_by_slot[slot] for slot in server.spec.env_slot_refs if slot in resolved_by_slot
        )
        env: dict[str, str] = {
            slot_to_env_var(slot): value for slot, value in resolved_by_slot.items()
        }

        stack = contextlib.AsyncExitStack()
        try:
            session = await self._open_session(spec=server.spec, env=env, stack=stack)
            list_result = await session.list_tools()
            tools = self._snapshot_tools(server.spec, list_result.tools)
        except ServerStartupFailed:
            await stack.aclose()
            raise
        except (McpError, OSError, ValueError) as exc:
            await stack.aclose()
            raise ServerStartupFailed(
                spec=server.spec,
                reason=f"tools/list failed after open: {exc!r}",
            ) from exc
        except BaseException:
            # Includes ``CancelledError`` and any unexpected error; ensure
            # the stack is torn down before propagating.
            await stack.aclose()
            raise

        self._handles[server.id] = _Handle(
            session=session,
            tools=tools,
            exit_stack=stack,
            slot_values=slot_values,
        )

        await self._event_bus.emit(
            Event(
                kind="mcp.server.started",
                payload={
                    "server_id": server.id,
                    "server_name": server.spec.name,
                    "transport": server.spec.transport,
                    "tool_count": len(tools),
                },
            )
        )

        return RegisteredServer(
            id=server.id,
            spec=server.spec,
            owner_id=server.owner_id,
            tools=tools,
            started_at=datetime.now(tz=timezone.utc),
        )

    async def stop(self, server_id: str) -> None:
        """Stop a running server and release its transport / subprocess."""

        handle = self._handles.pop(server_id, None)
        if handle is None:
            raise ServerNotRunning(server_id)
        # ``aclose`` walks the stack in reverse-entry order: session first,
        # then launcher, then any subprocess wrapper.
        await handle.exit_stack.aclose()
        await self._event_bus.emit(
            Event(
                kind="mcp.server.stopped",
                payload={"server_id": server_id},
            )
        )

    async def stop_all(self) -> None:
        """Graceful shutdown helper — stops every live handle.

        Failures are tolerated: each ``stop`` is awaited concurrently and a
        single broken handle (e.g. an ``aclose`` that raises) cannot abort
        teardown of the remaining handles. Per-handle failures are surfaced
        as ``mcp.server.stop_failed`` events so operators retain visibility.
        """

        server_ids = list(self._handles.keys())
        results = await asyncio.gather(
            *(self.stop(sid) for sid in server_ids),
            return_exceptions=True,
        )
        for sid, outcome in zip(server_ids, results, strict=True):
            if isinstance(outcome, BaseException) and not isinstance(outcome, ServerNotRunning):
                await self._event_bus.emit(
                    Event(
                        kind="mcp.server.stop_failed",
                        payload={
                            "server_id": sid,
                            "error_type": type(outcome).__name__,
                            "reason": str(outcome),
                        },
                    )
                )

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def tools_for(self, server_id: str) -> tuple[ToolDescriptor, ...]:
        """Return the snapshotted tool list for a running server."""

        handle = self._handles.get(server_id)
        if handle is None:
            raise ServerNotRunning(server_id)
        return handle.tools

    def slot_values_for(self, server_id: str) -> tuple[str, ...]:
        """Return the decrypted slot values currently in flight for a server.

        Used by :class:`agentlabx.mcp.dispatcher.ToolDispatcher` to scrub
        result text before emitting tool-result events.
        """

        handle = self._handles.get(server_id)
        if handle is None:
            raise ServerNotRunning(server_id)
        return handle.slot_values

    # ------------------------------------------------------------------
    # Tool invocation
    # ------------------------------------------------------------------

    async def call(
        self,
        server_id: str,
        tool: str,
        args: dict[str, JSONValue],
    ) -> ToolCallResult:
        """Invoke a tool and adapt the SDK result into AgentLabX types."""

        handle = self._handles.get(server_id)
        if handle is None:
            raise ServerNotRunning(server_id)

        if not any(t.tool_name == tool for t in handle.tools):
            raise ToolNotFound(server_id, tool)

        # SDK's call_tool signature accepts ``dict[str, Any]``; our
        # JSONValue mapping is a strict subset of that, so the call is sound.
        try:
            sdk_result = await handle.session.call_tool(tool, args)
        except McpError as exc:
            raise ToolExecutionFailed(server_id, tool, exc) from exc
        except Exception as exc:  # noqa: BLE001 — wrap-and-rethrow contract
            raise ToolExecutionFailed(server_id, tool, exc) from exc

        # SDK convention: server-side exceptions are *not* re-raised on the
        # client; instead the SDK returns a ``CallToolResult`` with
        # ``isError=True`` whose content carries the exception text. Surface
        # that as ``ToolExecutionFailed`` so the dispatcher's
        # ``mcp.tool.error`` event always fires on a failed invocation,
        # regardless of which side caught the original exception.
        if sdk_result.isError:
            reason = _extract_error_text(sdk_result) or "tool reported isError=True"
            raise ToolExecutionFailed(server_id, tool, RuntimeError(reason))

        return _adapt_call_result(sdk_result)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _open_session(
        self,
        *,
        spec: MCPServerSpec,
        env: Mapping[str, str],
        stack: contextlib.AsyncExitStack,
    ) -> ClientSession:
        try:
            if spec.transport == "stdio":
                if spec.command is None:
                    raise ServerStartupFailed(
                        spec=spec, reason="stdio transport requires a command"
                    )
                launcher_cm = StdioLauncher(spec.command, env).open()
            elif spec.transport == "http":
                if spec.url is None:
                    raise ServerStartupFailed(spec=spec, reason="http transport requires a url")
                # HTTP launcher uses headers, not env. Slot values flow in via
                # the ``Authorization`` / bundle-defined headers in a future
                # task; for A3 the spec carries no header template, so we pass
                # an empty mapping. (Bundle-level header templating is Task 9.)
                launcher_cm = StreamableHTTPLauncher(spec.url, {}).open()
            elif spec.transport == "inprocess":
                if spec.inprocess_key is None:
                    raise ServerStartupFailed(
                        spec=spec,
                        reason="inprocess transport requires an inprocess_key",
                    )
                launcher_cm = InProcessLauncher(
                    spec.inprocess_key, self._inprocess_factories
                ).open()
            else:  # pragma: no cover — Transport literal exhausted above
                raise ServerStartupFailed(
                    spec=spec,
                    reason=f"unsupported transport {spec.transport!r}",
                )
            session = await stack.enter_async_context(launcher_cm)
        except TransportOpenFailed as exc:
            raise ServerStartupFailed(spec=spec, reason=str(exc)) from exc
        return session

    async def _resolve_slot_map(
        self, *, spec: MCPServerSpec, owner_id: str | None
    ) -> dict[str, str]:
        """Resolve declared env_slot_refs into a {slot_name: value} mapping.

        Slots whose resolver returns ``None`` are omitted entirely (the
        corresponding env var is left unset) — this matches the convention
        documented for :class:`SlotResolver`.
        """

        resolved: dict[str, str] = {}
        for slot in spec.env_slot_refs:
            value = await self._slot_resolver.resolve(owner_id=owner_id, slot=slot)
            if value is not None:
                resolved[slot] = value
        return resolved

    def _snapshot_tools(
        self,
        spec: MCPServerSpec,
        sdk_tools: list[MCPTool],
    ) -> tuple[ToolDescriptor, ...]:
        descriptors: list[ToolDescriptor] = []
        for tool in sdk_tools:
            schema = _coerce_input_schema(tool.inputSchema)
            capabilities = _per_tool_capabilities(
                server_caps=spec.declared_capabilities,
                tool_schema=schema,
            )
            descriptors.append(
                ToolDescriptor(
                    server_name=spec.name,
                    tool_name=tool.name,
                    description=tool.description or "",
                    input_schema=schema,
                    capabilities=capabilities,
                )
            )
        return tuple(descriptors)


# ---------------------------------------------------------------------------
# Capability mapping
# ---------------------------------------------------------------------------


def _per_tool_capabilities(
    *,
    server_caps: tuple[str, ...],
    tool_schema: dict[str, JSONValue],
) -> tuple[str, ...]:
    """Return the effective capabilities for a tool.

    If the tool's ``inputSchema`` carries ``x-agentlabx-capabilities`` (a
    list of strings), that list **overrides** the server-level declaration.
    Otherwise the tool inherits the server's declared capabilities verbatim.
    Unknown / malformed override values fall back to the server caps so a
    misconfigured bundle cannot accidentally widen the gate.
    """

    raw = tool_schema.get(CAPABILITY_METADATA_KEY)
    if raw is None:
        return tuple(server_caps)
    if not isinstance(raw, list):
        return tuple(server_caps)
    overrides: list[str] = []
    for item in raw:
        if isinstance(item, str):
            overrides.append(item)
    if not overrides:
        return tuple(server_caps)
    return tuple(overrides)


# ---------------------------------------------------------------------------
# SDK result adaptation
# ---------------------------------------------------------------------------


def _extract_error_text(result: CallToolResult) -> str | None:
    """Return the first text content of an error result, if any."""

    for entry in result.content:
        if isinstance(entry, MCPTextContent):
            return entry.text
    return None


def _adapt_call_result(result: CallToolResult) -> ToolCallResult:
    items: list[ToolContentItem] = []
    for entry in result.content:
        items.append(_adapt_content_item(entry))
    structured: dict[str, JSONValue] | None = None
    if result.structuredContent is not None:
        structured = _coerce_json_dict(result.structuredContent)
    return ToolCallResult(
        content=tuple(items),
        is_error=bool(result.isError),
        structured=structured,
    )


def _adapt_content_item(entry: ContentBlock) -> ToolContentItem:
    # The SDK's ``ContentBlock`` union is wider (AudioContent, ResourceLink)
    # than the three variants AgentLabX surfaces today. We accept the SDK
    # union here and rely on the explicit ``isinstance`` chain to raise on
    # any other variant the SDK may hand us at runtime — which keeps the
    # signature precise (no ``object`` placeholder) while still narrowing
    # safely against future SDK additions.
    if isinstance(entry, MCPTextContent):
        return TextContent(text=entry.text)
    if isinstance(entry, MCPImageContent):
        return ImageContent(data=entry.data, mime_type=entry.mimeType)
    if isinstance(entry, EmbeddedResource):
        resource = entry.resource
        uri_obj = resource.uri
        # ``AnyUrl`` from pydantic — cast to its string form for the public
        # AgentLabX value type.
        uri_str = str(uri_obj)
        mime_type = resource.mimeType if isinstance(resource, MCPTextResourceContents) else None
        return ResourceRefContent(uri=uri_str, mime_type=mime_type)
    raise ValueError(f"unsupported MCP content item type: {type(entry).__name__}")


# ---------------------------------------------------------------------------
# JSON coercion helpers
# ---------------------------------------------------------------------------


def _coerce_input_schema(schema: object) -> dict[str, JSONValue]:
    """Coerce the SDK's loosely-typed input schema into our strict JSONValue map."""

    if not isinstance(schema, dict):
        return {}
    return _coerce_json_dict(schema)


def _coerce_json_dict(value: object) -> dict[str, JSONValue]:
    if not isinstance(value, dict):
        raise ValueError(f"expected dict, got {type(value).__name__}")
    out: dict[str, JSONValue] = {}
    for key, raw in value.items():
        if not isinstance(key, str):
            raise ValueError(f"expected str dict key, got {type(key).__name__}")
        out[key] = _coerce_json_value(raw)
    return out


def _coerce_json_value(value: object) -> JSONValue:
    if value is None or isinstance(value, str | bool | int | float):
        return value
    if isinstance(value, dict):
        return _coerce_json_dict(value)
    if isinstance(value, list | tuple):
        return [_coerce_json_value(item) for item in value]
    # Fallback: stringify unknown payloads (e.g. pydantic URLs) so we never
    # leak a non-JSONValue through the typed boundary.
    return str(value)


__all__ = [
    "CAPABILITY_METADATA_KEY",
    "MCPHost",
    "slot_to_env_var",
]
