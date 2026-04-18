from __future__ import annotations

import importlib.resources
import logging
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response

from agentlabx.config.settings import AppSettings, BindMode
from agentlabx.db.migrations import apply_migrations
from agentlabx.db.session import DatabaseHandle
from agentlabx.events.bus import EventBus
from agentlabx.events.logger import JsonlEventSink
from agentlabx.llm.catalog import ProviderCatalog
from agentlabx.security.fernet_store import FernetStore
from agentlabx.security.keyring_store import get_or_create_session_secret
from agentlabx.server.middleware import SessionConfig, install_session_middleware
from agentlabx.server.rate_limit import LoginRateLimiter
from agentlabx.server.routers import auth as auth_router
from agentlabx.server.routers import health as health_router
from agentlabx.server.routers import llm as llm_router
from agentlabx.server.routers import runs as runs_router
from agentlabx.server.routers import settings as settings_router

_log = logging.getLogger(__name__)


async def create_app(settings: AppSettings) -> FastAPI:
    app = FastAPI(title="AgentLabX", version="0.1.0")
    db = DatabaseHandle(settings.db_path)
    await db.connect()
    await apply_migrations(db)

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

    @app.middleware("http")
    async def inject_crypto_and_events(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request.state.crypto = crypto
        request.state.events = bus
        request.state.login_limiter = request.app.state.login_limiter
        return await call_next(request)

    # Provider catalog — resolve from settings, fall back to package data
    catalog_path = settings.catalog_path
    if catalog_path is not None and catalog_path.exists():
        catalog = ProviderCatalog.from_file(catalog_path)
    else:
        try:
            ref = importlib.resources.files("agentlabx.data").joinpath("providers.yaml")
            with importlib.resources.as_file(ref) as p:
                catalog = ProviderCatalog.from_file(p)
        except (FileNotFoundError, TypeError, ModuleNotFoundError):
            _log.warning("providers.yaml not found — catalog is empty")
            catalog = ProviderCatalog(providers=[])
    app.state.catalog = catalog

    app.include_router(health_router.router)
    app.include_router(auth_router.router)
    app.include_router(settings_router.router)
    app.include_router(runs_router.router)
    app.include_router(llm_router.router)

    app.state.db = db
    app.state.settings = settings
    app.state.crypto = crypto
    app.state.events = bus
    return app
