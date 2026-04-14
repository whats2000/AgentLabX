"""HITL pause: needs_approval clears paused_event; /checkpoint/approve resumes."""
from __future__ import annotations

import os
import pytest
from fastapi.testclient import TestClient

from agentlabx.server.app import create_app


@pytest.fixture
def client(tmp_path):
    os.environ["AGENTLABX_STORAGE__DATABASE_URL"] = (
        f"sqlite+aiosqlite:///{tmp_path / 'ckpt.db'}"
    )
    os.environ["AGENTLABX_STORAGE__ARTIFACTS_PATH"] = str(tmp_path / "artifacts")
    app = create_app(use_mock_llm=True)
    with TestClient(app) as c:
        yield c
    os.environ.pop("AGENTLABX_STORAGE__DATABASE_URL", None)
    os.environ.pop("AGENTLABX_STORAGE__ARTIFACTS_PATH", None)


def test_checkpoint_approve_returns_404_for_unknown_session(client):
    r = client.post(
        "/api/sessions/nonexistent/checkpoint/approve",
        json={"action": "approve"},
    )
    assert r.status_code == 404


def test_checkpoint_approve_endpoint_accepts_approve_action(client):
    r = client.post("/api/sessions", json={"topic": "t", "user_id": "default"})
    assert r.status_code == 201
    sid = r.json()["session_id"]

    # Start session so a RunningSession exists with paused_event
    r1 = client.post(f"/api/sessions/{sid}/start")
    # Starting returns 202; session is initially running (event set).
    # Pause so we have a paused session to approve-resume.
    r2 = client.post(f"/api/sessions/{sid}/pause")

    r3 = client.post(
        f"/api/sessions/{sid}/checkpoint/approve",
        json={"action": "approve"},
    )
    assert r3.status_code == 200, r3.text
    # Session should be resumed — the endpoint's response indicates success.
    body = r3.json()
    assert body["status"] == "resumed"
    assert body["action"] == "approve"


def test_checkpoint_approve_rejects_unsupported_action(client):
    """redirect/edit actions are 501 in Plan 7E A2 — deferred."""
    r = client.post("/api/sessions", json={"topic": "t", "user_id": "default"})
    sid = r.json()["session_id"]
    client.post(f"/api/sessions/{sid}/start")

    r2 = client.post(
        f"/api/sessions/{sid}/checkpoint/approve",
        json={"action": "redirect", "redirect_target": "plan_formulation"},
    )
    assert r2.status_code == 501
    assert "deferred" in r2.json().get("detail", "").lower()


def test_checkpoint_approve_reject_action_resumes_with_same_target(client):
    """Reject = resume without modifying routing (handler's decision stands)."""
    r = client.post("/api/sessions", json={"topic": "t", "user_id": "default"})
    sid = r.json()["session_id"]
    client.post(f"/api/sessions/{sid}/start")
    client.post(f"/api/sessions/{sid}/pause")

    r2 = client.post(
        f"/api/sessions/{sid}/checkpoint/approve",
        json={"action": "reject", "reason": "not yet"},
    )
    assert r2.status_code == 200
    assert r2.json()["action"] == "reject"


def test_checkpoint_approve_returns_409_when_session_not_started(client):
    """Approving a checkpoint for a session that was never started returns 409.

    Previously the endpoint would silently return 200 when context.executor had
    no RunningSession for the given session_id (the `if context.executor is not None:`
    guard fell through to the final `return {"status": "resumed"}` line).
    """
    r = client.post("/api/sessions", json={"topic": "t", "user_id": "default"})
    assert r.status_code == 201
    sid = r.json()["session_id"]
    # Deliberately do NOT start the session — no RunningSession will exist.

    r2 = client.post(
        f"/api/sessions/{sid}/checkpoint/approve",
        json={"action": "approve"},
    )
    # Session exists but has no active executor run → 409 (not a silent 200).
    assert r2.status_code in (404, 409), (
        f"Expected 404 or 409 for un-started session, got {r2.status_code}: {r2.text}"
    )
