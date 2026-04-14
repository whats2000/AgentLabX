"""B2 regression: StageContext.model is plumbed from settings into agents,
and resolve_agent no longer injects a hardcoded 'claude-sonnet-4-6' default."""
from __future__ import annotations

import pytest

from agentlabx.agents.config_agent import ConfigAgent
from agentlabx.agents.config_loader import AgentConfig
from agentlabx.agents.base import MemoryScope
from agentlabx.core.registry import PluginRegistry, PluginType
from agentlabx.stages._helpers import resolve_agent, resolve_agents_for_stage
from agentlabx.stages.base import StageContext


def _make_registry_with_agent():
    reg = PluginRegistry()
    config = AgentConfig(
        name="test_agent",
        role="test",
        system_prompt="you are a test",
        memory_scope=MemoryScope(),
    )
    reg.register(PluginType.AGENT, "test_agent", config)
    return reg


def test_resolve_agent_uses_passed_model_not_hardcoded():
    reg = _make_registry_with_agent()
    agent = resolve_agent(reg, "test_agent", model="gemini/gemini-2.5-flash")
    assert isinstance(agent, ConfigAgent)
    assert agent.model == "gemini/gemini-2.5-flash"


def test_resolve_agent_no_default_model_when_none_passed():
    """When model is None, resolve_agent must NOT inject a hardcoded fallback."""
    reg = _make_registry_with_agent()
    agent = resolve_agent(reg, "test_agent", model=None)
    assert isinstance(agent, ConfigAgent)
    assert agent.model is None or agent.model == ""


def test_stage_context_has_model_field():
    ctx = StageContext(model="gemini/gemini-2.5-flash")
    assert ctx.model == "gemini/gemini-2.5-flash"


def test_resolve_agents_for_stage_passes_context_model():
    reg = _make_registry_with_agent()
    ctx = StageContext(registry=reg, model="gemini/gemini-2.5-flash")
    agents = resolve_agents_for_stage(ctx, ["test_agent"])
    assert agents["test_agent"].model == "gemini/gemini-2.5-flash"


# ── Contract unit tests ──────────────────────────────────────────────────────

from tests.harness.contracts.base import HarnessTrace
from tests.harness.contracts.resolve_agent import model_plumbed_contract


def test_model_plumbed_contract_passes_on_correct_model():
    trace = HarnessTrace(test_id="t")
    trace.record_event({"type": "agent_llm_request", "data": {"model": "gemini/gemini-2.5-flash"}})
    c = model_plumbed_contract(expected_prefix="gemini/")
    assert c.run(trace).passed


def test_model_plumbed_contract_fails_on_wrong_model():
    trace = HarnessTrace(test_id="t")
    trace.record_event({"type": "agent_llm_request", "data": {"model": "claude-sonnet-4-6"}})
    c = model_plumbed_contract(expected_prefix="gemini/")
    assert not c.run(trace).passed


def test_model_plumbed_contract_passes_when_no_llm_calls():
    trace = HarnessTrace(test_id="t")
    c = model_plumbed_contract(expected_prefix="gemini/")
    assert c.run(trace).passed
