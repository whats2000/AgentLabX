"""Tests for PATCH /api/sessions/{id}/preferences."""

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


class TestPreferencesUpdate:
    def test_update_mode(self, client):
        sid = client.post("/api/sessions", json={"topic": "t"}).json()["session_id"]
        r = client.patch(
            f"/api/sessions/{sid}/preferences",
            json={"mode": "hitl"},
        )
        assert r.status_code == 200
        assert r.json()["preferences"]["mode"] == "hitl"

    def test_update_stage_controls(self, client):
        sid = client.post("/api/sessions", json={"topic": "t"}).json()["session_id"]
        r = client.patch(
            f"/api/sessions/{sid}/preferences",
            json={"stage_controls": {"experimentation": "approve"}},
        )
        assert r.status_code == 200
        prefs = r.json()["preferences"]
        assert prefs["stage_controls"]["experimentation"] == "approve"

    def test_update_multiple_fields(self, client):
        sid = client.post("/api/sessions", json={"topic": "t"}).json()["session_id"]
        r = client.patch(
            f"/api/sessions/{sid}/preferences",
            json={
                "mode": "hitl",
                "stage_controls": {"report_writing": "edit"},
                "backtrack_control": "approve",
            },
        )
        assert r.status_code == 200
        prefs = r.json()["preferences"]
        assert prefs["mode"] == "hitl"
        assert prefs["stage_controls"]["report_writing"] == "edit"
        assert prefs["backtrack_control"] == "approve"

    def test_empty_patch_noop(self, client):
        sid = client.post("/api/sessions", json={"topic": "t"}).json()["session_id"]
        r = client.patch(f"/api/sessions/{sid}/preferences", json={})
        assert r.status_code == 200
        assert r.json()["preferences"]["mode"] == "auto"  # default

    def test_patch_missing_404(self, client):
        r = client.patch(
            "/api/sessions/sess-nonexistent/preferences",
            json={"mode": "hitl"},
        )
        assert r.status_code == 404

    def test_patches_accumulate(self, client):
        sid = client.post("/api/sessions", json={"topic": "t"}).json()["session_id"]
        client.patch(f"/api/sessions/{sid}/preferences", json={"mode": "hitl"})
        client.patch(
            f"/api/sessions/{sid}/preferences",
            json={"stage_controls": {"experimentation": "approve"}},
        )
        r = client.get(f"/api/sessions/{sid}")
        prefs = r.json()["preferences"]
        assert prefs["mode"] == "hitl"
        assert prefs["stage_controls"]["experimentation"] == "approve"
