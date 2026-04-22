"""MCP protocol surface — value types, tagged-union content, exceptions.

These dataclasses are the AgentLabX-native representation of MCP concepts
(servers, tool descriptors, tool-call results). The host adapts raw mcp-SDK
types into these shapes at the boundary so downstream code (dispatcher, REST,
events) only ever sees AgentLabX types.

All dataclasses here are frozen value objects. Validation that depends on
multiple fields lives in ``__post_init__`` and raises ``ValueError`` (not an
``MCPError`` — bad constructor arguments are programmer errors, not domain
errors).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from agentlabx.core.json_types import JSONValue

Scope = Literal["user", "admin"]
Transport = Literal["stdio", "http", "inprocess"]


# ---------------------------------------------------------------------------
# Tool-call content (tagged union)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TextContent:
    """Plain-text fragment of a tool-call result."""

    text: str
    type: Literal["text"] = "text"


@dataclass(frozen=True, slots=True)
class ImageContent:
    """Inline image (base64-encoded) fragment of a tool-call result."""

    data: str
    mime_type: str
    type: Literal["image"] = "image"


@dataclass(frozen=True, slots=True)
class ResourceRefContent:
    """Reference to an out-of-band resource fragment of a tool-call result."""

    uri: str
    mime_type: str | None = None
    type: Literal["resource"] = "resource"


ToolContentItem = TextContent | ImageContent | ResourceRefContent
"""Tagged union over the MCP SDK's ``CallToolResult.content`` variants.

Discriminate via ``match`` on ``.type`` at the call site.
"""


# ---------------------------------------------------------------------------
# Server / tool surface types
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class MCPServerSpec:
    """Launch + identity descriptor for an MCP server.

    Exactly one of ``command`` (stdio), ``url`` (http), or ``inprocess_key``
    (inprocess) must be set; all others must be ``None``. The validator in
    ``__post_init__`` enforces this and also checks that the chosen field
    matches ``transport``.
    """

    name: str
    scope: Scope
    transport: Transport
    command: tuple[str, ...] | None
    url: str | None
    inprocess_key: str | None
    env_slot_refs: tuple[str, ...]
    declared_capabilities: tuple[str, ...]

    def __post_init__(self) -> None:
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
                "MCPServerSpec requires exactly one of command, url, "
                f"inprocess_key to be set; got: {set_fields or ('none',)}"
            )
        expected_field = {
            "stdio": "command",
            "http": "url",
            "inprocess": "inprocess_key",
        }[self.transport]
        if set_fields[0] != expected_field:
            raise ValueError(
                f"transport={self.transport!r} requires field "
                f"{expected_field!r} to be set, but {set_fields[0]!r} was set "
                "instead"
            )


@dataclass(frozen=True, slots=True)
class ToolDescriptor:
    """Snapshot of a single tool exposed by an MCP server.

    ``input_schema`` is a real (possibly recursively nested) JSON Schema
    object as advertised by the server's ``tools/list`` response.
    """

    server_name: str
    tool_name: str
    description: str
    input_schema: dict[str, JSONValue]
    capabilities: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ToolCallResult:
    """AgentLabX-native shape for the result of a single tool invocation.

    ``structured`` mirrors the MCP SDK's optional ``structuredContent`` field
    when the server provides one.
    """

    content: tuple[ToolContentItem, ...]
    is_error: bool
    structured: dict[str, JSONValue] | None


@dataclass(frozen=True, slots=True)
class RegisteredServer:
    """A server that has been registered (and tools snapshotted) with the host.

    ``owner_id is None`` only for admin-scope servers; user-scope servers
    must always carry the owning user's id. ``id`` is the persistent server
    identity assigned by the registry on insert and is the lookup key used by
    ``ServerRegistry.get`` / ``ServerRegistry.delete``.
    """

    id: str
    spec: MCPServerSpec
    owner_id: str | None
    tools: tuple[ToolDescriptor, ...]
    started_at: datetime | None

    def __post_init__(self) -> None:
        if self.spec.scope == "user" and self.owner_id is None:
            raise ValueError("user-scope RegisteredServer requires owner_id to be set")
        if self.spec.scope == "admin" and self.owner_id is not None:
            raise ValueError("admin-scope RegisteredServer must have owner_id=None")


@dataclass(frozen=True, slots=True)
class CapabilityRequest:
    """Input to the capability gate: who is asking for which capability."""

    stage_name: str
    agent_name: str
    capability: str


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class MCPError(Exception):
    """Base class for all MCP-layer domain errors."""


class ServerNotRunning(MCPError):  # noqa: N818  — name fixed by Stage A3 plan
    """Raised when a tool call is attempted against a server that is not live."""

    def __init__(self, server: str) -> None:
        self.server = server
        super().__init__(f"MCP server {server!r} is not running")


class ToolNotFound(MCPError):  # noqa: N818  — name fixed by Stage A3 plan
    """Raised when a (server, tool) pair is not present in the registry."""

    def __init__(self, server: str, tool: str) -> None:
        self.server = server
        self.tool = tool
        super().__init__(f"tool {tool!r} not found on server {server!r}")


class ToolExecutionFailed(MCPError):  # noqa: N818  — name fixed by Stage A3 plan
    """Raised when an MCP tool invocation fails inside the server."""

    def __init__(self, server: str, tool: str, underlying: BaseException) -> None:
        self.server = server
        self.tool = tool
        self.underlying = underlying
        super().__init__(f"tool {tool!r} on server {server!r} failed: {underlying!r}")


class CapabilityRefused(MCPError):  # noqa: N818  — name fixed by Stage A3 plan
    """Raised when the capability gate rejects a tool invocation."""

    def __init__(self, stage: str, agent: str, capability: str) -> None:
        self.stage = stage
        self.agent = agent
        self.capability = capability
        super().__init__(
            f"capability {capability!r} refused for agent {agent!r} in stage {stage!r}"
        )


class ServerStartupFailed(MCPError):  # noqa: N818  — name fixed by Stage A3 plan
    """Raised when an MCP server fails to start."""

    def __init__(self, spec: MCPServerSpec, reason: str) -> None:
        self.spec = spec
        self.reason = reason
        super().__init__(f"MCP server {spec.name!r} ({spec.transport}) failed to start: {reason}")


class RegistrationConflict(MCPError):  # noqa: N818  — name fixed by Stage A3 plan
    """Raised when a server name collides within the same scope."""

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"MCP server name {name!r} already registered in scope")


__all__ = [
    "CapabilityRefused",
    "CapabilityRequest",
    "ImageContent",
    "MCPError",
    "MCPServerSpec",
    "RegisteredServer",
    "RegistrationConflict",
    "ResourceRefContent",
    "Scope",
    "ServerNotRunning",
    "ServerStartupFailed",
    "TextContent",
    "ToolCallResult",
    "ToolContentItem",
    "ToolDescriptor",
    "ToolExecutionFailed",
    "ToolNotFound",
    "Transport",
]
