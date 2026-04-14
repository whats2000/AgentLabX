"""Unit test for harness session bootstrap. Uses mock llm_provider (not live) to
verify wiring; live tests live under tests/harness/ behind the marker."""
from __future__ import annotations

import pytest

from tests.harness.harness.session import HarnessSession


@pytest.mark.asyncio
async def test_session_boots_and_exposes_state():
    async with HarnessSession.boot_mock(topic="diffusion priors") as session:
        assert session.session_id is not None
        assert session.executor is not None
        assert session.state["research_topic"] == "diffusion priors"


@pytest.mark.asyncio
async def test_session_collects_events():
    async with HarnessSession.boot_mock(topic="x") as session:
        await session.emit_synthetic_event({"type": "probe", "value": 1})
        assert any(e.get("type") == "probe" for e in session.events)


@pytest.mark.asyncio
async def test_session_get_state_returns_dict():
    async with HarnessSession.boot_mock(topic="async-state") as session:
        import asyncio

        await asyncio.sleep(0.1)  # let the pipeline tick
        state = await session.get_state()
        assert isinstance(state, dict)
        # research_topic is always present (from session-level fallback)
        assert state.get("research_topic") in ("async-state", "")
