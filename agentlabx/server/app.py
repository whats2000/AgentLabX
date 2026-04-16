from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response

from agentlabx.config.settings import AppSettings, BindMode
from agentlabx.db.migrations import apply_migrations
from agentlabx.db.session import DatabaseHandle
from agentlabx.events.bus import EventBus
from agentlabx.events.logger import JsonlEventSink
from agentlabx.security.fernet_store import FernetStore
from agentlabx.security.keyring_store import get_or_create_session_secret
from agentlabx.server.middleware import SessionConfig, install_session_middleware
from agentlabx.server.routers import auth as auth_router
from agentlabx.server.routers import health as health_router
from agentlabx.server.routers import runs as runs_router
from agentlabx.server.routers import settings as settings_router


async def create_app(settings: AppSettings) -> FastAPI:
    app = FastAPI(title="AgentLabX", version="0.1.0")
    db = DatabaseHandle(settings.db_path)
    await db.connect()
    await apply_migrations(db)

    crypto = FernetStore.from_keyring()
    cfg = SessionConfig(
        secret=get_or_create_session_secret(),
        secure=(settings.bind_mode is BindMode.LAN),
    )
    install_session_middleware(app, cfg=cfg, db=db)

    # Event bus + JSONL sink
    bus = EventBus()
    sink = JsonlEventSink(path=settings.audit_log_path)
    sink.install(bus)

    @app.middleware("http")
    async def inject_crypto_and_events(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request.state.crypto = crypto
        request.state.events = bus
        return await call_next(request)

    app.include_router(health_router.router)
    app.include_router(auth_router.router)
    app.include_router(settings_router.router)
    app.include_router(runs_router.router)

    app.state.db = db
    app.state.settings = settings
    app.state.crypto = crypto
    app.state.events = bus
    return app
