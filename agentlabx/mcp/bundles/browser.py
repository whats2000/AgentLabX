"""Browser / web-fetch MCP bundle launch spec.

Adopts the official Anthropic reference ``mcp-server-fetch`` upstream over
stdio. Default invocation is ``uvx mcp-server-fetch``; if a particular
distribution doesn't expose a console script, fall back to
``uvx --from mcp-server-fetch python -m mcp_server_fetch`` via the
``AGENTLABX_BUNDLE_BROWSER_COMMAND`` env override.

A3 ships only the ``web_fetch`` capability (HTTP GET / fetch). Full
headless-browser interaction (``web_browse``) is **out of scope for A3** --
that lands in a later stage with a Playwright-based bundle.
"""

from __future__ import annotations

import os

from agentlabx.mcp.protocol import MCPServerSpec


def spec() -> MCPServerSpec:
    """Construct the browser/web-fetch bundle's launch spec."""

    cmd_override = os.environ.get("AGENTLABX_BUNDLE_BROWSER_COMMAND")
    command: tuple[str, ...] = (
        tuple(cmd_override.split()) if cmd_override else ("uvx", "mcp-server-fetch")
    )
    return MCPServerSpec(
        name="browser",
        scope="admin",
        transport="stdio",
        command=command,
        url=None,
        inprocess_key=None,
        env_slot_refs=(),
        declared_capabilities=("web_fetch",),
    )


__all__ = ["spec"]
