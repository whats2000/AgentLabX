"""Transport launchers — thin async-context-manager wrappers over the MCP SDK.

Each launcher exposes the same shape::

    async def open(self) -> AsyncContextManager[ClientSession]

so :class:`agentlabx.mcp.host.MCPHost` can dispatch on
:attr:`MCPServerSpec.transport` uniformly. The launchers themselves do not
know about :class:`MCPServerSpec`; they raise a generic
:class:`TransportOpenFailed` on failure, which the host then wraps in
:class:`agentlabx.mcp.protocol.ServerStartupFailed` (the public
caller-facing exception) with the spec attached.

Three launchers ship in A3:

* :class:`StdioLauncher` — subprocess stdio (the dominant transport for
  third-party MCP servers shipped via ``npx`` / ``uvx``).
* :class:`StreamableHTTPLauncher` — HTTP transport using the SDK's
  streamable-HTTP client (used by HTTP-hosted MCP servers).
* :class:`InProcessLauncher` — looks up an in-process server factory by key
  and wires it via the SDK's in-memory transport. The host owns the master
  factory registry and threads the same mapping reference through to every
  ``InProcessLauncher`` it constructs.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Iterator, Mapping
from contextlib import asynccontextmanager

import httpx
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.streamable_http import streamablehttp_client
from mcp.server import Server
from mcp.shared.exceptions import McpError
from mcp.shared.memory import create_connected_server_and_client_session


def _leaf_exceptions(group: BaseExceptionGroup[BaseException]) -> Iterator[BaseException]:
    """Yield leaf exceptions from a (possibly nested) ``BaseExceptionGroup``.

    anyio task groups (used inside the MCP SDK's stdio + streamable-HTTP
    clients) raise ``BaseExceptionGroup`` containing the actual cause.
    Walking to leaves lets the launcher surface ``ConnectError(...)``
    instead of ``ExceptionGroup(...)`` repr in the user-facing reason.
    """

    for child in group.exceptions:
        if isinstance(child, BaseExceptionGroup):
            yield from _leaf_exceptions(child)
        else:
            yield child


def _format_http_failure(url: str, exc: BaseException) -> str:
    """Render an httpx / OS-level transport failure as a clean English string.

    Caller passes ``url`` so the message can name the target. Falls back to
    ``str(exc)`` when no specific httpx subclass matches; never returns a
    Python type repr.
    """

    if isinstance(exc, httpx.ConnectError):
        return f"could not connect to {url!r}: {exc}"
    if isinstance(exc, httpx.ReadTimeout | httpx.WriteTimeout | httpx.ConnectTimeout):
        return f"timeout reaching {url!r}: {exc}"
    if isinstance(exc, httpx.HTTPStatusError):
        return f"upstream returned {exc.response.status_code} from {url!r}: {exc}"
    if isinstance(exc, httpx.HTTPError):
        return f"http error from {url!r}: {exc}"
    if isinstance(exc, OSError):
        return f"OS error reaching {url!r}: {exc.strerror or exc}"
    if isinstance(exc, McpError):
        return f"MCP protocol error from {url!r}: {exc}"
    return f"transport failure for {url!r}: {type(exc).__name__}: {exc}"


# `mcp.server.Server` is generic over `(LifespanResultT, RequestT)`; bundle
# factories may parameterise either, so we keep the registry annotation loose
# at the structural level (no `Any`, but accept the most permissive ``object``
# parameterisation).
ServerFactory = Callable[[], "Server[object, object]"]


class TransportOpenFailed(RuntimeError):  # noqa: N818  — name fixed by Stage A3 plan
    """Raised by a launcher when its underlying transport open fails.

    The host catches this (and other narrow SDK errors) and re-raises a
    :class:`agentlabx.mcp.protocol.ServerStartupFailed` carrying the
    :class:`MCPServerSpec` that the launcher itself does not know about.
    """


class StdioLauncher:
    """Launch an MCP server as a subprocess and connect over stdio.

    ``command`` follows the conventional ``(executable, *args)`` shape; the
    first element is the program to spawn and the remainder are positional
    arguments. ``env`` is passed through to the child process verbatim — the
    host is responsible for resolving secret slots into env-var values
    (typically ``AGENTLABX_SLOT_<UPPER>``) before constructing the launcher.
    """

    def __init__(self, command: tuple[str, ...], env: Mapping[str, str]) -> None:
        if not command:
            raise ValueError("StdioLauncher requires a non-empty command tuple")
        self._command: tuple[str, ...] = command
        self._env: dict[str, str] = dict(env)

    @asynccontextmanager
    async def open(self) -> AsyncIterator[ClientSession]:
        params = StdioServerParameters(
            command=self._command[0],
            args=list(self._command[1:]),
            # Pass an empty dict (rather than ``None``) so the SDK propagates
            # exactly the env we built; ``None`` would inherit the parent
            # process env which is not what callers want for slot-resolved
            # credentials.
            env=self._env,
        )
        try:
            async with (
                stdio_client(params) as (read, write),
                ClientSession(read, write) as session,
            ):
                await session.initialize()
                yield session
        except FileNotFoundError as exc:
            # Most common stdio failure: the launcher binary (uvx, npx,
            # python, etc.) is missing from PATH. Translate to an English
            # caller-actionable message instead of a localised OS string
            # wrapped in repr().
            argv0 = self._command[0] if self._command else "(no command)"
            raise TransportOpenFailed(
                f"stdio transport open failed: command not found: {argv0!r}"
            ) from exc
        except OSError as exc:
            # ``exc.strerror`` is locale-dependent on Windows; fall back to
            # ``str(exc)`` if absent. Either way no Python-type leakage.
            detail = exc.strerror or str(exc)
            raise TransportOpenFailed(f"stdio transport open failed: {detail}") from exc
        except McpError as exc:
            raise TransportOpenFailed(f"stdio transport open failed: {exc}") from exc


class StreamableHTTPLauncher:
    """Connect to an MCP server over the streamable-HTTP transport."""

    def __init__(self, url: str, headers: Mapping[str, str]) -> None:
        if not url:
            raise ValueError("StreamableHTTPLauncher requires a non-empty url")
        self._url: str = url
        self._headers: dict[str, str] = dict(headers)

    @asynccontextmanager
    async def open(self) -> AsyncIterator[ClientSession]:
        try:
            async with (
                streamablehttp_client(self._url, headers=self._headers) as (
                    read,
                    write,
                    _get_session_id,
                ),
                ClientSession(read, write) as session,
            ):
                await session.initialize()
                yield session
        except BaseExceptionGroup as group:
            # streamablehttp_client uses an inner anyio task group, so
            # transport failures arrive wrapped in ``ExceptionGroup``.
            # Flatten to the leaf so the user-facing reason names the
            # actual cause (httpx.ConnectError, ReadTimeout, etc.) instead
            # of an opaque ExceptionGroup repr.
            leaves = list(_leaf_exceptions(group))
            primary = leaves[0] if leaves else group
            raise TransportOpenFailed(
                f"http transport open failed: {_format_http_failure(self._url, primary)}"
            ) from primary
        except (httpx.HTTPError, OSError) as exc:
            raise TransportOpenFailed(
                f"http transport open failed: {_format_http_failure(self._url, exc)}"
            ) from exc
        except McpError as exc:
            raise TransportOpenFailed(
                f"http transport open failed: {_format_http_failure(self._url, exc)}"
            ) from exc


class InProcessLauncher:
    """Wire an in-process MCP server to a client session via memory streams.

    The host owns the master factory registry; each ``InProcessLauncher``
    receives the same ``factories`` mapping reference so adding a bundle to
    the host's registry at startup makes it instantly available to every
    subsequent launch.
    """

    def __init__(
        self,
        inprocess_key: str,
        factories: Mapping[str, ServerFactory],
    ) -> None:
        if not inprocess_key:
            raise ValueError("InProcessLauncher requires a non-empty inprocess_key")
        self._key: str = inprocess_key
        self._factories: Mapping[str, ServerFactory] = factories

    @asynccontextmanager
    async def open(self) -> AsyncIterator[ClientSession]:
        try:
            factory = self._factories[self._key]
        except KeyError as exc:
            raise TransportOpenFailed(
                f"no in-process MCP server factory registered for key {self._key!r}"
            ) from exc
        try:
            server = factory()
        except Exception as exc:  # noqa: BLE001 — intentional broad wrap
            raise TransportOpenFailed(
                f"in-process server factory for {self._key!r} raised: {exc!r}"
            ) from exc
        try:
            async with create_connected_server_and_client_session(server) as session:
                # The SDK's in-memory helper performs initialise itself when
                # constructing the session; calling ``initialize`` again would
                # double-handshake. Yield directly.
                yield session
        except McpError as exc:
            raise TransportOpenFailed(
                f"in-process transport open failed for {self._key!r}: {exc!r}"
            ) from exc


__all__ = [
    "InProcessLauncher",
    "ServerFactory",
    "StdioLauncher",
    "StreamableHTTPLauncher",
    "TransportOpenFailed",
]
