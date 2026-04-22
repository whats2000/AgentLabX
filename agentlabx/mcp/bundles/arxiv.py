"""arXiv MCP bundle launch spec.

Adopts the community ``arxiv-mcp-server`` upstream (``blazickjp/arxiv-mcp-server``)
launched via ``uvx arxiv-mcp-server``. No API key is required.

The full launch command can be overridden via the
``AGENTLABX_BUNDLE_ARXIV_COMMAND`` environment variable so operators can swap
in a fork or pin a different version without forking AgentLabX.
"""

from __future__ import annotations

import os

from agentlabx.mcp.protocol import MCPServerSpec


def spec() -> MCPServerSpec:
    """Construct the arXiv bundle's launch spec."""

    cmd_override = os.environ.get("AGENTLABX_BUNDLE_ARXIV_COMMAND")
    command: tuple[str, ...] = (
        tuple(cmd_override.split()) if cmd_override else ("uvx", "arxiv-mcp-server")
    )
    return MCPServerSpec(
        name="arxiv",
        scope="admin",
        transport="stdio",
        command=command,
        url=None,
        inprocess_key=None,
        env_slot_refs=(),
        declared_capabilities=("paper_search", "paper_fetch"),
    )


__all__ = ["spec"]
