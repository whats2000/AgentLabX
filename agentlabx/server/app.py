"""FastAPI application factory."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agentlabx.core.config import Settings
from agentlabx.server.deps import AppContext, build_app_context
from agentlabx.server.routes import preferences, sessions


def create_app(
    *,
    settings: Settings | None = None,
    use_mock_llm: bool = False,
) -> FastAPI:
    """Factory for the FastAPI app.

    Uses a lifespan handler so the AppContext is constructed on startup and
    storage is cleanly closed on shutdown. This makes the app testable via
    httpx.AsyncClient(transport=ASGITransport(app=app)) without a real server.
    """
    if settings is None:
        settings = Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        context = await build_app_context(
            settings=settings,
            use_mock_llm=use_mock_llm,
        )
        app.state.context = context
        try:
            yield
        finally:
            if context.executor is not None:
                await context.executor.close()
            await context.storage.close()

    app = FastAPI(
        title="AgentLabX",
        version="0.1.0",
        description="Modular multi-instance research automation platform",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.server.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(sessions.router)
    app.include_router(preferences.router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": "0.1.0"}

    return app


def get_context(app: FastAPI) -> AppContext:
    """Helper for routes to access the shared app context from app.state."""
    return app.state.context
