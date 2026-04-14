"""GET /api/sessions/{id}/stages/{stage}/history returns turns for that stage."""
from __future__ import annotations

import os
import pytest
from fastapi.testclient import TestClient

from agentlabx.server.app import create_app


@pytest.fixture
def client(tmp_path):
    os.environ["AGENTLABX_STORAGE__DATABASE_URL"] = (
        f"sqlite+aiosqlite:///{tmp_path / 'sh.db'}"
    )
    os.environ["AGENTLABX_STORAGE__ARTIFACTS_PATH"] = str(tmp_path / "artifacts")
    app = create_app(use_mock_llm=True)
    with TestClient(app) as c:
        yield c
    os.environ.pop("AGENTLABX_STORAGE__DATABASE_URL", None)
    os.environ.pop("AGENTLABX_STORAGE__ARTIFACTS_PATH", None)


def test_stage_history_empty_list_for_unstarted_session(client):
    r = client.post("/api/sessions", json={"topic": "t", "user_id": "default"})
    assert r.status_code == 201
    sid = r.json()["session_id"]

    r2 = client.get(f"/api/sessions/{sid}/stages/literature_review/history")
    assert r2.status_code == 200
    body = r2.json()
    assert body["turns"] == []
    assert "next_cursor" in body


def test_stage_history_404_on_unknown_session(client):
    r = client.get("/api/sessions/nonexistent/stages/literature_review/history")
    assert r.status_code == 404


def test_stage_history_unknown_stage_returns_404(client):
    r = client.post("/api/sessions", json={"topic": "t", "user_id": "default"})
    assert r.status_code == 201
    sid = r.json()["session_id"]

    r2 = client.get(f"/api/sessions/{sid}/stages/not_a_stage/history")
    assert r2.status_code == 404
    assert "not_a_stage" in r2.json().get("detail", "")
