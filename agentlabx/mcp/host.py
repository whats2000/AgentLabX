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
import math
import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone

import anyio
from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream
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


def _flatten_exception_group(group: BaseExceptionGroup[BaseException]) -> Iterator[BaseException]:
    """Yield leaf exceptions from a (possibly nested) ``BaseExceptionGroup``.

    anyio task groups frequently nest groups several levels deep when a child
    fails while another is mid-await. Walking the tree to a leaf gives the
    router a useful ``transport open failed: McpError(...)`` reason instead
    of the recursive group repr.
    """

    for child in group.exceptions:
        if isinstance(child, BaseExceptionGroup):
            yield from _flatten_exception_group(child)
        else:
            yield child


# Type alias for the single-shot result channel a caller hands to the owner
# task. The owner sends exactly one item — either an SDK :class:`CallToolResult`
# or the exception raised inside ``session.call_tool`` — then closes the send
# end. The caller's ``async with`` over the receive end disposes the channel
# either way. The buffer size is 1 so the owner's send never has to wait.
_CallResult = CallToolResult | BaseException


@dataclass(slots=True)
class _CallRequest:
    """A queued ``call_tool`` request waiting for owner-task execution.

    ``result_send`` is an anyio memory-object send stream created on the
    caller's task. The owner task sends exactly one :class:`CallToolResult`
    or :class:`BaseException` into it, then closes it. Anyio memory-object
    streams traverse Starlette's per-request task-group boundary correctly,
    which an :class:`asyncio.Future` does not — that mismatch is what made
    in-process MCP invokes hang under live Uvicorn even though the
    pure-ASGI test client worked.

    Routing every invocation through the owner task is still required
    because the MCP SDK's :class:`ClientSession` wraps anyio memory-object
    streams whose cancel scopes are bound to the task that opened them.
    """

    tool: str
    args: dict[str, JSONValue]
    result_send: MemoryObjectSendStream[_CallResult]


@dataclass(slots=True)
class _Handle:
    """Internal per-server runtime state held by :class:`MCPHost`.

    ``owner_task`` is the dedicated background task that opened the session
    and owns its ``AsyncExitStack``. All teardown happens inside that task
    via ``stop_event`` to avoid anyio cancel-scope task-affinity errors —
    cancel scopes raised by stdio / in-process launchers must be exited in
    the same task that entered them, which is the owner task by construction.

    ``call_send`` is the cross-task hand-off used by :meth:`MCPHost.call`:
    callers send a :class:`_CallRequest` (which carries its own single-shot
    result-receive stream) into this anyio send stream, while the owner task
    receives requests on the paired receive end and runs ``session.call_tool``
    from its own task context (where the underlying SDK streams were created).

    ``exit_stack`` is retained for the synthetic-handle test path
    (``test_stop_all_tolerates_broken_handle``) which installs handles
    without an owner task; ``stop`` falls back to closing the stack
    directly when ``owner_task`` is ``None``.
    """

    session: ClientSession
    tools: tuple[ToolDescriptor, ...]
    exit_stack: contextlib.AsyncExitStack
    slot_values: tuple[str, ...]
    owner_task: asyncio.Task[None] | None = None
    stop_event: anyio.Event | None = None
    call_send: MemoryObjectSendStream[_CallRequest] | None = None


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
        slot_values: tuple[str, ...] = tuple(
            resolved_by_slot[slot] for slot in server.spec.env_slot_refs if slot in resolved_by_slot
        )
        # Honour per-slot env-var overrides declared by the bundle (e.g.
        # semantic_scholar maps its slot to SEMANTIC_SCHOLAR_API_KEY because
        # that's what the upstream subprocess reads). Fall back to the
        # AGENTLABX_SLOT_<UPPER> default for any slot not in the override map.
        overrides: dict[str, str] = dict(server.spec.slot_env_overrides)
        env: dict[str, str] = {
            overrides.get(slot, slot_to_env_var(slot)): value
            for slot, value in resolved_by_slot.items()
        }

        # Spawn a dedicated owner task that opens the session, signals
        # readiness, then blocks on the stop event. All transport
        # context-managers are entered + exited inside the owner task to
        # honour anyio's cancel-scope task-affinity rule (the bug previously
        # surfaced as "Attempted to exit cancel scope in a different task").
        ready: asyncio.Future[
            tuple[ClientSession, tuple[ToolDescriptor, ...], contextlib.AsyncExitStack]
        ] = asyncio.get_running_loop().create_future()
        stop_event = anyio.Event()
        call_send, call_recv = anyio.create_memory_object_stream[_CallRequest](
            max_buffer_size=math.inf,
        )

        owner_task = asyncio.create_task(
            self._owner_task(
                server=server,
                env=env,
                ready=ready,
                stop_event=stop_event,
                call_recv=call_recv,
            ),
            name=f"mcp-owner-{server.id}",
        )

        try:
            session, tools, stack = await ready
        except BaseException:
            # The owner task already ran teardown via the same task; just
            # await it to surface any final exception cleanly.
            with contextlib.suppress(BaseException):
                await owner_task
            raise

        self._handles[server.id] = _Handle(
            session=session,
            tools=tools,
            exit_stack=stack,
            slot_values=slot_values,
            owner_task=owner_task,
            stop_event=stop_event,
            call_send=call_send,
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

    async def _owner_task(
        self,
        *,
        server: RegisteredServer,
        env: dict[str, str],
        ready: asyncio.Future[
            tuple[ClientSession, tuple[ToolDescriptor, ...], contextlib.AsyncExitStack]
        ],
        stop_event: anyio.Event,
        call_recv: MemoryObjectReceiveStream[_CallRequest],
    ) -> None:
        """Long-lived per-handle task that owns transport open + close.

        Lifecycle: open transport, snapshot tools, signal ``ready``, then
        loop receiving from ``call_recv`` (running each request's
        ``session.call_tool`` in this task's context) until ``stop_event``
        fires. On stop, drain any pending requests by failing them with
        :class:`ServerNotRunning`, then close the transport. All inside one
        task so anyio cancel scopes never cross task boundaries.

        The cross-task hand-off uses anyio memory-object streams (rather
        than ``asyncio.Queue`` + ``asyncio.Future``) because anyio
        primitives traverse Starlette's per-request inner task group
        boundary correctly. With asyncio futures, in-process MCP invokes
        hung indefinitely under live Uvicorn even though pure-ASGI tests
        passed — see ``tests/integration/mcp/
        test_router_live_invoke_through_middleware.py``.
        """

        stack = contextlib.AsyncExitStack()
        try:
            try:
                session = await self._open_session(spec=server.spec, env=env, stack=stack)
                list_result = await session.list_tools()
                tools = self._snapshot_tools(server.spec, list_result.tools)
            except ServerStartupFailed as exc:
                await stack.aclose()
                if not ready.done():
                    ready.set_exception(exc)
                return
            except (McpError, OSError, ValueError) as exc:
                await stack.aclose()
                wrapped = ServerStartupFailed(
                    spec=server.spec,
                    reason=f"tools/list failed after open: {exc!r}",
                )
                if not ready.done():
                    ready.set_exception(wrapped)
                return
            except BaseExceptionGroup as group:
                # anyio task groups (used inside the MCP SDK's stdio transport
                # and ClientSession) re-raise child failures as
                # BaseExceptionGroup, often nested several levels deep. Flatten
                # to the first transport-level leaf so the router surfaces a
                # readable 502 reason instead of a recursive group repr.
                await stack.aclose()
                cancelled = group.subgroup(asyncio.CancelledError)
                if cancelled is not None:
                    if not ready.done():
                        ready.set_exception(cancelled)
                    raise
                leaves = list(_flatten_exception_group(group))
                interesting = next(
                    (e for e in leaves if isinstance(e, McpError | OSError | ValueError)),
                    None,
                )
                reason = (
                    f"transport open failed: {interesting!r}"
                    if interesting is not None
                    else f"transport open failed: {group!r}"
                )
                wrapped = ServerStartupFailed(spec=server.spec, reason=reason)
                if not ready.done():
                    ready.set_exception(wrapped)
                return
            except BaseException as exc:
                await stack.aclose()
                if not ready.done():
                    ready.set_exception(exc)
                raise

            if not ready.done():
                ready.set_result((session, tools, stack))

            # Drive the request loop. ``session.call_tool`` is invoked from
            # *this* task so anyio's task-affine memory-object streams in
            # the SDK's ClientSession see send + receive from the same
            # cancel scope that opened them.
            try:
                async with call_recv:
                    while not stop_event.is_set():
                        req = await _receive_or_stop(call_recv, stop_event)
                        if req is None:
                            break
                        await _run_one_call(session, req)
            finally:
                # Fail-fast any requests that arrived after stop was
                # signalled but before callers noticed the handle was
                # popped from ``_handles``. ``receive_nowait`` works on the
                # already-closed-for-receive stream until the buffer is
                # empty, which is exactly the drain semantics we want.
                with contextlib.suppress(
                    anyio.WouldBlock, anyio.EndOfStream, anyio.ClosedResourceError
                ):
                    while True:
                        pending = call_recv.receive_nowait()
                        async with pending.result_send:
                            with contextlib.suppress(
                                anyio.BrokenResourceError, anyio.ClosedResourceError
                            ):
                                await pending.result_send.send(ServerNotRunning(server.id))
        finally:
            # Always close in this task. Tolerate any close-time errors so
            # one bad handle does not poison the stop path.
            with contextlib.suppress(BaseException):
                await stack.aclose()

    async def stop(self, server_id: str) -> None:
        """Stop a running server and release its transport / subprocess.

        Signals the owner task's stop event and awaits the task. The owner
        task closes the transport from its own task context, which is the
        only way anyio's task-affine cancel scopes accept teardown.
        """

        handle = self._handles.pop(server_id, None)
        if handle is None:
            raise ServerNotRunning(server_id)

        if handle.stop_event is not None and handle.owner_task is not None:
            handle.stop_event.set()
            # Close the call-send end so any new ``host.call`` from a
            # racing task fails fast with ``ServerNotRunning`` instead of
            # silently buffering into a stream the owner will never drain.
            if handle.call_send is not None:
                with contextlib.suppress(BaseException):
                    await handle.call_send.aclose()
            with contextlib.suppress(BaseException):
                await handle.owner_task
        else:
            # Synthetic-handle path used by the broken-handle stop_all test:
            # no owner task to coordinate with, so close the stack directly.
            await handle.exit_stack.aclose()

        await self._event_bus.emit(
            Event(
                kind="mcp.server.stopped",
                payload={"server_id": server_id},
            )
        )

    async def stop_all(self) -> None:
        """Graceful shutdown helper — stops every live handle.

        Stops are issued sequentially to avoid spawning sub-tasks (which would
        re-introduce the cancel-scope task-affinity bug). Per-handle failures
        are surfaced as ``mcp.server.stop_failed`` events; one broken handle
        cannot abort teardown of the rest.
        """

        server_ids = list(self._handles.keys())
        for sid in server_ids:
            try:
                await self.stop(sid)
            except ServerNotRunning:
                continue
            except BaseException as exc:  # noqa: BLE001 — observe and continue
                await self._event_bus.emit(
                    Event(
                        kind="mcp.server.stop_failed",
                        payload={
                            "server_id": sid,
                            "error_type": type(exc).__name__,
                            "reason": str(exc),
                        },
                    )
                )

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def running_server_ids(self) -> tuple[str, ...]:
        """Return the ids of every currently-running server.

        Used by the bootstrap-audit log line in :mod:`agentlabx.server.app` to
        count successful starts without reaching into the private handle dict.
        Order is the natural insertion order of the underlying dict.
        """

        return tuple(self._handles.keys())

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

        # Route the SDK call through the owner task so that
        # ``session.call_tool`` runs in the same task that opened the
        # underlying anyio memory-object streams. A direct ``await
        # handle.session.call_tool(...)`` from a different task (e.g. a
        # Starlette request handler) trips ``anyio.ClosedResourceError``
        # because anyio enforces task-affinity on memory-object streams.
        if handle.call_send is None:
            # Synthetic-handle path (test_stop_all_tolerates_broken_handle
            # installs a handle without an owner task / queue). Preserve
            # the legacy direct-call semantics for that fixture.
            try:
                sdk_result = await handle.session.call_tool(tool, args)
            except McpError as exc:
                raise ToolExecutionFailed(server_id, tool, exc) from exc
            except Exception as exc:  # noqa: BLE001 — wrap-and-rethrow contract
                raise ToolExecutionFailed(server_id, tool, exc) from exc
        else:
            # Single-shot anyio result channel. Buffer size 1 so the owner
            # task's send completes immediately. Both ends are closed by
            # the ``async with`` blocks below.
            result_send, result_recv = anyio.create_memory_object_stream[_CallResult](1)
            req = _CallRequest(tool=tool, args=args, result_send=result_send)
            try:
                await handle.call_send.send(req)
            except (anyio.BrokenResourceError, anyio.ClosedResourceError) as exc:
                # Owner task is gone (server stopped between the handle
                # lookup above and the send). Match the canonical error.
                async with result_send:
                    pass
                async with result_recv:
                    pass
                raise ServerNotRunning(server_id) from exc
            try:
                async with result_recv:
                    outcome = await result_recv.receive()
            except anyio.EndOfStream as exc:
                raise ServerNotRunning(server_id) from exc
            if isinstance(outcome, ServerNotRunning):
                raise outcome
            if isinstance(outcome, McpError):
                raise ToolExecutionFailed(server_id, tool, outcome) from outcome
            if isinstance(outcome, BaseException):
                raise ToolExecutionFailed(server_id, tool, outcome) from outcome
            sdk_result = outcome

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
# Owner-task helpers (anyio cross-task hand-off primitives)
# ---------------------------------------------------------------------------


async def _receive_or_stop(
    call_recv: MemoryObjectReceiveStream[_CallRequest],
    stop_event: anyio.Event,
) -> _CallRequest | None:
    """Wait for either a request or the stop signal, whichever arrives first.

    Returns the received request, or ``None`` if the stop event fires (or the
    send end is closed). Implemented via an anyio task group with cooperative
    cancellation so the loser is cleanly torn down — anyio's structured
    concurrency means we don't have to manage task handles by hand.
    """

    holder: list[_CallRequest | None] = [None]

    async def _wait_stop() -> None:
        await stop_event.wait()
        tg.cancel_scope.cancel()

    async def _wait_req() -> None:
        try:
            holder[0] = await call_recv.receive()
        except (anyio.EndOfStream, anyio.ClosedResourceError):
            holder[0] = None
        tg.cancel_scope.cancel()

    async with anyio.create_task_group() as tg:
        tg.start_soon(_wait_stop)
        tg.start_soon(_wait_req)
    return holder[0]


async def _run_one_call(session: ClientSession, req: _CallRequest) -> None:
    """Execute one queued tool call in the owner task and reply on its channel.

    Catches every exception so a single failing call never breaks the owner
    loop. The receive end's ``async with`` in :meth:`MCPHost.call` disposes
    the stream regardless of which branch fires.
    """

    async with req.result_send:
        try:
            result = await session.call_tool(req.tool, req.args)
        except BaseException as exc:
            with contextlib.suppress(anyio.BrokenResourceError, anyio.ClosedResourceError):
                await req.result_send.send(exc)
            return
        with contextlib.suppress(anyio.BrokenResourceError, anyio.ClosedResourceError):
            await req.result_send.send(result)


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
