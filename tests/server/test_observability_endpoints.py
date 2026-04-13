"""Tests for the 8 observability REST endpoints (B11).

Endpoints under test:
  GET /api/sessions/{id}/graph
  GET /api/sessions/{id}/agents
  GET /api/sessions/{id}/agents/{name}/context
  GET /api/sessions/{id}/agents/{name}/history
  GET /api/sessions/{id}/agents/{name}/memory
  GET /api/sessions/{id}/pi/history
  GET /api/sessions/{id}/requests
  GET /api/sessions/{id}/experiments

All tests use the sync TestClient pattern (consistent with the rest of the
server test suite). A freshly-created (not-yet-started) session is used
so tests are fast and require no mock LLM responses. Empty / default state
is checked rather than populated values.
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from agentlabx.server.app import create_app


@pytest.fixture()
def client(tmp_path):
    """TestClient with isolated storage/checkpoint DB per test."""
    os.environ["AGENTLABX_STORAGE__DATABASE_URL"] = (
        f"sqlite+aiosqlite:///{tmp_path / 'obs.db'}"
    )
    os.environ["AGENTLABX_STORAGE__ARTIFACTS_PATH"] = str(tmp_path / "artifacts")
    app = create_app(use_mock_llm=True)
    with TestClient(app) as c:
        yield c
    os.environ.pop("AGENTLABX_STORAGE__DATABASE_URL", None)
    os.environ.pop("AGENTLABX_STORAGE__ARTIFACTS_PATH", None)


@pytest.fixture()
def created_session(client):
    """Create a session and return its id."""
    r = client.post(
        "/api/sessions",
        json={"topic": "observability smoke", "user_id": "default", "config": {}},
    )
    assert r.status_code == 201
    return r.json()["session_id"]


class TestGraphEndpoint:
    def test_returns_owned_shape(self, client, created_session):
        r = client.get(f"/api/sessions/{created_session}/graph")
        assert r.status_code == 200
        data = r.json()
        assert set(data.keys()) >= {"nodes", "edges", "cursor", "subgraphs"}

    def test_nodes_and_edges_are_lists(self, client, created_session):
        r = client.get(f"/api/sessions/{created_session}/graph")
        data = r.json()
        assert isinstance(data["nodes"], list)
        assert isinstance(data["edges"], list)
        assert isinstance(data["subgraphs"], list)

    def test_missing_session_returns_404(self, client):
        r = client.get("/api/sessions/does-not-exist/graph")
        assert r.status_code == 404


class TestAgentsEndpoint:
    def test_lists_registered_agents(self, client, created_session):
        r = client.get(f"/api/sessions/{created_session}/agents")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_missing_session_returns_404(self, client):
        r = client.get("/api/sessions/does-not-exist/agents")
        assert r.status_code == 404


class TestAgentContextEndpoint:
    def test_returns_scope_shape(self, client, created_session):
        r = client.get(f"/api/sessions/{created_session}/agents/phd_student/context")
        assert r.status_code == 200
        data = r.json()
        assert set(data.keys()) >= {"keys", "preview", "scope"}
        assert {"read", "summarize", "write"} <= set(data["scope"].keys())

    def test_unknown_agent_returns_404(self, client, created_session):
        r = client.get(f"/api/sessions/{created_session}/agents/no_such_agent/context")
        assert r.status_code == 404

    def test_missing_session_returns_404(self, client):
        r = client.get("/api/sessions/does-not-exist/agents/phd_student/context")
        assert r.status_code == 404


class TestAgentHistoryEndpoint:
    def test_returns_turns_list(self, client, created_session):
        r = client.get(
            f"/api/sessions/{created_session}/agents/phd_student/history?limit=50"
        )
        assert r.status_code == 200
        body = r.json()
        assert "turns" in body
        assert isinstance(body["turns"], list)

    def test_missing_session_returns_404(self, client):
        r = client.get("/api/sessions/does-not-exist/agents/phd_student/history")
        assert r.status_code == 404


class TestAgentMemoryEndpoint:
    def test_returns_memory_record_shape(self, client, created_session):
        r = client.get(f"/api/sessions/{created_session}/agents/phd_student/memory")
        assert r.status_code == 200
        data = r.json()
        assert set(data.keys()) >= {"working_memory", "notes", "last_active_stage", "turn_count"}

    def test_missing_session_returns_404(self, client):
        r = client.get("/api/sessions/does-not-exist/agents/phd_student/memory")
        assert r.status_code == 404


class TestPiHistoryEndpoint:
    def test_returns_list(self, client, created_session):
        r = client.get(f"/api/sessions/{created_session}/pi/history")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_missing_session_returns_404(self, client):
        r = client.get("/api/sessions/does-not-exist/pi/history")
        assert r.status_code == 404


class TestRequestsEndpoint:
    def test_returns_pending_and_completed(self, client, created_session):
        r = client.get(f"/api/sessions/{created_session}/requests")
        assert r.status_code == 200
        data = r.json()
        assert set(data.keys()) == {"pending", "completed"}

    def test_missing_session_returns_404(self, client):
        r = client.get("/api/sessions/does-not-exist/requests")
        assert r.status_code == 404


class TestExperimentsEndpoint:
    def test_returns_runs_and_log(self, client, created_session):
        r = client.get(f"/api/sessions/{created_session}/experiments")
        assert r.status_code == 200
        data = r.json()
        assert set(data.keys()) >= {"runs", "log"}

    def test_missing_session_returns_404(self, client):
        r = client.get("/api/sessions/does-not-exist/experiments")
        assert r.status_code == 404
