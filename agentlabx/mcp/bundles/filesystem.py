"""Filesystem MCP bundle launch spec.

Adopts the official ``@modelcontextprotocol/server-filesystem`` upstream over
stdio (``npx -y @modelcontextprotocol/server-filesystem <workspace-root>``).
The workspace root is read from :class:`agentlabx.config.settings.AppSettings`
so the bundled server is sandboxed to AgentLabX's workspace directory.

The full launch command can be overridden via the
``AGENTLABX_BUNDLE_FILESYSTEM_COMMAND`` environment variable; the override is
split on whitespace and used verbatim. This is the standard escape hatch for
operators who need to swap in a fork or pin a different version.
"""

from __future__ import annotations

import os
import shlex

from agentlabx.config.settings import AppSettings
from agentlabx.mcp.protocol import MCPServerSpec


def spec() -> MCPServerSpec:
    """Construct the filesystem bundle's launch spec."""

    settings = AppSettings()
    cmd_override = os.environ.get("AGENTLABX_BUNDLE_FILESYSTEM_COMMAND")
    command: tuple[str, ...]
    if cmd_override:
        command = tuple(shlex.split(cmd_override))
    else:
        command = (
            "npx",
            "-y",
            "@modelcontextprotocol/server-filesystem",
            str(settings.workspace),
        )
    return MCPServerSpec(
        name="filesystem",
        scope="admin",
        transport="stdio",
        command=command,
        url=None,
        inprocess_key=None,
        env_slot_refs=(),
        declared_capabilities=("fs_read", "fs_write"),
    )


__all__ = ["spec"]
