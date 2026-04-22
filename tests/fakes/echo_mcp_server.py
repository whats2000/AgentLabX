"""Deterministic stdio MCP server used as a target by host/dispatcher tests.

Exposes two tools:

* ``echo(message: str) -> str`` — returns the input message verbatim.
* ``boom() -> NoReturn`` — raises ``RuntimeError("boom!")`` to drive the
  ``ToolExecutionFailed`` path.

Run via ``python -m tests.fakes.echo_mcp_server``. Depends only on the ``mcp``
SDK so it can be launched as a subprocess from any test.
"""

from __future__ import annotations

import asyncio
from typing import NoReturn

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

ECHO_INPUT_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "message": {"type": "string"},
    },
    "required": ["message"],
    # Bundled-server style metadata key — exercised by test_host_lifecycle's
    # capability-mapping assertion to confirm the SDK round-trips unknown keys.
    "x-agentlabx-capabilities": ["echo_speak"],
}

BOOM_INPUT_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {},
    "required": [],
}


async def main() -> None:
    server: Server[object, object] = Server("echo-fake")

    @server.list_tools()  # type: ignore[no-untyped-call,untyped-decorator]
    async def list_tools() -> list[Tool]:
        return [
            Tool(
                name="echo",
                description="Echo the supplied message back as text.",
                inputSchema=ECHO_INPUT_SCHEMA,
            ),
            Tool(
                name="boom",
                description="Always raises — used to test the failure path.",
                inputSchema=BOOM_INPUT_SCHEMA,
            ),
        ]

    @server.call_tool()  # type: ignore[untyped-decorator]
    async def call_tool(name: str, arguments: dict[str, object]) -> list[TextContent]:
        if name == "echo":
            message = arguments.get("message")
            if not isinstance(message, str):
                raise ValueError("echo requires a string 'message' argument")
            return [TextContent(type="text", text=message)]
        if name == "boom":
            _raise_boom()
        raise ValueError(f"unknown tool: {name}")

    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


def _raise_boom() -> NoReturn:
    raise RuntimeError("boom!")


if __name__ == "__main__":
    asyncio.run(main())
