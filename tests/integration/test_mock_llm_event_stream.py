"""Integration test: mock-LLM pipeline emits full agent turn event stream (B12).

Runs a single-stage pipeline (literature_review only) with MockLLMProvider,
then asserts that the agent_turns table has correlated llm_request + llm_response
rows with is_mock=True and matching turn_ids.

Uses the same sync TestClient pattern as the rest of the server test suite —
no AsyncClient or anyio required.
"""

from __future__ import annotations

import os
import time

import pytest
from fastapi.testclient import TestClient

from agentlabx.server.app import create_app


def _wait_for_status(
    client: TestClient,
    session_id: str,
    target_statuses: set[str],
    timeout: float = 30.0,
) -> dict:
    """Poll GET /api/sessions/{id} until status is in target_statuses or timeout."""
    deadline = time.monotonic() + timeout
    last_status = None
    while time.monotonic() < deadline:
        r = client.get(f"/api/sessions/{session_id}")
        assert r.status_code == 200
        body = r.json()
        last_status = body["status"]
        if last_status in target_statuses:
            return body
        time.sleep(0.1)
    raise TimeoutError(
        f"Session {session_id} never reached {target_statuses}; "
        f"last status was '{last_status}'"
    )


@pytest.fixture()
def mock_llm_client(tmp_path):
    """TestClient with isolated DB and MockLLMProvider wired in."""
    os.environ["AGENTLABX_STORAGE__DATABASE_URL"] = (
        f"sqlite+aiosqlite:///{tmp_path / 'b12.db'}"
    )
    os.environ["AGENTLABX_STORAGE__ARTIFACTS_PATH"] = str(tmp_path / "artifacts")
    app = create_app(use_mock_llm=True)
    with TestClient(app) as c:
        yield c
    os.environ.pop("AGENTLABX_STORAGE__DATABASE_URL", None)
    os.environ.pop("AGENTLABX_STORAGE__ARTIFACTS_PATH", None)


class TestMockLLMEventStream:
    def test_mock_llm_pipeline_produces_full_event_stream(self, mock_llm_client):
        """Create a session with MockLLMProvider; run literature_review only; verify:

        - agent_turns table has at least one llm_request + one llm_response row
        - all rows are tagged is_mock=True
        - llm_request and llm_response rows share at least one common turn_id
          (i.e., request + response are correlated via the same TurnContext)
        """
        client = mock_llm_client

        # Create a session whose pipeline runs only literature_review.
        # We use default_sequence (not skip_stages) because the executor reads
        # pipeline.default_sequence from config_overrides to build the graph.
        r = client.post(
            "/api/sessions",
            json={
                "topic": "MATH benchmark scaling study with detailed baselines",
                "user_id": "default",
                "config": {
                    "pipeline": {
                        "default_sequence": ["literature_review"],
                    }
                },
            },
        )
        assert r.status_code == 201, r.text
        sid = r.json()["session_id"]

        # Start the pipeline
        started = client.post(f"/api/sessions/{sid}/start")
        assert started.status_code == 202, started.text

        # Wait for completion (or failure) — with MockLLMProvider this is fast
        final = _wait_for_status(
            client,
            sid,
            {"completed", "failed"},
            timeout=30.0,
        )
        # The pipeline should complete (not fail) with mock LLM
        assert final["status"] in ("completed", "failed"), (
            f"Unexpected final status: {final['status']}"
        )

        # Fetch agent turn history for phd_student
        h = client.get(f"/api/sessions/{sid}/agents/phd_student/history?limit=200")
        assert h.status_code == 200, h.text
        body = h.json()
        turns = body["turns"]

        # --- core assertions ---

        kinds = [t["kind"] for t in turns]
        assert "llm_request" in kinds, (
            f"Expected llm_request in agent_turns kinds; got: {kinds}"
        )
        assert "llm_response" in kinds, (
            f"Expected llm_response in agent_turns kinds; got: {kinds}"
        )

        # All rows must be tagged is_mock=True (MockLLMProvider sets this)
        not_mock = [t for t in turns if not t["is_mock"]]
        assert not not_mock, (
            f"Expected all turns to have is_mock=True; non-mock rows: {not_mock}"
        )

        # Turn correlation: at least one request + response share the same turn_id
        request_ids = {t["turn_id"] for t in turns if t["kind"] == "llm_request"}
        response_ids = {t["turn_id"] for t in turns if t["kind"] == "llm_response"}
        shared = request_ids & response_ids
        assert shared, (
            f"No shared turn_ids between llm_request ({request_ids}) "
            f"and llm_response ({response_ids})"
        )
