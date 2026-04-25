"""MCP integration layer — host, dispatcher, registry.

A3 ships the protocol surface and capability taxonomy first; later tasks
in the same stage add :class:`MCPHost`, :class:`ToolDispatcher`, and the
bundled-server launchers, which will be re-exported here as they land.
"""

from __future__ import annotations

from agentlabx.mcp.capabilities import (
    SEED_CAPABILITIES,
    CapabilitySet,
)
from agentlabx.mcp.protocol import (
    CapabilityRefused,
    CapabilityRequest,
    ImageContent,
    InvalidToolArgs,
    MCPError,
    MCPServerSpec,
    RegisteredServer,
    RegistrationConflict,
    ResourceRefContent,
    Scope,
    ServerNotRunning,
    ServerStartupFailed,
    TextContent,
    ToolCallResult,
    ToolContentItem,
    ToolDescriptor,
    ToolExecutionFailed,
    ToolNotFound,
    Transport,
)

__all__ = [
    "SEED_CAPABILITIES",
    "CapabilityRefused",
    "CapabilityRequest",
    "CapabilitySet",
    "ImageContent",
    "InvalidToolArgs",
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
