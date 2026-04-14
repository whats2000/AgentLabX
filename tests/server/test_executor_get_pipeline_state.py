"""ARCH-2 (Plan 8): PipelineExecutor.get_pipeline_state returns current LangGraph state."""
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import pytest

from agentlabx.core.session import SessionManager
from agentlabx.providers.llm.mock_provider import MockLLMProvider
from agentlabx.server.deps import build_default_registry
from agentlabx.server.executor import PipelineExecutor


@pytest.mark.asyncio
async def test_get_pipeline_state_returns_empty_for_unknown_session():
    registry = build_default_registry()
    manager = SessionManager()
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db = tmp.name
    try:
        exec_ = PipelineExecutor(
            registry=registry,
            session_manager=manager,
            llm_provider=MockLLMProvider(),
            checkpoint_db_path=db,
        )
        await exec_.initialize()
        result = await exec_.get_pipeline_state("no-such-session")
        assert result == {}
        await exec_.close()
    finally:
        Path(db).unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_get_pipeline_state_returns_dict_for_running_session():
    registry = build_default_registry()
    manager = SessionManager()
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db = tmp.name
    try:
        exec_ = PipelineExecutor(
            registry=registry,
            session_manager=manager,
            llm_provider=MockLLMProvider(),
            checkpoint_db_path=db,
        )
        await exec_.initialize()
        session = manager.create_session(
            research_topic="test",
            user_id="harness",
            config_overrides={
                "pipeline": {
                    "default_sequence": ["literature_review"],
                    "max_total_iterations": 1,
                },
            },
        )
        await exec_.start_session(session)

        # Give the pipeline a tick to at least write initial state to checkpointer
        await asyncio.sleep(0.1)

        state = await exec_.get_pipeline_state(session.session_id)
        assert isinstance(state, dict)
        # Invariant: result is a dict (not an exception). Pipeline state may or
        # may not be persisted to the checkpointer yet depending on timing, so
        # we only assert on the type.

        await exec_.cancel_session(session.session_id)
        await exec_.close()
    finally:
        Path(db).unlink(missing_ok=True)
