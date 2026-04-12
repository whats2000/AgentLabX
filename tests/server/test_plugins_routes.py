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


def _names(entries: list[dict]) -> list[str]:
    return [e["name"] for e in entries]


class TestPluginsRoute:
    def test_returns_all_plugin_types(self, client):
        r = client.get("/api/plugins")
        assert r.status_code == 200
        data = r.json()
        # Keys use the singular PluginType.value form
        for key in (
            "agent",
            "stage",
            "tool",
            "llm_provider",
            "execution_backend",
            "storage_backend",
            "code_agent",
        ):
            assert key in data, f"missing bucket: {key}"

    def test_entries_are_name_description_objects(self, client):
        """Every entry carries a name + description so the UI can render both."""
        r = client.get("/api/plugins")
        data = r.json()
        for bucket in data.values():
            for entry in bucket:
                assert isinstance(entry, dict)
                assert "name" in entry
                assert "description" in entry

    def test_agents_include_defaults(self, client):
        r = client.get("/api/plugins")
        names = _names(r.json()["agent"])
        for name in ["phd_student", "postdoc", "ml_engineer", "pi_agent"]:
            assert name in names

    def test_stages_include_defaults(self, client):
        r = client.get("/api/plugins")
        names = _names(r.json()["stage"])
        for name in [
            "literature_review",
            "plan_formulation",
            "experimentation",
            "peer_review",
        ]:
            assert name in names

    def test_tools_include_defaults(self, client):
        r = client.get("/api/plugins")
        names = _names(r.json()["tool"])
        for name in ["arxiv_search", "semantic_scholar", "code_executor", "latex_compiler"]:
            assert name in names

    def test_llm_provider_registered(self, client):
        """Mock provider is registered when use_mock_llm=True."""
        r = client.get("/api/plugins")
        names = _names(r.json()["llm_provider"])
        assert "mock" in names

    def test_execution_backend_registered(self, client):
        r = client.get("/api/plugins")
        names = _names(r.json()["execution_backend"])
        assert "subprocess" in names

    def test_storage_backend_registered(self, client):
        r = client.get("/api/plugins")
        names = _names(r.json()["storage_backend"])
        assert "sqlite" in names

    def test_code_agent_registered(self, client):
        r = client.get("/api/plugins")
        names = _names(r.json()["code_agent"])
        assert "builtin" in names

    def test_descriptions_are_populated(self, client):
        """A sample plugin from each major type has a non-empty description."""
        r = client.get("/api/plugins")
        data = r.json()

        def find(bucket: str, name: str) -> dict:
            return next(e for e in data[bucket] if e["name"] == name)

        assert find("tool", "arxiv_search")["description"]
        assert find("llm_provider", "mock")["description"]
        assert find("storage_backend", "sqlite")["description"]
        assert find("execution_backend", "subprocess")["description"]
        assert find("code_agent", "builtin")["description"]
