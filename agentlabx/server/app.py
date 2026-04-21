from __future__ import annotations

from collections.abc import Awaitable, Callable
from importlib import metadata as importlib_metadata

from fastapi import FastAPI, Request, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentlabx.config.settings import AppSettings, BindMode
from agentlabx.db.migrations import CURRENT_SCHEMA_VERSION, apply_migrations
from agentlabx.db.session import DatabaseHandle
from agentlabx.events.bus import Event, EventBus
from agentlabx.events.logger import JsonlEventSink
from agentlabx.mcp.bundles import memory_server as memory_bundle
from agentlabx.mcp.dispatcher import AlwaysAllow, ToolDispatcher
from agentlabx.mcp.host import MCPHost
from agentlabx.mcp.protocol import MCPServerSpec, ServerStartupFailed
from agentlabx.mcp.registry import ServerRegistry
from agentlabx.mcp.transport import ServerFactory
from agentlabx.security.fernet_store import FernetStore
from agentlabx.security.keyring_store import get_or_create_session_secret
from agentlabx.security.slot_resolver import SlotResolver
from agentlabx.server.middleware import SessionConfig, install_session_middleware
from agentlabx.server.rate_limit import LoginRateLimiter
from agentlabx.server.routers import auth as auth_router
from agentlabx.server.routers import health as health_router
from agentlabx.server.routers import llm as llm_router
from agentlabx.server.routers import mcp as mcp_router
from agentlabx.server.routers import runs as runs_router
from agentlabx.server.routers import settings as settings_router

# Hardcoded bundle list — Task 9 will register these via the
# ``agentlabx.mcp_bundles`` entry-point group in ``pyproject.toml`` and
# this module will switch to ``importlib.metadata.entry_points`` discovery.
# A3 Task 7 only ships the memory bundle; the discovery code path is exercised
# at startup so the swap is purely a configuration change.
_BUNDLE_ENTRY_POINT_GROUP = "agentlabx.mcp_bundles"


async def create_app(settings: AppSettings) -> FastAPI:
    app = FastAPI(title="AgentLabX", version="0.1.0")
    db = DatabaseHandle(settings.db_path)
    await db.connect()
    await apply_migrations(db)
    await _assert_schema_version_pinned(db)

    crypto = FernetStore.from_keyring()
    cfg = SessionConfig(
        secret=get_or_create_session_secret(),
        secure=(settings.bind_mode is BindMode.LAN),
        max_age_seconds=settings.session_max_age_seconds,
        remember_me_max_age_seconds=settings.remember_me_max_age_seconds,
    )
    install_session_middleware(app, cfg=cfg, db=db)

    # Event bus + JSONL sink
    bus = EventBus()
    sink = JsonlEventSink(path=settings.audit_log_path)
    sink.install(bus)

    limiter = LoginRateLimiter()
    app.state.login_limiter = limiter

    # ------------------------------------------------------------------
    # MCP wiring (Stage A3 Task 7)
    # ------------------------------------------------------------------
    session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
        db.engine, expire_on_commit=False
    )
    slot_resolver = SlotResolver(crypto, session_factory)

    bundles = _discover_bundles()
    inprocess_factories: dict[str, ServerFactory] = {}
    for bundle_name, module in bundles:
        # Each bundle exposes its in-process factory as ``build_server_factory``
        # if (and only if) it ships an in-process MCP server. The memory bundle
        # is the only one in A3; future bundles add themselves to this dict by
        # exposing the same callable.
        if hasattr(module, "build_server_factory") and bundle_name == "memory_server":
            inprocess_factories[bundle_name] = module.build_server_factory(session_factory)

    registry = ServerRegistry(session_factory)
    host = MCPHost(
        registry=registry,
        slot_resolver=slot_resolver,
        event_bus=bus,
        inprocess_factories=inprocess_factories,
    )
    dispatcher = ToolDispatcher(host, bus, AlwaysAllow())

    await _seed_admin_bundles(
        registry=registry,
        slot_resolver=slot_resolver,
        bundles=bundles,
    )
    await _start_enabled_servers(registry=registry, host=host, event_bus=bus)

    @app.middleware("http")
    async def inject_crypto_and_events(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request.state.crypto = crypto
        request.state.events = bus
        request.state.login_limiter = request.app.state.login_limiter
        return await call_next(request)

    app.include_router(health_router.router)
    app.include_router(auth_router.router)
    app.include_router(settings_router.router)
    app.include_router(runs_router.router)
    app.include_router(llm_router.router)
    app.include_router(mcp_router.router)

    app.state.db = db
    app.state.settings = settings
    app.state.crypto = crypto
    app.state.events = bus
    app.state.mcp_registry = registry
    app.state.mcp_host = host
    app.state.mcp_dispatcher = dispatcher

    @app.on_event("shutdown")
    async def _shutdown_mcp() -> None:
        await host.stop_all()

    return app


# ---------------------------------------------------------------------------
# Schema version pin
# ---------------------------------------------------------------------------


async def _assert_schema_version_pinned(db: DatabaseHandle) -> None:
    """Re-read the migration table and assert it matches ``CURRENT_SCHEMA_VERSION``.

    A3's `apply_migrations` walks forward to v5; this guard surfaces any
    silent regression (e.g. a stale dev DB that didn't migrate) as a loud
    boot failure rather than letting the MCP code paths break in obscure ways.
    """
    async with db.session() as session:
        # The persistent version lives in the ``app_state`` row keyed
        # ``schema_version`` (see ``apply_migrations``); A3's plan suggests
        # a ``schema_migrations`` table but the live A1 schema uses
        # ``app_state``. We assert against whichever is authoritative.
        result = await session.execute(
            text("SELECT value FROM app_state WHERE key = 'schema_version'")
        )
        row = result.first()
    if row is None:
        raise RuntimeError("schema_version row missing from app_state after migrations")
    version = int(row[0])
    if version != CURRENT_SCHEMA_VERSION:
        raise RuntimeError(
            f"schema_version mismatch after migrations: got {version}, "
            f"expected {CURRENT_SCHEMA_VERSION}"
        )


# ---------------------------------------------------------------------------
# Bundle discovery + admin-scope seeding
# ---------------------------------------------------------------------------


_Bundle = tuple[str, object]
"""``(bundle_name, module)`` pair. Module loosely typed because bundles only
need to expose a small structural surface — ``spec()`` and (optionally)
``build_server_factory(...)`` — that does not warrant a Protocol class."""


def _discover_bundles() -> list[_Bundle]:
    """Discover MCP bundles via the ``agentlabx.mcp_bundles`` entry-point group.

    Falls back to a hardcoded ``[("memory_server", memory_bundle)]`` if the
    entry point is not registered (Task 9 will register it in
    ``pyproject.toml``). Either path produces the same in-memory list.
    """
    try:
        eps = importlib_metadata.entry_points(group=_BUNDLE_ENTRY_POINT_GROUP)
    except TypeError:
        # Older importlib.metadata signature — shouldn't trigger on 3.12 but
        # belt-and-braces for environments running an older shim.
        eps = ()  # type: ignore[assignment]
    discovered: list[_Bundle] = []
    seen: set[str] = set()
    for ep in eps:
        try:
            module = ep.load()
        except Exception:  # noqa: BLE001 — skip broken bundles, don't crash boot
            continue
        if ep.name in seen:
            continue
        seen.add(ep.name)
        discovered.append((ep.name, module))
    if "memory_server" not in seen:
        discovered.append(("memory_server", memory_bundle))
    return discovered


def _bundle_spec(module: object) -> MCPServerSpec | None:
    """Return the bundle's launch spec by calling its ``spec()`` factory.

    The memory bundle in A3 does not yet expose a ``spec()`` callable (Task 9
    introduces that contract for the launch-spec bundles). We synthesise one
    here so the seed loop has uniform input.
    """
    spec_callable = getattr(module, "spec", None)
    if callable(spec_callable):
        candidate = spec_callable()
        if isinstance(candidate, MCPServerSpec):
            return candidate
        return None
    if module is memory_bundle:
        return MCPServerSpec(
            name="memory",
            scope="admin",
            transport="inprocess",
            command=None,
            url=None,
            inprocess_key="memory_server",
            env_slot_refs=(),
            declared_capabilities=memory_bundle.DECLARED_CAPABILITIES,
        )
    return None


async def _seed_admin_bundles(
    *,
    registry: ServerRegistry,
    slot_resolver: SlotResolver,
    bundles: list[_Bundle],
) -> None:
    """Idempotently UPSERT an admin-scope row for every discovered bundle.

    For required-slot bundles, ``enabled`` flips to 0 if any slot resolves to
    ``None``; otherwise to 1. Re-running this on every startup reconciles any
    drift introduced since the last boot (e.g. a slot was filled in via the
    settings UI).
    """
    from sqlalchemy import select

    from agentlabx.db.schema import MCPServer

    for _name, module in bundles:
        spec = _bundle_spec(module)
        if spec is None:
            continue
        if spec.scope != "admin":
            continue
        # Resolve required slots. Missing slot => disabled until filled.
        all_resolved = True
        for slot in spec.env_slot_refs:
            value = await slot_resolver.resolve(owner_id=None, slot=slot)
            if value is None:
                all_resolved = False
                break
        enabled_int = 1 if all_resolved else 0

        async with registry._sessionmaker() as session:  # noqa: SLF001 — internal seed
            existing = (
                await session.execute(
                    select(MCPServer).where(
                        MCPServer.scope == spec.scope,
                        MCPServer.owner_id.is_(None),
                        MCPServer.name == spec.name,
                    )
                )
            ).scalar_one_or_none()
            if existing is None:
                try:
                    await registry.register(spec, owner_id=None)
                except Exception:  # noqa: BLE001 — seed failures must not block boot
                    continue
                # set enabled if needed (registry defaults to 1)
                if enabled_int == 0:
                    fresh = (
                        await session.execute(
                            select(MCPServer).where(
                                MCPServer.scope == spec.scope,
                                MCPServer.owner_id.is_(None),
                                MCPServer.name == spec.name,
                            )
                        )
                    ).scalar_one_or_none()
                    if fresh is not None:
                        await registry.set_enabled(fresh.id, False)
            else:
                # Reconcile enabled flag only — name/transport are part of the
                # identity key and changing them would orphan the row.
                if existing.enabled != enabled_int:
                    await registry.set_enabled(existing.id, bool(enabled_int))


async def _start_enabled_servers(
    *, registry: ServerRegistry, host: MCPHost, event_bus: EventBus
) -> None:
    """Start every ``enabled=1`` server from the registry.

    Failures are isolated per server: ``mcp.server.startup_failed`` is emitted
    and the loop continues so a single broken bundle cannot block boot.
    """
    from sqlalchemy import select

    from agentlabx.db.schema import MCPServer

    async with registry._sessionmaker() as session:  # noqa: SLF001 — internal startup
        rows = (
            (await session.execute(select(MCPServer).where(MCPServer.enabled == 1))).scalars().all()
        )
        ids = [r.id for r in rows]

    for server_id in ids:
        registered = await registry.get(server_id)
        if registered is None:
            continue
        try:
            await host.start(registered, owner_id=registered.owner_id)
        except ServerStartupFailed as exc:
            await event_bus.emit(
                Event(
                    kind="mcp.server.startup_failed",
                    payload={
                        "server_id": registered.id,
                        "server_name": registered.spec.name,
                        "reason": exc.reason,
                    },
                )
            )
        except Exception as exc:  # noqa: BLE001 — defensive: never abort boot
            await event_bus.emit(
                Event(
                    kind="mcp.server.startup_failed",
                    payload={
                        "server_id": registered.id,
                        "server_name": registered.spec.name,
                        "reason": f"unexpected error: {exc!r}",
                    },
                )
            )
