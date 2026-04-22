"""Semantic Scholar MCP bundle launch spec.

Adopts the community ``semanticscholar-mcp`` upstream launched via
``uvx semanticscholar-mcp``. The exact PyPI package name MUST be verified at
Task 10 smoke time -- if the upstream is unmaintained or renamed, switch the
default command and update the docstring (the structural spec contract here
does not change).

A Semantic Scholar API key is *optional* upstream, but we declare a slot for
it so the seed loop disables the bundle until the operator either fills the
slot or explicitly enables anonymous use via the launch-command override. The
slot name ``semantic_scholar_api_key`` is the conventional A3 slot id.

The full launch command can be overridden via
``AGENTLABX_BUNDLE_SEMANTIC_SCHOLAR_COMMAND``.
"""

from __future__ import annotations

import os

from agentlabx.mcp.protocol import MCPServerSpec


def spec() -> MCPServerSpec:
    """Construct the Semantic Scholar bundle's launch spec."""

    cmd_override = os.environ.get("AGENTLABX_BUNDLE_SEMANTIC_SCHOLAR_COMMAND")
    # TODO(task10-smoke): verify ``semanticscholar-mcp`` is the canonical
    # PyPI distribution name; some forks publish as ``mcp-semanticscholar``.
    command: tuple[str, ...] = (
        tuple(cmd_override.split()) if cmd_override else ("uvx", "semanticscholar-mcp")
    )
    return MCPServerSpec(
        name="semantic_scholar",
        scope="admin",
        transport="stdio",
        command=command,
        url=None,
        inprocess_key=None,
        env_slot_refs=("semantic_scholar_api_key",),
        declared_capabilities=("paper_search",),
    )


__all__ = ["spec"]
