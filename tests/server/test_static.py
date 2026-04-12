"""Tests for SPA static file serving."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agentlabx.server.static import mount_spa

INDEX_HTML = "<!doctype html><html><body>react root</body></html>"
ASSET_JS = "console.log('agentlabx');"


@pytest.fixture()
def web_dist(tmp_path: Path) -> Path:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text(INDEX_HTML, encoding="utf-8")
    (dist / "favicon.svg").write_text("<svg/>", encoding="utf-8")
    assets = dist / "assets"
    assets.mkdir()
    (assets / "index.js").write_text(ASSET_JS, encoding="utf-8")
    return dist


class TestMountSpa:
    def test_root_serves_index(self, web_dist: Path) -> None:
        app = FastAPI()
        mount_spa(app, web_dist=web_dist)
        with TestClient(app) as client:
            r = client.get("/")
            assert r.status_code == 200
            assert "react root" in r.text

    def test_unknown_path_serves_index_for_spa_routing(self, web_dist: Path) -> None:
        """Fix I: any unmatched path falls through to index.html so React
        Router can handle client-side routes like /sessions/sess-123."""
        app = FastAPI()
        mount_spa(app, web_dist=web_dist)
        with TestClient(app) as client:
            assert "react root" in client.get("/sessions/sess-123").text
            assert "react root" in client.get("/documents").text  # "docs" prefix is NOT filtered

    def test_api_routes_take_precedence(self, web_dist: Path) -> None:
        """Real API routes are registered before the catchall, so they win."""
        app = FastAPI()

        @app.get("/api/ping")
        async def ping() -> dict[str, str]:
            return {"pong": "yes"}

        mount_spa(app, web_dist=web_dist)
        with TestClient(app) as client:
            r = client.get("/api/ping")
            assert r.status_code == 200
            assert r.json() == {"pong": "yes"}

    def test_openapi_json_still_works(self, web_dist: Path) -> None:
        app = FastAPI()
        mount_spa(app, web_dist=web_dist)
        with TestClient(app) as client:
            r = client.get("/openapi.json")
            assert r.status_code == 200
            assert r.headers["content-type"].startswith("application/json")

    def test_assets_served(self, web_dist: Path) -> None:
        app = FastAPI()
        mount_spa(app, web_dist=web_dist)
        with TestClient(app) as client:
            r = client.get("/assets/index.js")
            assert r.status_code == 200
            assert "agentlabx" in r.text

    def test_favicon_served(self, web_dist: Path) -> None:
        app = FastAPI()
        mount_spa(app, web_dist=web_dist)
        with TestClient(app) as client:
            r = client.get("/favicon.svg")
            assert r.status_code == 200

    def test_missing_dist_is_noop(self, tmp_path: Path) -> None:
        """API-only mode: if web/dist doesn't exist, mount_spa is silent."""
        app = FastAPI()

        @app.get("/health")
        async def health() -> dict[str, str]:
            return {"status": "ok"}

        missing = tmp_path / "never-built"
        mount_spa(app, web_dist=missing)

        with TestClient(app) as client:
            assert client.get("/health").status_code == 200
            # Root should 404 since no SPA is mounted
            assert client.get("/").status_code == 404

    def test_missing_index_is_noop(self, tmp_path: Path) -> None:
        """If the directory exists but index.html doesn't, skip the mount."""
        app = FastAPI()
        dist = tmp_path / "empty-dist"
        dist.mkdir()
        mount_spa(app, web_dist=dist)
        with TestClient(app) as client:
            assert client.get("/").status_code == 404
