"""Tests for append_agent_turn and list_agent_turns on SQLiteBackend (Task A4)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest_asyncio

from agentlabx.providers.storage.base import AgentTurnRecord
from agentlabx.providers.storage.sqlite_backend import SQLiteBackend


@pytest_asyncio.fixture
async def backend(tmp_path):
    b = SQLiteBackend(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'test.db'}",
        artifacts_path=tmp_path / "art",
    )
    await b.initialize()
    yield b
    await b.close()


async def test_append_and_list_turn(backend):
    rec = AgentTurnRecord(
        session_id="s1", turn_id="t1", agent="phd_student",
        stage="literature_review", kind="llm_request",
        payload={"model": "gpt-4o", "prompt": "hi"},
    )
    row_id = await backend.append_agent_turn(rec)
    assert row_id > 0

    rows = await backend.list_agent_turns("s1")
    assert len(rows) == 1
    assert rows[0].turn_id == "t1"
    assert rows[0].payload["model"] == "gpt-4o"


async def test_list_filters_by_agent(backend):
    await backend.append_agent_turn(AgentTurnRecord(
        session_id="s1", turn_id="t1", agent="a1", stage="x", kind="llm_request", payload={}))
    await backend.append_agent_turn(AgentTurnRecord(
        session_id="s1", turn_id="t2", agent="a2", stage="x", kind="llm_request", payload={}))

    only_a1 = await backend.list_agent_turns("s1", agent="a1")
    assert len(only_a1) == 1 and only_a1[0].agent == "a1"


async def test_list_filters_by_stage_and_after_ts(backend):
    t0 = datetime.now(UTC)
    await backend.append_agent_turn(AgentTurnRecord(
        session_id="s1", turn_id="t1", agent="a1", stage="s1stage",
        kind="llm_request", payload={}, ts=t0))
    await backend.append_agent_turn(AgentTurnRecord(
        session_id="s1", turn_id="t2", agent="a1", stage="s2stage",
        kind="llm_request", payload={}, ts=t0 + timedelta(seconds=1)))

    rows = await backend.list_agent_turns("s1", stage="s1stage")
    assert len(rows) == 1

    rows = await backend.list_agent_turns("s1", after_ts=t0)
    assert len(rows) == 1 and rows[0].turn_id == "t2"
