"""Docker-sandboxed Python code-execution MCP server (AgentLabX-owned).

This is the runner module pointed at by
:mod:`agentlabx.mcp.bundles.code_execution`'s launch spec; it is started as a
stdio subprocess (``python -m agentlabx.mcp.bundles.code_execution_server``)
by :class:`agentlabx.mcp.host.MCPHost`.

----------------------------------------------------------------------
Surface (one tool)
----------------------------------------------------------------------
``code.exec(code: str, timeout_sec: int = 5)``
    Execute the supplied Python source inside a hardened ephemeral Docker
    container and return its captured streams::

        {"stdout": str, "stderr": str, "exit_code": int}

    Result is wrapped in a single :class:`mcp.types.TextContent` whose
    ``text`` is the JSON encoding of that payload (the AgentLabX bundled-server
    convention; see :mod:`agentlabx.mcp.bundles.memory_server` for the
    rationale).

----------------------------------------------------------------------
Sandbox hardening
----------------------------------------------------------------------
The container is launched with::

    docker run --rm
      --network=none
      --memory=512m --cpus=1
      --read-only --pids-limit=64
      --tmpfs /tmp:size=64m,exec
      --user 1000:1000
      <pinned-digest>
      python -c <code>

* ``--network=none``  -> no outbound calls.
* ``--memory=512m``   -> bounded RSS.
* ``--cpus=1``        -> single-core soft cap.
* ``--read-only``     -> root filesystem is immutable.
* ``--pids-limit=64`` -> bounds fork bombs.
* ``--tmpfs /tmp...`` -> small writable scratch inside the otherwise read-only
  rootfs so Python can write its bytecode cache and tempfiles.
* ``--user 1000:1000``-> non-root execution.
* Pinned image digest -> no surprises from upstream tag drift.

The host-side ``subprocess.run`` carries an additional ``timeout`` kwarg so a
runaway container is reaped even if Docker itself wedges. ``timeout_sec`` is
clamped to :data:`MAX_TIMEOUT_SEC` (60 s) regardless of what the caller asks
for.

----------------------------------------------------------------------
Capability mapping
----------------------------------------------------------------------
Server-level :data:`DECLARED_CAPABILITIES` is ``("code_exec",)``. The single
tool's ``inputSchema`` advertises the same via the
``x-agentlabx-capabilities`` metadata key (Task 5 convention) for symmetry
with the other AgentLabX-owned bundles.

----------------------------------------------------------------------
Operator prerequisites
----------------------------------------------------------------------
Docker Engine MUST be installed and reachable; otherwise the
``code.exec`` tool returns ``exit_code=-1`` with the docker error text in
``stderr`` rather than raising on the wire (the host-level
``mcp.server.startup_failed`` path covers Docker absence at boot time -- the
tool-level path is the runtime fallback).
"""

from __future__ import annotations

import asyncio
import json
import shutil
import subprocess  # noqa: S404 — sandboxed docker invocation, intentional
from collections.abc import Sequence

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

DECLARED_CAPABILITIES: tuple[str, ...] = ("code_exec",)
"""Server-level declared capabilities, advertised to the host registry."""

SERVER_NAME: str = "agentlabx-code-execution"
"""Stable MCP server ``name`` advertised to clients."""

CAPABILITY_METADATA_KEY: str = "x-agentlabx-capabilities"
"""``inputSchema`` key recognised by :mod:`agentlabx.mcp.host` for per-tool override."""

# TODO(stageA3-mcp-host): re-confirm digest against ``docker pull
# python:3.12-slim`` on a machine with a running daemon before merging A3.
# Sourced from the public Docker Hub registry index for ``library/python:3.12-slim``
# at 2026-04-20; this is the multi-arch index digest, which Docker will resolve
# to the correct per-platform image at pull time.
PINNED_IMAGE_DIGEST: str = (
    "python:3.12-slim@sha256:804ddf3251a60bbf9c92e73b7566c40428d54d0e79d3428194edf40da6521286"
)
"""Pinned ``python:3.12-slim`` image reference used by every ``code.exec`` call."""

DEFAULT_TIMEOUT_SEC: int = 5
"""Default ``timeout_sec`` if the caller omits it."""

MAX_TIMEOUT_SEC: int = 60
"""Hard upper bound on ``timeout_sec`` (request value is clamped)."""

DOCKER_OVERHEAD_SEC: float = 5.0
"""Extra wall-clock budget added on top of ``timeout_sec`` to absorb container
start/teardown latency before the host-side ``subprocess.run`` timeout fires."""


def _exec_schema() -> dict[str, object]:
    return {
        "type": "object",
        "properties": {
            "code": {"type": "string"},
            "timeout_sec": {
                "type": "integer",
                "minimum": 1,
                "maximum": MAX_TIMEOUT_SEC,
                "default": DEFAULT_TIMEOUT_SEC,
            },
        },
        "required": ["code"],
        "additionalProperties": False,
        CAPABILITY_METADATA_KEY: ["code_exec"],
    }


TOOL_DESCRIPTORS: tuple[Tool, ...] = (
    Tool(
        name="code.exec",
        description=(
            "Execute Python source inside a hardened, network-isolated Docker "
            "container (pinned python:3.12-slim digest). Returns captured "
            "{stdout, stderr, exit_code}. timeout_sec is clamped to "
            f"{MAX_TIMEOUT_SEC} seconds."
        ),
        inputSchema=_exec_schema(),
    ),
)


def _as_text(payload: object) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps(payload))]


def _docker_command(code: str) -> tuple[str, ...]:
    """Build the ``docker run`` argv for a single ``code.exec`` invocation.

    Kept as a pure function so unit tests can assert the exact arg shape
    without spawning Docker.
    """

    return (
        "docker",
        "run",
        "--rm",
        "--network=none",
        "--memory=512m",
        "--cpus=1",
        "--read-only",
        "--pids-limit=64",
        "--tmpfs",
        "/tmp:size=64m,exec",
        "--user",
        "1000:1000",
        PINNED_IMAGE_DIGEST,
        "python",
        "-c",
        code,
    )


def _run_in_docker(code: str, timeout_sec: int) -> dict[str, str | int]:
    """Run ``code`` inside the sandbox and capture its stdout/stderr/exit_code.

    Failure modes (Docker missing, image pull failure, timeout) are surfaced
    as a result dict with ``exit_code=-1`` and a descriptive ``stderr`` rather
    than raised exceptions, so the MCP wire path always returns a structured
    payload.
    """

    if shutil.which("docker") is None:
        return {
            "stdout": "",
            "stderr": "code.exec requires Docker on PATH; not found",
            "exit_code": -1,
        }

    argv = _docker_command(code)
    wall_clock_budget = float(timeout_sec) + DOCKER_OVERHEAD_SEC
    try:
        completed = subprocess.run(  # noqa: S603 — argv is a fixed tuple, no shell
            argv,
            capture_output=True,
            text=True,
            timeout=wall_clock_budget,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        partial_stdout = exc.stdout or ""
        partial_stderr = exc.stderr or ""
        if isinstance(partial_stdout, bytes):
            partial_stdout = partial_stdout.decode("utf-8", errors="replace")
        if isinstance(partial_stderr, bytes):
            partial_stderr = partial_stderr.decode("utf-8", errors="replace")
        return {
            "stdout": partial_stdout,
            "stderr": (
                f"{partial_stderr}\n[code.exec] timed out after "
                f"{wall_clock_budget:.1f}s of wall-clock"
            ),
            "exit_code": -1,
        }
    except FileNotFoundError as exc:
        return {
            "stdout": "",
            "stderr": f"code.exec failed to launch docker: {exc!r}",
            "exit_code": -1,
        }

    return {
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "exit_code": completed.returncode,
    }


async def _handle_exec(arguments: dict[str, object]) -> dict[str, str | int]:
    raw_code = arguments.get("code")
    if not isinstance(raw_code, str):
        raise ValueError("code.exec requires a string 'code'")
    raw_timeout = arguments.get("timeout_sec", DEFAULT_TIMEOUT_SEC)
    if isinstance(raw_timeout, bool) or not isinstance(raw_timeout, int) or raw_timeout < 1:
        raise ValueError("code.exec 'timeout_sec' must be a positive integer")
    timeout_sec = min(raw_timeout, MAX_TIMEOUT_SEC)

    # Off-load the blocking ``subprocess.run`` to a worker thread so the
    # asyncio event loop driving the MCP stdio transport stays responsive.
    return await asyncio.to_thread(_run_in_docker, raw_code, timeout_sec)


def build_server() -> Server[object, object]:
    """Construct a configured ``Server`` exposing the ``code.exec`` tool."""

    server: Server[object, object] = Server(SERVER_NAME)

    @server.list_tools()  # type: ignore[no-untyped-call,untyped-decorator]
    async def list_tools() -> list[Tool]:
        return list(TOOL_DESCRIPTORS)

    @server.call_tool()  # type: ignore[untyped-decorator]
    async def call_tool(name: str, arguments: dict[str, object]) -> Sequence[TextContent]:
        if name == "code.exec":
            return _as_text(await _handle_exec(arguments))
        raise ValueError(f"unknown tool: {name}")

    return server


async def main() -> None:
    server = build_server()
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())


__all__ = [
    "DECLARED_CAPABILITIES",
    "DEFAULT_TIMEOUT_SEC",
    "MAX_TIMEOUT_SEC",
    "PINNED_IMAGE_DIGEST",
    "SERVER_NAME",
    "TOOL_DESCRIPTORS",
    "build_server",
    "main",
]
