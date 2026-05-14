"""Pydantic request / response models for the ``/api/mcp/*`` REST surface.

Kept deliberately separate from the internal :mod:`agentlabx.mcp.protocol`
dataclasses: the dataclasses model the runtime / persistence shape, the
Pydantic models model the wire shape. Conversions live in the router.

JSON arg payloads are typed as ``dict[str, JSONValue]`` so Pydantic validates
the structure at the boundary; the dispatcher re-validates against the tool's
``input_schema`` before invocation.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from agentlabx.core.json_types import JSONValue

Scope = Literal["user", "admin"]
Transport = Literal["stdio", "http", "inprocess"]


class MCPToolResponse(BaseModel):  # type: ignore[explicit-any]
    """Wire shape for a single tool advertised by a running MCP server."""

    server_id: str
    server_name: str
    tool_name: str
    description: str
    input_schema: dict[str, JSONValue]
    capabilities: tuple[str, ...]


class MCPServerResponse(BaseModel):  # type: ignore[explicit-any]
    """Wire shape for a registered MCP server (with optional live tool snapshot)."""

    id: str
    name: str
    scope: Scope
    transport: Transport
    enabled: bool
    owner_id: str | None
    declared_capabilities: tuple[str, ...]
    env_slot_refs: tuple[str, ...] = ()
    # Launch descriptor — exactly one is non-null per ``transport``. Surfaced
    # so the UI can show what's running. Slot values are NEVER inlined here;
    # they are env-injected from admin_configs/user_configs at start time.
    command: tuple[str, ...] | None = None
    url: str | None = None
    inprocess_key: str | None = None
    # Last ``ServerStartupFailed.reason`` recorded for this row, or null
    # when the row last started cleanly. Surfaced so the frontend can
    # render *why* a row is grey without consulting the audit log.
    last_startup_error: str | None = None
    tools: list[MCPToolResponse] = Field(default_factory=list)
    started_at: datetime | None = None
    # True when this row was seeded from an admin-scope bundled spec
    # (matches the same ``mcp_bundled_names`` set the DELETE handler
    # checks). Surfaced so the UI can hide the delete affordance — the
    # seed loop re-creates the row on next boot, so deletion is illusory
    # and the user almost certainly meant ``enabled=false`` instead.
    bundled: bool = False


class MCPServerCreateRequest(BaseModel):  # type: ignore[explicit-any]
    """Body for ``POST /api/mcp/servers``.

    Mirrors :class:`agentlabx.mcp.protocol.MCPServerSpec`'s validation: exactly
    one of ``command`` / ``url`` / ``inprocess_key`` must be set, and the chosen
    field must match ``transport``.
    """

    name: str
    scope: Scope = "user"
    transport: Transport
    command: tuple[str, ...] | None = None
    url: str | None = None
    inprocess_key: str | None = None
    env_slot_refs: tuple[str, ...] = ()
    declared_capabilities: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _exactly_one_transport_field(self) -> MCPServerCreateRequest:
        set_fields: tuple[str, ...] = tuple(
            name
            for name, value in (
                ("command", self.command),
                ("url", self.url),
                ("inprocess_key", self.inprocess_key),
            )
            if value is not None
        )
        if len(set_fields) != 1:
            raise ValueError(
                "exactly one of command, url, inprocess_key must be set; "
                f"got: {set_fields or ('none',)}"
            )
        expected = {
            "stdio": "command",
            "http": "url",
            "inprocess": "inprocess_key",
        }[self.transport]
        if set_fields[0] != expected:
            raise ValueError(
                f"transport={self.transport!r} requires field {expected!r} to be set, "
                f"but {set_fields[0]!r} was set instead"
            )
        if self.transport == "stdio" and self.command is not None and len(self.command) == 0:
            raise ValueError("stdio transport requires a non-empty command tuple")
        return self


class MCPServerEnabledPatch(BaseModel):  # type: ignore[explicit-any]
    """Body for ``PATCH /api/mcp/servers/{id}`` — toggles ``enabled``."""

    enabled: bool


class ToolInvokeRequest(BaseModel):  # type: ignore[explicit-any]
    """Body for the debug-only ``invoke`` endpoint."""

    args: dict[str, JSONValue] = Field(default_factory=dict)


class ToolInvokeResponse(BaseModel):  # type: ignore[explicit-any]
    """Wire shape for a tool invocation result.

    ``text`` is the joined ``TextContent`` fragments of the result; ``structured``
    mirrors the SDK's optional ``structuredContent`` field when present.
    """

    is_error: bool
    text: str
    structured: dict[str, JSONValue] | None = None


__all__ = [
    "MCPServerCreateRequest",
    "MCPServerEnabledPatch",
    "MCPServerResponse",
    "MCPToolResponse",
    "Scope",
    "ToolInvokeRequest",
    "ToolInvokeResponse",
    "Transport",
]
