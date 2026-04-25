"""Docker-sandboxed Python code-execution MCP bundle launch spec.

A3 takes the **build path** here: no maintained upstream MCP server wraps a
Docker-isolated Python runner with the hardening AgentLabX requires (network
disabled, memory/cpu/pids capped, read-only filesystem, pinned image digest).
The implementation lives in
:mod:`agentlabx.mcp.bundles.code_execution_server`; this module just provides
the launch spec that points the host at it.

The server is launched as a stdio subprocess (``python -m
agentlabx.mcp.bundles.code_execution_server``) rather than in-process because
each ``code.exec`` call shells out to ``docker run``, which is heavyweight and
shouldn't share the AgentLabX event loop.

The launch command can be overridden via
``AGENTLABX_BUNDLE_CODE_EXECUTION_COMMAND`` -- e.g. to swap in a future
upstream once one becomes available.

**Operator prerequisite:** Docker Engine must be installed and the daemon
reachable by the user running AgentLabX. The plan's cross-cutting prereqs make
Docker a hard requirement; this bundle ships *enabled* by default and will
emit ``mcp.server.startup_failed`` at boot if Docker is missing.
"""

from __future__ import annotations

import os
import shlex
import sys

from agentlabx.mcp.protocol import MCPServerSpec


def spec() -> MCPServerSpec:
    """Construct the code-execution bundle's launch spec."""

    cmd_override = os.environ.get("AGENTLABX_BUNDLE_CODE_EXECUTION_COMMAND")
    command: tuple[str, ...]
    if cmd_override:
        command = tuple(shlex.split(cmd_override))
    else:
        # Use ``sys.executable`` so the subprocess inherits the same interpreter
        # AgentLabX is running under -- avoids PATH ambiguity in venv installs.
        command = (
            sys.executable,
            "-m",
            "agentlabx.mcp.bundles.code_execution_server",
        )
    return MCPServerSpec(
        name="code_execution",
        scope="admin",
        transport="stdio",
        command=command,
        url=None,
        inprocess_key=None,
        env_slot_refs=(),
        declared_capabilities=("code_exec",),
    )


__all__ = ["spec"]
