"""Serve the built React SPA from web/dist."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

logger = logging.getLogger(__name__)


def mount_spa(app: FastAPI, web_dist: Path | None = None) -> None:
    """Mount the built React bundle at /.

    If web_dist is None, auto-detect at <repo_root>/web/dist. If the directory
    does not exist (no build has been run), skip the mount with a warning so
    the API-only mode still works.

    Must be called LAST in create_app, after every API and WebSocket router
    has been included — FastAPI dispatches by registration order, so real
    routes take precedence over the catchall (Fix I: no defensive startswith
    guard needed).
    """
    if web_dist is None:
        web_dist = Path(__file__).resolve().parents[2] / "web" / "dist"
    if not web_dist.exists() or not (web_dist / "index.html").exists():
        logger.info("No web/dist found at %s — running API-only.", web_dist)
        return

    assets_dir = web_dist / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    favicon_path = web_dist / "favicon.svg"

    @app.get("/favicon.svg", include_in_schema=False)
    async def favicon() -> FileResponse:
        return FileResponse(favicon_path)

    @app.get("/", include_in_schema=False)
    async def spa_root() -> FileResponse:
        return FileResponse(web_dist / "index.html")

    # Catchall must be LAST. Real API/WS/docs routes are registered earlier and
    # take precedence; only unmatched paths reach here. Fix I: no path prefix
    # filtering — FastAPI's route precedence is the source of truth.
    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_catchall(full_path: str) -> FileResponse:
        return FileResponse(web_dist / "index.html")
