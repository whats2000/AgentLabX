"""GET /api/sessions/{id}/stage_plans/{stage} returns StagePlan history."""
from __future__ import annotations

import os
import pytest
from fastapi.testclient import TestClient

from agentlabx.server.app import create_app


@pytest.fixture
def client(tmp_path):
    os.environ["AGENTLABX_STORAGE__DATABASE_URL"] = (
        f"sqlite+aiosqlite:///{tmp_path / 'sp.db'}"
    )
    os.environ["AGENTLABX_STORAGE__ARTIFACTS_PATH"] = str(tmp_path / "artifacts")
    app = create_app(use_mock_llm=True)
    with TestClient(app) as c:
        yield c
    os.environ.pop("AGENTLABX_STORAGE__DATABASE_URL", None)
    os.environ.pop("AGENTLABX_STORAGE__ARTIFACTS_PATH", None)


def test_stage_plans_endpoint_empty_for_unstarted_session(client):
    r = client.post("/api/sessions", json={"topic": "t", "user_id": "default"})
    assert r.status_code == 201
    sid = r.json()["session_id"]

    r2 = client.get(f"/api/sessions/{sid}/stage_plans/literature_review")
    assert r2.status_code == 200
    assert r2.json() == {"stage_name": "literature_review", "plans": []}


def test_stage_plans_endpoint_404_on_unknown_session(client):
    r = client.get("/api/sessions/nonexistent/stage_plans/literature_review")
    assert r.status_code == 404
