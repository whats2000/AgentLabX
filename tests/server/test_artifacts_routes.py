"""Tests for /api/sessions/{id}/artifacts, /transitions, /cost, /hypotheses."""

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


def _create_session(client, topic="test topic"):
    r = client.post("/api/sessions", json={"topic": topic})
    return r.json()["session_id"]


class TestArtifactsRoute:
    def test_empty_before_start(self, client):
        sid = _create_session(client)
        r = client.get(f"/api/sessions/{sid}/artifacts")
        assert r.status_code == 200
        data = r.json()
        # All arrays present and empty
        for key in ["literature_review", "plan", "experiment_results", "report"]:
            assert data[key] == []

    def test_missing_session_404(self, client):
        r = client.get("/api/sessions/sess-nonexistent/artifacts")
        assert r.status_code == 404


class TestTransitionsRoute:
    def test_empty_before_start(self, client):
        sid = _create_session(client)
        r = client.get(f"/api/sessions/{sid}/transitions")
        assert r.status_code == 200
        data = r.json()
        assert data["transitions"] == []
        assert data["completed_stages"] == []
        assert data["current_stage"] == ""
        assert data["total_iterations"] == 0

    def test_missing_session_404(self, client):
        r = client.get("/api/sessions/sess-nonexistent/transitions")
        assert r.status_code == 404


class TestCostRoute:
    def test_zero_before_start(self, client):
        sid = _create_session(client)
        r = client.get(f"/api/sessions/{sid}/cost")
        assert r.status_code == 200
        data = r.json()
        assert data["total_tokens_in"] == 0
        assert data["total_tokens_out"] == 0
        assert data["total_cost"] == 0.0

    def test_missing_session_404(self, client):
        r = client.get("/api/sessions/sess-nonexistent/cost")
        assert r.status_code == 404


class TestHypothesesRoute:
    def test_empty_before_start(self, client):
        sid = _create_session(client)
        r = client.get(f"/api/sessions/{sid}/hypotheses")
        assert r.status_code == 200
        data = r.json()
        assert data["hypotheses"] == []
        assert data["total_records"] == 0

    def test_missing_session_404(self, client):
        r = client.get("/api/sessions/sess-nonexistent/hypotheses")
        assert r.status_code == 404
