"""Tests for the FastAPI app factory."""

from __future__ import annotations

import os

from httpx import ASGITransport, AsyncClient

from agentlabx.server.app import create_app


class TestApp:
    async def test_health_endpoint(self, tmp_path):
        # Override storage to use tmp dir so we don't pollute the repo
        os.environ["AGENTLABX_STORAGE__DATABASE_URL"] = (
            f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"
        )
        os.environ["AGENTLABX_STORAGE__ARTIFACTS_PATH"] = str(tmp_path / "artifacts")

        try:
            app = create_app(use_mock_llm=True)
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                # Lifespan runs via the transport
                response = await client.get("/health")
            assert response.status_code == 200
            body = response.json()
            assert body["status"] == "ok"
            assert body["version"] == "0.1.0"
        finally:
            os.environ.pop("AGENTLABX_STORAGE__DATABASE_URL", None)
            os.environ.pop("AGENTLABX_STORAGE__ARTIFACTS_PATH", None)

    async def test_app_has_context_after_startup(self, tmp_path):
        """Verify that lifespan builds and stores AppContext on app.state.

        Uses starlette.testclient.TestClient (sync) because it reliably triggers
        ASGI lifespan events — ASGITransport does not fire lifespan by design.
        """
        from starlette.testclient import TestClient

        os.environ["AGENTLABX_STORAGE__DATABASE_URL"] = (
            f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"
        )
        os.environ["AGENTLABX_STORAGE__ARTIFACTS_PATH"] = str(tmp_path / "artifacts")
        try:
            app = create_app(use_mock_llm=True)
            with TestClient(app) as client:
                response = client.get("/health")
                assert response.status_code == 200
                # Lifespan has fired; context must be set while client is open
                assert hasattr(app.state, "context")
                assert app.state.context.registry is not None
                assert app.state.context.session_manager is not None
                assert app.state.context.llm_provider is not None
                assert app.state.context.storage is not None
        finally:
            os.environ.pop("AGENTLABX_STORAGE__DATABASE_URL", None)
            os.environ.pop("AGENTLABX_STORAGE__ARTIFACTS_PATH", None)

    async def test_cors_headers_present(self, tmp_path):
        os.environ["AGENTLABX_STORAGE__DATABASE_URL"] = (
            f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"
        )
        os.environ["AGENTLABX_STORAGE__ARTIFACTS_PATH"] = str(tmp_path / "artifacts")
        try:
            app = create_app(use_mock_llm=True)
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.options(
                    "/health",
                    headers={
                        "Origin": "http://example.com",
                        "Access-Control-Request-Method": "GET",
                    },
                )
            # CORS middleware responds with 200 + headers for preflight
            assert response.status_code == 200
            assert "access-control-allow-origin" in [h.lower() for h in response.headers.keys()]
        finally:
            os.environ.pop("AGENTLABX_STORAGE__DATABASE_URL", None)
            os.environ.pop("AGENTLABX_STORAGE__ARTIFACTS_PATH", None)


class TestBuildDefaultRegistry:
    """Unit tests for build_default_registry without needing app startup."""

    def test_registers_all_agents(self):
        from agentlabx.core.registry import PluginType
        from agentlabx.server.deps import build_default_registry

        registry = build_default_registry()
        for name in [
            "phd_student",
            "postdoc",
            "ml_engineer",
            "sw_engineer",
            "professor",
            "reviewers",
            "pi_agent",
        ]:
            assert registry.has_plugin(PluginType.AGENT, name)

    def test_registers_all_stages(self):
        from agentlabx.core.registry import PluginType
        from agentlabx.server.deps import build_default_registry

        registry = build_default_registry()
        for name in [
            "literature_review",
            "plan_formulation",
            "data_exploration",
            "data_preparation",
            "experimentation",
            "results_interpretation",
            "report_writing",
            "peer_review",
        ]:
            assert registry.has_plugin(PluginType.STAGE, name)

    def test_registers_stateless_tools(self):
        from agentlabx.core.registry import PluginType
        from agentlabx.server.deps import build_default_registry

        registry = build_default_registry()
        for name in [
            "arxiv_search",
            "semantic_scholar",
            "hf_dataset_search",
            "github_search",
            "latex_compiler",
        ]:
            assert registry.has_plugin(PluginType.TOOL, name)
