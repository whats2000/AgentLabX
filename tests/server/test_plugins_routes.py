"""Tests for /api/plugins."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from agentlabx.server.app import create_app


@pytest.fixture()
def client(tmp_path):
    os.environ["AGENTLABX_STORAGE__DATABASE_URL"] = f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"
    os.environ["AGENTLABX_STORAGE__ARTIFACTS_PATH"] = str(tmp_path / "artifacts")
    app = create_app(use_mock_llm=True)
    with TestClient(app) as c:
        yield c
    os.environ.pop("AGENTLABX_STORAGE__DATABASE_URL", None)
    os.environ.pop("AGENTLABX_STORAGE__ARTIFACTS_PATH", None)


class TestPluginsRoute:
    def test_returns_all_plugin_types(self, client):
        r = client.get("/api/plugins")
        assert r.status_code == 200
        data = r.json()
        assert "agent" in data
        assert "stage" in data
        assert "tool" in data

    def test_agents_include_defaults(self, client):
        r = client.get("/api/plugins")
        data = r.json()
        agents = data["agent"]
        for name in ["phd_student", "postdoc", "ml_engineer", "pi_agent"]:
            assert name in agents

    def test_stages_include_defaults(self, client):
        r = client.get("/api/plugins")
        data = r.json()
        stages = data["stage"]
        for name in ["literature_review", "plan_formulation", "experimentation", "peer_review"]:
            assert name in stages

    def test_tools_include_defaults(self, client):
        r = client.get("/api/plugins")
        data = r.json()
        tools = data["tool"]
        for name in ["arxiv_search", "semantic_scholar", "code_executor", "latex_compiler"]:
            assert name in tools
