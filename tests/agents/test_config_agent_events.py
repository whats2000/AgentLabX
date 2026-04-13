# tests/agents/test_config_agent_events.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from agentlabx.agents.config_agent import ConfigAgent
from agentlabx.agents.config_loader import AgentConfig
from agentlabx.agents.base import MemoryScope, AgentContext
from agentlabx.providers.llm.base import LLMResponse


@pytest.fixture
def cfg():
    return AgentConfig(
        name="phd_student", role="phd", system_prompt="sp",
        memory_scope=MemoryScope(read=["*"], summarize={}, write=[]),
        tools=[], phases=[],
    )


@pytest.mark.asyncio
async def test_inference_emits_turn_started_and_completed(cfg):
    bus = MagicMock(); bus.emit = AsyncMock()
    storage = MagicMock(); storage.append_agent_turn = AsyncMock()
    llm = MagicMock()
    llm.is_mock = False
    llm.query = AsyncMock(return_value=LLMResponse(content="ok", tokens_in=1, tokens_out=1, model="m", cost=0.0))

    a = ConfigAgent.from_config(cfg, llm_provider=llm, event_bus=bus, storage=storage)
    # AgentContext uses `phase` (not `stage`) and has no `session_id`
    actx = AgentContext(phase="literature_review", state={}, working_memory={})
    await a.inference("what?", actx)

    types = [c.args[0].type for c in bus.emit.await_args_list]
    assert types[0] == "agent_turn_started"
    assert types[-1] == "agent_turn_completed"
    assert a.turn_count == 1
    assert a.last_active_stage == "literature_review"
    assert a.dirty is True


@pytest.mark.asyncio
async def test_turn_started_payload_includes_metadata(cfg):
    bus = MagicMock(); bus.emit = AsyncMock()
    llm = MagicMock()
    llm.is_mock = False
    llm.query = AsyncMock(return_value=LLMResponse(content="x", tokens_in=0, tokens_out=0, model="m", cost=0.0))

    a = ConfigAgent.from_config(cfg, llm_provider=llm, event_bus=bus)
    actx = AgentContext(phase="plan_formulation", state={"plan": [{"x": 1}], "hypotheses": []}, working_memory={})
    await a.inference("go", actx)

    started_event = bus.emit.await_args_list[0].args[0]
    assert started_event.type == "agent_turn_started"
    data = started_event.data
    assert data["agent"] == "phd_student"
    assert data["stage"] == "plan_formulation"
    assert data["turn_id"]  # some uuid
    assert data["system_prompt_hash"]  # some hash digest
    assert "system_prompt_preview" in data
    assert "assembled_context_keys" in data
    assert "memory_scope_applied" in data
    assert data["is_mock"] is False


@pytest.mark.asyncio
async def test_is_mock_flag_propagates_from_mock_provider(cfg):
    bus = MagicMock(); bus.emit = AsyncMock()
    from agentlabx.providers.llm.mock_provider import MockLLMProvider
    llm = MockLLMProvider(responses=["answer"])
    a = ConfigAgent.from_config(cfg, llm_provider=llm, event_bus=bus)
    actx = AgentContext(phase="lit", state={}, working_memory={})
    await a.inference("go", actx)

    started_event = bus.emit.await_args_list[0].args[0]
    assert started_event.data["is_mock"] is True


@pytest.mark.asyncio
async def test_inference_without_event_bus_still_works(cfg):
    """Backward-compat: agents constructed without event_bus still run."""
    llm = MagicMock()
    llm.is_mock = False
    llm.query = AsyncMock(return_value=LLMResponse(content="ok", tokens_in=1, tokens_out=1, model="m", cost=0.0))

    a = ConfigAgent.from_config(cfg, llm_provider=llm)  # no event_bus
    actx = AgentContext(phase="lit", state={}, working_memory={})
    result = await a.inference("what?", actx)
    assert result == "ok"
    assert a.turn_count == 1  # bumps regardless of emit
    assert a.last_active_stage == "lit"
    assert a.dirty is True
