"""REST surface for MCP server management — ``/api/mcp/*``.

All endpoints sit behind the existing session-cookie / bearer-token
authentication shared with the rest of the server. Authorisation rules:

* ``GET`` endpoints return resources visible to the caller (admin-scope rows
  are visible to all logged-in users; user-scope rows only to their owner).
* ``POST`` of an admin-scope server requires the ``admin`` capability.
* ``PATCH`` / ``DELETE`` require the caller to be the row's owner or an admin.
* ``POST .../invoke`` is debug-only and gated identically — owner or admin.

The router does not own lifecycle state: it reaches into ``request.app.state``
for the singleton :class:`ServerRegistry`, :class:`MCPHost`, and
:class:`ToolDispatcher` which are constructed by ``app.py``'s lifespan.
"""

from __future__ import annotations

import contextlib
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status

from agentlabx.auth.protocol import Identity
from agentlabx.mcp.api_models import (
    MCPServerCreateRequest,
    MCPServerEnabledPatch,
    MCPServerResponse,
    MCPToolResponse,
    ToolInvokeRequest,
    ToolInvokeResponse,
)
from agentlabx.mcp.dispatcher import ToolDispatcher
from agentlabx.mcp.host import MCPHost
from agentlabx.mcp.protocol import (
    CapabilityRefused,
    InvalidToolArgs,
    MCPServerSpec,
    RegisteredServer,
    RegistrationConflict,
    ServerNotRunning,
    ServerStartupFailed,
    TextContent,
    ToolCallResult,
    ToolDescriptor,
    ToolExecutionFailed,
    ToolNotFound,
)
from agentlabx.mcp.registry import ServerRegistry
from agentlabx.server.dependencies import current_identity, is_admin

router = APIRouter(prefix="/api/mcp", tags=["mcp"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _registry(request: Request) -> ServerRegistry:
    reg: ServerRegistry = request.app.state.mcp_registry
    return reg


def _host(request: Request) -> MCPHost:
    host: MCPHost = request.app.state.mcp_host
    return host


def _dispatcher(request: Request) -> ToolDispatcher:
    disp: ToolDispatcher = request.app.state.mcp_dispatcher
    return disp


def _bundled_names(request: Request) -> frozenset[str]:
    """Spec-name set of admin-scope bundles discovered at boot.

    Mirrors the value the DELETE handler consults to reject deletion of
    seeded bundles — surfaced on every response so the UI can hide the
    delete affordance up-front instead of relying on the 409 round-trip.
    Falls back to an empty set when the lifespan didn't populate it
    (e.g. test apps that wire the router manually).
    """
    names: frozenset[str] = getattr(request.app.state, "mcp_bundled_names", frozenset())
    return names


def _is_bundled(server: RegisteredServer, bundled_names: frozenset[str]) -> bool:
    return server.spec.scope == "admin" and server.spec.name in bundled_names


def _can_view(server: RegisteredServer, identity: Identity) -> bool:
    if server.spec.scope == "admin":
        return True
    return server.owner_id == identity.id


def _can_mutate(server: RegisteredServer, identity: Identity) -> bool:
    if is_admin(identity):
        return True
    if server.spec.scope == "admin":
        return False
    return server.owner_id == identity.id


def _tool_to_response(server: RegisteredServer, tool: ToolDescriptor) -> MCPToolResponse:
    return MCPToolResponse(
        server_id=server.id,
        server_name=server.spec.name,
        tool_name=tool.tool_name,
        description=tool.description,
        input_schema=tool.input_schema,
        capabilities=tool.capabilities,
    )


def _live_tools(host: MCPHost, server: RegisteredServer) -> tuple[ToolDescriptor, ...]:
    """Return the live tool snapshot for a server, or () when not running."""
    try:
        return host.tools_for(server.id)
    except ServerNotRunning:
        return ()


def _server_to_response(
    server: RegisteredServer,
    *,
    tools: tuple[ToolDescriptor, ...],
    enabled: bool,
    started_at: datetime | None,
    bundled: bool,
) -> MCPServerResponse:
    return MCPServerResponse(
        id=server.id,
        name=server.spec.name,
        scope=server.spec.scope,
        transport=server.spec.transport,
        enabled=enabled,
        owner_id=server.owner_id,
        declared_capabilities=server.spec.declared_capabilities,
        env_slot_refs=server.spec.env_slot_refs,
        command=server.spec.command,
        url=server.spec.url,
        inprocess_key=server.spec.inprocess_key,
        last_startup_error=server.last_startup_error,
        tools=[_tool_to_response(server, t) for t in tools],
        started_at=started_at,
        bundled=bundled,
    )


async def _row_enabled(registry: ServerRegistry, server_id: str) -> bool:
    """Re-read the persisted ``enabled`` flag for a server.

    Thin wrapper over :meth:`ServerRegistry.get_enabled` that flattens the
    ``None`` (no such row) case to ``False`` for the response-shaping callers
    in this module.
    """
    enabled = await registry.get_enabled(server_id)
    return bool(enabled)


# ---------------------------------------------------------------------------
# GET /api/mcp/servers
# ---------------------------------------------------------------------------


@router.get("/servers", response_model=list[MCPServerResponse])
async def list_servers(
    request: Request, identity: Identity = Depends(current_identity)
) -> list[MCPServerResponse]:
    registry = _registry(request)
    host = _host(request)
    bundled_names = _bundled_names(request)
    visible = await registry.list_visible_to(identity.id)
    out: list[MCPServerResponse] = []
    for server in visible:
        tools = _live_tools(host, server)
        enabled = await _row_enabled(registry, server.id)
        out.append(
            _server_to_response(
                server,
                tools=tools,
                enabled=enabled,
                started_at=None,
                bundled=_is_bundled(server, bundled_names),
            )
        )
    return out


# ---------------------------------------------------------------------------
# POST /api/mcp/servers
# ---------------------------------------------------------------------------


@router.post(
    "/servers",
    status_code=status.HTTP_201_CREATED,
    response_model=MCPServerResponse,
)
async def register_server(
    payload: MCPServerCreateRequest,
    request: Request,
    identity: Identity = Depends(current_identity),
) -> MCPServerResponse:
    # Mirror the gate enforced by ``dependencies.require_admin`` — we cannot
    # use that dependency directly here because admin is only required for the
    # admin-scope branch, not for user-scope registration.
    if payload.scope == "admin" and not is_admin(identity):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="admin capability required to register an admin-scope server",
        )

    # I2: HTTP transport doesn't get env-injected slot values (a stdio
    # subprocess inherits parent env; an HTTP request doesn't). Reject
    # registrations that would silently drop their slot values rather than
    # let users believe a key is wired through. Header-based slot
    # forwarding for HTTP is a future addition.
    if payload.transport == "http" and payload.env_slot_refs:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "HTTP transport does not yet support env_slot_refs (slot values "
                "would be silently dropped). Either remove env_slot_refs or use "
                "a stdio/inprocess transport."
            ),
        )

    try:
        spec = MCPServerSpec(
            name=payload.name,
            scope=payload.scope,
            transport=payload.transport,
            command=payload.command,
            url=payload.url,
            inprocess_key=payload.inprocess_key,
            env_slot_refs=payload.env_slot_refs,
            declared_capabilities=payload.declared_capabilities,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    owner_id: str | None = None if payload.scope == "admin" else identity.id

    registry = _registry(request)
    host = _host(request)

    try:
        registered = await registry.register(spec, owner_id=owner_id)
    except RegistrationConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    started_at: datetime | None = None
    tools: tuple[ToolDescriptor, ...] = ()
    try:
        started = await host.start(registered, owner_id=owner_id)
        tools = started.tools
        started_at = started.started_at
    except ServerStartupFailed as exc:
        # Roll back the row so the user can retry without a stale enabled=1
        # registration blocking re-register on the same name.
        await registry.delete(registered.id, requester_id=identity.id, requester_is_admin=True)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"failed to start MCP server: {exc.reason}",
        ) from exc

    return _server_to_response(
        registered,
        tools=tools,
        enabled=True,
        started_at=started_at,
        bundled=_is_bundled(registered, _bundled_names(request)),
    )


# ---------------------------------------------------------------------------
# GET /api/mcp/servers/{id}
# ---------------------------------------------------------------------------


@router.get("/servers/{server_id}", response_model=MCPServerResponse)
async def get_server(
    server_id: str, request: Request, identity: Identity = Depends(current_identity)
) -> MCPServerResponse:
    registry = _registry(request)
    host = _host(request)
    server = await registry.get(server_id)
    if server is None or not _can_view(server, identity):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no such server")
    tools = _live_tools(host, server)
    enabled = await _row_enabled(registry, server.id)
    return _server_to_response(
        server,
        tools=tools,
        enabled=enabled,
        started_at=None,
        bundled=_is_bundled(server, _bundled_names(request)),
    )


# ---------------------------------------------------------------------------
# PATCH /api/mcp/servers/{id}
# ---------------------------------------------------------------------------


@router.patch("/servers/{server_id}", response_model=MCPServerResponse)
async def patch_server(
    server_id: str,
    payload: MCPServerEnabledPatch,
    request: Request,
    identity: Identity = Depends(current_identity),
) -> MCPServerResponse:
    registry = _registry(request)
    host = _host(request)
    server = await registry.get(server_id)
    if server is None or not _can_view(server, identity):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no such server")
    if not _can_mutate(server, identity):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="not permitted to modify this server",
        )

    if payload.enabled:
        # Idempotent w.r.t. the handle registry: if already running, no-op.
        try:
            host.tools_for(server.id)
            running = True
        except ServerNotRunning:
            running = False
        if not running:
            try:
                await host.start(server, owner_id=server.owner_id)
            except ServerStartupFailed as exc:
                # Persist the failure reason so the UI can render the
                # diagnostic next to the (still ``enabled=true``) row
                # instead of silently going grey. Best-effort: a
                # secondary DB failure must not mask the primary cause.
                with contextlib.suppress(Exception):
                    await registry.set_startup_error(server.id, exc.reason)
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"failed to start MCP server: {exc.reason}",
                ) from exc
            # Successful start — clear any prior recorded failure.
            await registry.set_startup_error(server.id, None)
    else:
        with contextlib.suppress(ServerNotRunning):
            await host.stop(server.id)

    await registry.set_enabled(server.id, payload.enabled)
    # Re-fetch so the response reflects post-mutation state — both
    # ``enabled`` (just toggled) and ``last_startup_error`` (cleared on
    # successful start, populated on failure). Reading the in-memory
    # ``server`` snapshot taken at the top of the handler would render
    # a stale red banner after a successful retry.
    refreshed = await registry.get(server.id)
    if refreshed is not None:
        server = refreshed
    tools = _live_tools(host, server)
    # ``started_at`` is intentionally omitted on PATCH responses: we do not
    # currently track per-handle start timestamps inside :class:`MCPHost`, and
    # synthesising ``datetime.now()`` here would mislead clients into thinking
    # the server (re-)started at PATCH-handler time. The field is informational
    # only at this stage; ``None`` is the honest answer.
    return _server_to_response(
        server,
        tools=tools,
        enabled=payload.enabled,
        started_at=None,
        bundled=_is_bundled(server, _bundled_names(request)),
    )


# ---------------------------------------------------------------------------
# DELETE /api/mcp/servers/{id}
# ---------------------------------------------------------------------------


@router.delete("/servers/{server_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_server(
    server_id: str, request: Request, identity: Identity = Depends(current_identity)
) -> None:
    registry = _registry(request)
    host = _host(request)
    server = await registry.get(server_id)
    if server is None or not _can_view(server, identity):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no such server")
    if not _can_mutate(server, identity):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="not permitted to delete this server",
        )

    # Refuse to delete bundled admin rows: the seed loop re-creates them on
    # next boot, so deletion is illusory. The user almost certainly meant
    # PATCH enabled=false instead.
    if _is_bundled(server, _bundled_names(request)):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"server {server.spec.name!r} is a bundled admin server — "
                "the seed loop will re-create it on next boot. Use PATCH "
                "enabled=false to keep it stopped instead."
            ),
        )

    # Stop first (best-effort), then delete the persisted row.
    with contextlib.suppress(ServerNotRunning):
        await host.stop(server.id)

    deleted = await registry.delete(
        server.id, requester_id=identity.id, requester_is_admin=is_admin(identity)
    )
    if not deleted:
        # Shouldn't happen — we already verified _can_mutate above. Treat as 404.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no such server")


# ---------------------------------------------------------------------------
# GET /api/mcp/tools — flat aggregate
# ---------------------------------------------------------------------------


@router.get("/tools", response_model=list[MCPToolResponse])
async def list_tools(
    request: Request, identity: Identity = Depends(current_identity)
) -> list[MCPToolResponse]:
    registry = _registry(request)
    host = _host(request)
    visible = await registry.list_visible_to(identity.id)
    out: list[MCPToolResponse] = []
    for server in visible:
        for tool in _live_tools(host, server):
            out.append(_tool_to_response(server, tool))
    return out


# ---------------------------------------------------------------------------
# POST /api/mcp/servers/{id}/tools/{tool}/invoke
# ---------------------------------------------------------------------------


def _result_to_response(result: ToolCallResult) -> ToolInvokeResponse:
    text = "\n".join(c.text for c in result.content if isinstance(c, TextContent))
    return ToolInvokeResponse(
        is_error=result.is_error,
        text=text,
        structured=result.structured,
    )


@router.post(
    "/servers/{server_id}/tools/{tool_name}/invoke",
    response_model=ToolInvokeResponse,
)
async def invoke_tool(
    server_id: str,
    tool_name: str,
    payload: ToolInvokeRequest,
    request: Request,
    identity: Identity = Depends(current_identity),
) -> ToolInvokeResponse:
    registry = _registry(request)
    dispatcher = _dispatcher(request)
    server = await registry.get(server_id)
    if server is None or not _can_view(server, identity):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no such server")
    if not _can_mutate(server, identity):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="not permitted to invoke tools on this server",
        )
    # The debug-invoke endpoint exercises the dispatcher path honestly
    # (so trace events fire identically to stage-driven calls). It does
    # NOT have a stage-declared capability the way A8's gating will, so
    # we look up one the tool actually advertises and use that — the
    # cross-check then validates rather than fails. If the tool has no
    # capabilities at all (legitimate but unusual), we pass empty and
    # accept the cross-check rejection.
    host = _host(request)
    descriptors = host.tools_for(server.id) if server.id in host.running_server_ids() else ()
    descriptor = next((t for t in descriptors if t.tool_name == tool_name), None)
    invoke_capability: str = (
        descriptor.capabilities[0] if descriptor and descriptor.capabilities else "debug"
    )
    try:
        result = await dispatcher.invoke(
            stage="debug",
            agent=identity.id,
            capability=invoke_capability,
            server_id=server.id,
            tool=tool_name,
            args=payload.args,
        )
    except CapabilityRefused as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except InvalidToolArgs as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except ToolNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ServerNotRunning as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"server is not running: {exc}",
        ) from exc
    except ToolExecutionFailed as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"tool execution failed: {exc}",
        ) from exc
    return _result_to_response(result)


__all__ = ["router"]
