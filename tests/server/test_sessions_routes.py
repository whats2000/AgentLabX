"""Tests for session REST endpoints."""

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


class TestSessionCreate:
    def test_create_returns_201(self, client):
        r = client.post("/api/sessions", json={"topic": "Test topic"})
        assert r.status_code == 201
        data = r.json()
        assert data["research_topic"] == "Test topic"
        assert data["status"] == "created"
        assert data["user_id"] == "default"
        assert data["session_id"].startswith("sess-")

    def test_create_with_user_id(self, client):
        r = client.post(
            "/api/sessions",
            json={"topic": "t", "user_id": "alice"},
        )
        assert r.status_code == 201
        assert r.json()["user_id"] == "alice"

    def test_create_with_config_overrides(self, client):
        r = client.post(
            "/api/sessions",
            json={"topic": "t", "config": {"llm": {"default_model": "gpt-4o"}}},
        )
        assert r.status_code == 201
        assert r.json()["config_overrides"] == {"llm": {"default_model": "gpt-4o"}}


class TestSessionList:
    def test_empty_list(self, client):
        r = client.get("/api/sessions")
        assert r.status_code == 200
        assert r.json() == []

    def test_list_all(self, client):
        client.post("/api/sessions", json={"topic": "a"})
        client.post("/api/sessions", json={"topic": "b"})
        r = client.get("/api/sessions")
        assert r.status_code == 200
        assert len(r.json()) == 2

    def test_list_filtered_by_user(self, client):
        client.post("/api/sessions", json={"topic": "a", "user_id": "alice"})
        client.post("/api/sessions", json={"topic": "b", "user_id": "bob"})
        client.post("/api/sessions", json={"topic": "c", "user_id": "alice"})
        r = client.get("/api/sessions?user_id=alice")
        assert r.status_code == 200
        assert len(r.json()) == 2
        assert all(s["user_id"] == "alice" for s in r.json())


class TestSessionGet:
    def test_get_existing(self, client):
        created = client.post("/api/sessions", json={"topic": "t"}).json()
        r = client.get(f"/api/sessions/{created['session_id']}")
        assert r.status_code == 200
        assert r.json()["session_id"] == created["session_id"]

    def test_get_missing_404(self, client):
        r = client.get("/api/sessions/sess-nonexistent")
        assert r.status_code == 404


class TestSessionStart:
    def test_start_from_created(self, client):
        sid = client.post("/api/sessions", json={"topic": "t"}).json()["session_id"]
        r = client.post(f"/api/sessions/{sid}/start")
        assert r.status_code == 202
        # Without executor, status transitions to running via session.start()
        assert r.json()["status"] == "running"

    def test_start_missing_404(self, client):
        r = client.post("/api/sessions/sess-nonexistent/start")
        assert r.status_code == 404

    def test_start_twice_409(self, client):
        sid = client.post("/api/sessions", json={"topic": "t"}).json()["session_id"]
        client.post(f"/api/sessions/{sid}/start")  # running
        r = client.post(f"/api/sessions/{sid}/start")
        assert r.status_code == 409


class TestSessionPauseResume:
    def test_pause_running(self, client):
        sid = client.post("/api/sessions", json={"topic": "t"}).json()["session_id"]
        client.post(f"/api/sessions/{sid}/start")
        r = client.post(f"/api/sessions/{sid}/pause")
        assert r.status_code == 202
        assert r.json()["status"] == "paused"

    def test_pause_not_running_409(self, client):
        sid = client.post("/api/sessions", json={"topic": "t"}).json()["session_id"]
        r = client.post(f"/api/sessions/{sid}/pause")
        assert r.status_code == 409

    def test_resume_paused(self, client):
        sid = client.post("/api/sessions", json={"topic": "t"}).json()["session_id"]
        client.post(f"/api/sessions/{sid}/start")
        client.post(f"/api/sessions/{sid}/pause")
        r = client.post(f"/api/sessions/{sid}/resume")
        assert r.status_code == 202
        assert r.json()["status"] == "running"

    def test_resume_not_paused_409(self, client):
        sid = client.post("/api/sessions", json={"topic": "t"}).json()["session_id"]
        r = client.post(f"/api/sessions/{sid}/resume")
        assert r.status_code == 409


class TestSessionRedirect:
    def test_redirect_running_202(self, client):
        """Fix I: redirect only works when RUNNING."""
        sid = client.post("/api/sessions", json={"topic": "t"}).json()["session_id"]
        client.post(f"/api/sessions/{sid}/start")
        r = client.post(
            f"/api/sessions/{sid}/redirect",
            json={"target_stage": "plan_formulation", "reason": "test"},
        )
        assert r.status_code == 202
        data = r.json()
        assert data["target_stage"] == "plan_formulation"

    def test_redirect_not_running_409(self, client):
        """Fix I: reject redirect when session isn't RUNNING."""
        sid = client.post("/api/sessions", json={"topic": "t"}).json()["session_id"]
        # Session is CREATED, not RUNNING
        r = client.post(
            f"/api/sessions/{sid}/redirect",
            json={"target_stage": "plan_formulation"},
        )
        assert r.status_code == 409
        assert "RUNNING" in r.json()["detail"]

    def test_redirect_missing_404(self, client):
        r = client.post(
            "/api/sessions/sess-nonexistent/redirect",
            json={"target_stage": "plan_formulation"},
        )
        assert r.status_code == 404
