"""Semantic Scholar MCP bundle launch spec.

Adopts the ``semantic-scholar-mcp`` PyPI package launched via
``uvx semantic-scholar-mcp``. Verified against PyPI on 2026-04-25;
``semanticscholar-mcp`` and ``mcp-semanticscholar`` (the original
candidate names) do not exist. Two close-name alternatives also exist
(``semanticscholar-mcp-server`` / ``mcp-server-semanticscholar`` —
both same upstream by JackKuo666) and can be substituted via the env
override below.

A Semantic Scholar API key is *optional* upstream (anonymous tier is
heavily rate-limited). We declare a slot for it so the seed loop
disables the bundle until the operator either fills the slot via the
admin-credentials UI or explicitly enables anonymous use via the
launch-command override. The slot name ``semantic_scholar_api_key`` is
the conventional A3 slot id.

The full launch command can be overridden via
``AGENTLABX_BUNDLE_SEMANTIC_SCHOLAR_COMMAND``.
"""

from __future__ import annotations

import os

from agentlabx.mcp.protocol import MCPServerSpec


def spec() -> MCPServerSpec:
    """Construct the Semantic Scholar bundle's launch spec."""

    cmd_override = os.environ.get("AGENTLABX_BUNDLE_SEMANTIC_SCHOLAR_COMMAND")
    command: tuple[str, ...] = (
        tuple(cmd_override.split()) if cmd_override else ("uvx", "semantic-scholar-mcp")
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
        # Upstream reads its API key from this fixed env-var name, not from
        # the host's default AGENTLABX_SLOT_SEMANTIC_SCHOLAR_API_KEY mapping.
        slot_env_overrides=(("semantic_scholar_api_key", "SEMANTIC_SCHOLAR_API_KEY"),),
    )


__all__ = ["spec"]
