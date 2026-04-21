"""AgentLabX-owned in-process MCP server bundles.

Each module under this package implements a single bundled MCP server that the
host wires up via :class:`agentlabx.mcp.transport.InProcessLauncher`. Bundles
own their tool surface and persistence concerns; bundle *launch specs*
(``MCPServerSpec`` rows) are constructed in Task 9.
"""

from __future__ import annotations
