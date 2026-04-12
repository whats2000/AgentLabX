"""Command-line entrypoints for AgentLabX.

IMPORTANT — reload caveat (Fix M):
The `_USE_MOCK_LLM` module global is NOT reload-safe. When `serve --reload` is
used, uvicorn spawns a new process on each file change, which resets the
global. The dev flow is "ctrl-C + restart" when flipping flags — flag changes
don't take effect live. This is an accepted limitation; env-var plumbing has
the same issue and adds no value over this approach.
"""

from __future__ import annotations

import click
import uvicorn

from agentlabx import __version__

# Fix M: module-level state driving the uvicorn factory. Not reload-safe —
# a reload spawns a fresh process that reinitializes this to False unless
# serve() is invoked again via the CLI.
_USE_MOCK_LLM = False


def _build_app_with_config():
    """Factory called by uvicorn.run(factory=True).

    Reads the module-level _USE_MOCK_LLM flag set by the serve() command.
    """
    from agentlabx.server.app import create_app

    return create_app(use_mock_llm=_USE_MOCK_LLM)


@click.group()
@click.version_option(version=__version__, prog_name="agentlabx")
def cli():
    """AgentLabX — modular multi-instance research automation platform."""


@cli.command()
@click.option("--host", default="0.0.0.0", show_default=True, help="Bind host.")
@click.option(
    "--port",
    default=8000,
    type=int,
    show_default=True,
    help="Bind port.",
)
@click.option(
    "--reload",
    is_flag=True,
    help="Enable hot reload (development). NOTE: flipping --mock-llm across "
    "a reload requires a full restart; the flag is set on the parent "
    "process only.",
)
@click.option(
    "--mock-llm",
    is_flag=True,
    help="Use MockLLMProvider instead of LiteLLM (no API keys needed).",
)
def serve(host: str, port: int, reload: bool, mock_llm: bool):
    """Run the AgentLabX HTTP + WebSocket server."""
    global _USE_MOCK_LLM
    _USE_MOCK_LLM = mock_llm
    uvicorn.run(
        "agentlabx.cli.main:_build_app_with_config",
        host=host,
        port=port,
        reload=reload,
        factory=True,
    )
