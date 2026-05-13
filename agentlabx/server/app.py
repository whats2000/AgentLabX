from __future__ import annotations

import asyncio
import contextlib
import logging
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
from agentlabx.server.middleware import (
    SessionConfig,
    install_session_middleware,
    install_session_middleware_lazy,
)
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

logger = logging.getLogger(__name__)


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
    for _bundle_name, module in bundles:
        # In-process bundles register under their spec's inprocess_key (which the
        # InProcessLauncher looks up at start time). Bundle entry-point names
        # may differ from the inprocess_key — the spec is the source of truth.
        if not hasattr(module, "build_server_factory"):
            continue
        spec = _bundle_spec(module, _bundle_name)
        if spec is None or spec.transport != "inprocess" or spec.inprocess_key is None:
            continue
        inprocess_factories[spec.inprocess_key] = module.build_server_factory(session_factory)

    registry = ServerRegistry(session_factory)
    host = MCPHost(
        registry=registry,
        slot_resolver=slot_resolver,
        event_bus=bus,
        inprocess_factories=inprocess_factories,
    )
    dispatcher = ToolDispatcher(host, bus, AlwaysAllow())

    disabled_reasons = await _seed_admin_bundles(
        registry=registry,
        slot_resolver=slot_resolver,
        bundles=bundles,
        event_bus=bus,
    )
    await _start_enabled_servers(registry=registry, host=host, event_bus=bus)
    await _log_bootstrap_audit(
        registry=registry,
        host=host,
        disabled_reasons=disabled_reasons,
    )

    # Modern FastAPI shutdown contract: a lifespan context manager that yields
    # immediately (startup already ran in this factory) and runs MCP teardown
    # on app exit. Replaces the deprecated ``@app.on_event("shutdown")``
    # registration so we don't emit a DeprecationWarning on every boot.
    #
    # NOTE: The ``async create_app`` path runs every async setup step (db
    # connect, MCP server starts) in the *caller's* event loop. That works
    # for the in-process ASGI test client because the test loop IS the
    # request-handling loop — but it's wrong for ``uvicorn.run(app)`` where
    # the caller's loop is a throwaway and Uvicorn spins up a new one. When
    # called from the CLI, the seeded MCP servers' owner tasks would die
    # with the throwaway loop and every request to invoke them would hang
    # forever. ``create_app_for_uvicorn`` (below) is the production path
    # and runs all async wiring inside Uvicorn's own loop via the lifespan.
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
    # Spec names (NOT entry-point names) of admin-scope bundles discovered
    # at boot — used by the router to mark rows as ``bundled`` in the
    # response and to short-circuit DELETE with a clear error (deleting a
    # bundle row is misleading: the seed loop re-creates it on next boot).
    bundled: set[str] = set()
    for bundle_name, module in bundles:
        spec = _bundle_spec(module, bundle_name)
        if spec is not None and spec.scope == "admin":
            bundled.add(spec.name)
    app.state.mcp_bundled_names = frozenset(bundled)

    return app


def create_app_default() -> FastAPI:
    """No-arg factory used by Uvicorn's ``--reload`` mode.

    The reloader spawns a child subprocess that re-imports the app each time
    a watched file changes, so it cannot accept a pre-built FastAPI instance.
    This wrapper reads :class:`AppSettings` from ``AGENTLABX_*`` env vars
    (the CLI sets these when ``--reload`` is on) and delegates to the
    standard :func:`create_app_for_uvicorn` factory.
    """

    return create_app_for_uvicorn(AppSettings())


def create_app_for_uvicorn(settings: AppSettings) -> FastAPI:
    """Build a FastAPI app whose async wiring runs inside Uvicorn's loop.

    The :func:`create_app` factory above is async and does its db / MCP
    bootstrap in the caller's event loop — which is correct for in-process
    ASGI test clients (where the test loop IS the request-handling loop)
    but wrong for ``uvicorn.run(app)``: the CLI's outer ``asyncio.run`` loop
    is torn down immediately after ``create_app`` returns, taking every
    spawned MCP owner task with it. The first request to invoke a seeded
    server then hangs forever because the owner task can never wake.

    This wrapper defers ALL async setup into a FastAPI lifespan startup
    phase that runs inside Uvicorn's loop. Routers and middleware are
    attached eagerly (they're sync) but the app's :attr:`state` slots are
    only populated when the lifespan starts, so request handlers see fully
    wired state by the time the first request arrives.
    """

    crypto = FernetStore.from_keyring()
    cfg = SessionConfig(
        secret=get_or_create_session_secret(),
        secure=(settings.bind_mode is BindMode.LAN),
        max_age_seconds=settings.session_max_age_seconds,
        remember_me_max_age_seconds=settings.remember_me_max_age_seconds,
    )

    @asynccontextmanager
    async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
        # ALL async wiring lives here so it executes inside Uvicorn's loop
        # — the same loop that will later drive request handlers and the
        # MCPHost owner tasks. Keep this body in sync with the legacy
        # async ``create_app`` above.
        db = DatabaseHandle(settings.db_path)
        await db.connect()
        await apply_migrations(db)
        await _assert_schema_version_pinned(db)

        bus = EventBus()
        sink = JsonlEventSink(path=settings.audit_log_path)
        sink.install(bus)

        limiter = LoginRateLimiter()

        session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
            db.engine, expire_on_commit=False
        )
        slot_resolver = SlotResolver(crypto, session_factory)

        bundles = _discover_bundles(event_bus=bus)
        inprocess_factories: dict[str, ServerFactory] = {}
        for _bundle_name, module in bundles:
            if not hasattr(module, "build_server_factory"):
                continue
            spec = _bundle_spec(module, _bundle_name)
            if spec is None or spec.transport != "inprocess" or spec.inprocess_key is None:
                continue
            inprocess_factories[spec.inprocess_key] = module.build_server_factory(session_factory)

        registry = ServerRegistry(session_factory)
        host = MCPHost(
            registry=registry,
            slot_resolver=slot_resolver,
            event_bus=bus,
            inprocess_factories=inprocess_factories,
        )
        dispatcher = ToolDispatcher(host, bus, AlwaysAllow())

        disabled_reasons = await _seed_admin_bundles(
            registry=registry,
            slot_resolver=slot_resolver,
            bundles=bundles,
            event_bus=bus,
        )
        await _start_enabled_servers(registry=registry, host=host, event_bus=bus)
        await _log_bootstrap_audit(
            registry=registry,
            host=host,
            disabled_reasons=disabled_reasons,
        )

        app.state.db = db
        app.state.settings = settings
        app.state.crypto = crypto
        app.state.events = bus
        app.state.login_limiter = limiter
        app.state.mcp_registry = registry
        app.state.mcp_host = host
        app.state.mcp_dispatcher = dispatcher

        try:
            yield
        finally:
            await host.stop_all()
            await db.close()

    app = FastAPI(title="AgentLabX", version="0.1.0", lifespan=_lifespan)

    # All middleware must be attached before the lifespan starts (Starlette
    # locks the middleware stack on first request). Both middlewares read
    # ``app.state`` at request time, so the lifespan-populated state is
    # live by the time anyone hits the app.
    install_session_middleware_lazy(app, cfg=cfg)

    @app.middleware("http")
    async def inject_crypto_and_events(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request.state.crypto = request.app.state.crypto
        request.state.events = request.app.state.events
        request.state.login_limiter = request.app.state.login_limiter
        return await call_next(request)

    app.include_router(health_router.router)
    app.include_router(auth_router.router)
    app.include_router(settings_router.router)
    app.include_router(runs_router.router)
    app.include_router(llm_router.router)
    app.include_router(mcp_router.router)

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
) -> dict[str, str]:
    """Idempotently UPSERT an admin-scope row for every discovered bundle.

    For required-slot bundles, ``enabled`` flips to 0 if any slot resolves to
    ``None``; otherwise to 1. Re-running this on every startup reconciles any
    drift introduced since the last boot (e.g. a slot was filled in via the
    settings UI).

    Returns a ``{bundle_name: reason}`` mapping for each bundle the seed loop
    decided to disable, so the bootstrap-audit log line can render a
    human-readable summary (e.g. ``"semantic_scholar: missing key"``). Bundles
    that are enabled, or bundles whose ``spec()`` returned ``None``, are
    omitted from the mapping.
    """
    disabled: dict[str, str] = {}
    for name, module in bundles:
        spec = _bundle_spec(module, bundle_name=name)
        if spec is None:
            continue
        if spec.scope != "admin":
            continue
        # Resolve required slots. Missing slot => disabled until filled.
        all_resolved = True
        missing_slot: str | None = None
        for slot in spec.env_slot_refs:
            value = await slot_resolver.resolve(owner_id=None, slot=slot)
            if value is None:
                all_resolved = False
                missing_slot = slot
                break
        desired_enabled = all_resolved
        if not desired_enabled and missing_slot is not None:
            disabled[spec.name] = f"missing slot {missing_slot!r}"

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
            # Reconcile launch spec in place: code changes to a bundle module
            # (renamed PyPI package, added slot refs, tweaked capabilities)
            # need to reach the DB row each boot. Name is the identity key so
            # the row id is preserved across the update.
            await registry.update_admin_spec(spec.name, spec)
            current_enabled = await registry.get_enabled(existing.id)
            if current_enabled is not None and current_enabled is not desired_enabled:
                await registry.set_enabled(existing.id, desired_enabled)
    return disabled


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


async def _log_bootstrap_audit(
    *,
    registry: ServerRegistry,
    host: MCPHost,
    disabled_reasons: dict[str, str],
) -> None:
    """Emit the operator-facing one-line MCP bundle health summary.

    Pulls the registered count from a single admin-scope listing
    (``list_visible_to`` with no user — admin-scope rows have ``owner_id IS
    NULL`` and are visible to every caller), the started count from
    :meth:`MCPHost.running_server_ids`, and the disabled-reason mapping from
    :func:`_seed_admin_bundles`'s return value. Renders e.g.::

        MCP bundles: 6 registered, 5 started, 1 disabled (semantic_scholar:
        missing slot 'semantic_scholar_api_key')

    Per the plan: launcher absence (Docker / uvx / npx) is a misconfiguration
    that surfaces as ``mcp.server.startup_failed`` per bundle, *not* as a
    silent ``disabled`` count, so the audit line uses the seeded
    ``disabled_reasons`` mapping verbatim and does not synthesise launcher-
    related entries.
    """

    # Use a sentinel user id that no real user owns; admin-scope rows are
    # returned regardless because their ``owner_id IS NULL`` clause matches
    # every caller. The user-scope rows that come back are negligible at boot
    # time (none exist before the first end-user logs in) but we still scope
    # the count to admin-scope to keep the message accurate post-launch.
    rows = await registry.list_visible_to(user_id="__bootstrap_audit__")
    admin_rows = [r for r in rows if r.spec.scope == "admin"]
    total_registered = len(admin_rows)
    total_started = len(host.running_server_ids())
    total_disabled = max(total_registered - total_started, 0)

    if disabled_reasons:
        summary = ", ".join(
            f"{name}: {reason}" for name, reason in sorted(disabled_reasons.items())
        )
    else:
        summary = "none"

    logger.info(
        "MCP bundles: %d registered, %d started, %d disabled (%s)",
        total_registered,
        total_started,
        total_disabled,
        summary,
    )
