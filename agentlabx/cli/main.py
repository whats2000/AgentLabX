from __future__ import annotations

import asyncio
from pathlib import Path

import click
import uvicorn

from agentlabx.auth.default import DefaultAuther
from agentlabx.config.settings import AppSettings, BindMode
from agentlabx.db.migrations import apply_migrations
from agentlabx.db.session import DatabaseHandle
from agentlabx.server.app import create_app


@click.group()
def cli() -> None:
    """AgentLabX command-line interface."""


@cli.command("bootstrap-admin")
@click.option("--display-name", required=True, help="Human-readable admin name.")
@click.option("--passphrase", prompt=True, hide_input=True, confirmation_prompt=True)
@click.option("--workspace", type=click.Path(path_type=Path), default=None)
def bootstrap_admin(display_name: str, passphrase: str, workspace: Path | None) -> None:
    """Register the first identity (granted admin capability automatically)."""

    async def _run() -> None:
        settings = AppSettings(workspace=workspace) if workspace else AppSettings()
        handle = DatabaseHandle(settings.db_path)
        await handle.connect()
        try:
            await apply_migrations(handle)
            identity = await DefaultAuther(handle).register(
                display_name=display_name, passphrase=passphrase
            )
            click.echo(f"Registered identity id={identity.id} (admin)")
        finally:
            await handle.close()

    asyncio.run(_run())


@cli.command("serve")
@click.option("--bind", type=click.Choice(["loopback", "lan"]), default="loopback")
@click.option("--host", default=None, help="Bind host; defaults by mode.")
@click.option("--port", default=8765, type=int)
@click.option("--tls-cert", type=click.Path(path_type=Path), default=None)
@click.option("--tls-key", type=click.Path(path_type=Path), default=None)
@click.option("--workspace", type=click.Path(path_type=Path), default=None)
def serve(
    bind: str,
    host: str | None,
    port: int,
    tls_cert: Path | None,
    tls_key: Path | None,
    workspace: Path | None,
) -> None:
    """Start the AgentLabX server."""
    mode = BindMode.LAN if bind == "lan" else BindMode.LOOPBACK
    effective_host = host or ("0.0.0.0" if mode is BindMode.LAN else "127.0.0.1")  # noqa: S104
    kwargs: dict[str, str | int | Path | BindMode | None] = {
        "bind_mode": mode,
        "bind_host": effective_host,
        "bind_port": port,
    }
    if tls_cert is not None:
        kwargs["tls_cert"] = tls_cert
    if tls_key is not None:
        kwargs["tls_key"] = tls_key
    if workspace is not None:
        kwargs["workspace"] = workspace

    settings = AppSettings(**kwargs)  # type: ignore[arg-type]
    app = asyncio.run(create_app(settings))

    uv_kwargs: dict[str, str | int | None] = {
        "host": settings.bind_host,
        "port": settings.bind_port,
    }
    if mode is BindMode.LAN:
        uv_kwargs["ssl_certfile"] = str(settings.tls_cert)
        uv_kwargs["ssl_keyfile"] = str(settings.tls_key)
    uvicorn.run(app, **uv_kwargs)  # type: ignore[arg-type]
