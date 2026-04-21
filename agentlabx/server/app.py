from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from importlib import metadata as importlib_metadata
from types import ModuleType

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

    # Event bus + JSONL sink
    bus = EventBus()
    sink = JsonlEventSink(path=settings.audit_log_path)
    sink.install(bus)

    limiter = LoginRateLimiter()

    # ------------------------------------------------------------------
    # MCP wiring (Stage A3 Task 7)
    # ------------------------------------------------------------------
    session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
        db.engine, expire_on_commit=False
    )
    slot_resolver = SlotResolver(crypto, session_factory)

    bundles = _discover_bundles(event_bus=bus)
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
        event_bus=bus,
    )
    await _start_enabled_servers(registry=registry, host=host, event_bus=bus)

    # Modern FastAPI shutdown contract: a lifespan context manager that yields
    # immediately (startup already ran in this factory) and runs MCP teardown
    # on app exit. Replaces the deprecated ``@app.on_event("shutdown")``
    # registration so we don't emit a DeprecationWarning on every boot. Folding
    # the full startup body into the lifespan would require restructuring the
    # ``async create_app`` factory contract that callers/tests already rely
    # on, so we scope this conversion to just the shutdown half per the polish
    # plan.
    @asynccontextmanager
    async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            await host.stop_all()

    app = FastAPI(title="AgentLabX", version="0.1.0", lifespan=_lifespan)
    install_session_middleware(app, cfg=cfg, db=db)
    app.state.login_limiter = limiter

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


_Bundle = tuple[str, ModuleType]
"""``(bundle_name, module)`` pair. Module loosely typed because bundles only
need to expose a small structural surface — ``spec()`` and (optionally)
``build_server_factory(...)`` — that does not warrant a Protocol class."""


def _discover_bundles(*, event_bus: EventBus | None = None) -> list[_Bundle]:
    """Discover MCP bundles via the ``agentlabx.mcp_bundles`` entry-point group.

    Falls back to a hardcoded ``[("memory_server", memory_bundle)]`` if the
    entry point is not registered (Task 9 will register it in
    ``pyproject.toml``). Either path produces the same in-memory list.

    Bundle import failures emit ``mcp.bundle.discovery_failed`` (when an
    ``event_bus`` is supplied) before being skipped, so a broken third-party
    bundle is observable instead of silently disappearing from the registry.
    """
    eps = importlib_metadata.entry_points(group=_BUNDLE_ENTRY_POINT_GROUP)
    discovered: list[_Bundle] = []
    seen: set[str] = set()
    for ep in eps:
        try:
            module = ep.load()
        except Exception as exc:  # noqa: BLE001 — observe and skip broken bundles
            if event_bus is not None:
                # Fire-and-forget: emit is async but discovery is sync. We
                # schedule the emit on the running loop so a malformed bundle
                # surfaces in the audit log without rewiring discovery to
                # async. Falls back silently if no loop is running (e.g. when
                # _discover_bundles is called from a unit test outside an
                # event loop).
                with contextlib.suppress(RuntimeError):
                    asyncio.get_running_loop().create_task(
                        event_bus.emit(
                            Event(
                                kind="mcp.bundle.discovery_failed",
                                payload={
                                    "entry_point": ep.name,
                                    "error_type": type(exc).__name__,
                                    "reason": str(exc),
                                },
                            )
                        )
                    )
            continue
        if ep.name in seen:
            continue
        seen.add(ep.name)
        discovered.append((ep.name, module))
    # Hardcoded safety-net for the memory bundle: ensures the in-process server
    # is always wired even if the ``agentlabx.mcp_bundles`` entry-points are
    # absent (e.g. running from a checkout without a fresh ``uv sync``). The EP
    # name is ``memory``; the fallback bundle name remains ``memory_server`` so
    # the in-process factory dict key stays stable. Skip the fallback when
    # either name has already been seen via entry-points.
    if "memory_server" not in seen and "memory" not in seen:
        discovered.append(("memory_server", memory_bundle))
    return discovered


def _bundle_spec(module: ModuleType, bundle_name: str | None = None) -> MCPServerSpec | None:
    """Return the bundle's launch spec.

    Prefers the bundle's own ``spec()`` callable (the Task 9 contract). Falls
    back to a synthesised spec for the memory bundle as a defence-in-depth
    safety net for any future bundle that ships without ``spec()``; the
    fallback only fires when ``module is memory_bundle``.

    Errors raised from a bundle's ``spec()`` are swallowed and surfaced as
    ``None`` so a single broken bundle cannot abort the seed loop. Discovery-
    layer error reporting (``mcp.bundle.discovery_failed``) covers the
    observability gap; the seed loop additionally emits
    ``mcp.bundle.seed_failed`` if registration itself fails downstream.
    """
    del bundle_name  # currently unused; reserved for future per-bundle policy
    spec_callable = getattr(module, "spec", None)
    if callable(spec_callable):
        try:
            candidate = spec_callable()
        except Exception:  # noqa: BLE001 — broken bundle must not abort seeding
            return None
        if isinstance(candidate, MCPServerSpec):
            return candidate
        return None
    if module is memory_bundle:
        # Safety-net synthesis kept in lockstep with ``memory_bundle.spec()``.
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
    event_bus: EventBus,
) -> None:
    """Idempotently UPSERT an admin-scope row for every discovered bundle.

    For required-slot bundles, ``enabled`` flips to 0 if any slot resolves to
    ``None``; otherwise to 1. Re-running this on every startup reconciles any
    drift introduced since the last boot (e.g. a slot was filled in via the
    settings UI).
    """
    for name, module in bundles:
        spec = _bundle_spec(module, bundle_name=name)
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
        desired_enabled = all_resolved

        existing = await registry.find_admin_by_name(spec.name)
        if existing is None:
            try:
                registered = await registry.register(spec, owner_id=None)
            except Exception as exc:  # noqa: BLE001 — seed failures must not block boot
                await event_bus.emit(
                    Event(
                        kind="mcp.bundle.seed_failed",
                        payload={
                            "bundle": spec.name,
                            "error_type": type(exc).__name__,
                            "reason": str(exc),
                        },
                    )
                )
                continue
            # registry defaults new rows to enabled=1; flip down only when
            # required slots are missing.
            if not desired_enabled:
                await registry.set_enabled(registered.id, False)
        else:
            # Reconcile enabled flag only — name/transport are part of the
            # identity key and changing them would orphan the row.
            current_enabled = await registry.get_enabled(existing.id)
            if current_enabled is not None and current_enabled is not desired_enabled:
                await registry.set_enabled(existing.id, desired_enabled)


async def _start_enabled_servers(
    *, registry: ServerRegistry, host: MCPHost, event_bus: EventBus
) -> None:
    """Start every ``enabled=1`` server from the registry.

    Failures are isolated per server: ``mcp.server.startup_failed`` is emitted
    and the loop continues so a single broken bundle cannot block boot.
    """
    ids = await registry.list_enabled_ids()

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
