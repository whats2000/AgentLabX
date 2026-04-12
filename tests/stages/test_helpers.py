"""Tests for stage helper utilities."""

from __future__ import annotations

import pytest

from agentlabx.agents.base import AgentContext, BaseAgent, MemoryScope
from agentlabx.agents.config_agent import ConfigAgent
from agentlabx.agents.config_loader import AgentConfig
from agentlabx.core.registry import PluginRegistry, PluginType
from agentlabx.core.state import create_initial_state
from agentlabx.stages._helpers import (
    build_agent_context,
    resolve_agent,
    resolve_agents_for_stage,
    resolve_tool,
)
from agentlabx.stages.base import StageContext
from agentlabx.tools.base import BaseTool, ToolResult


class DummyAgent(BaseAgent):
    async def inference(self, prompt: str, context: AgentContext) -> str:
        return "dummy"


class DummyTool(BaseTool):
    name = "dummy_tool"
    description = "A test tool"
    config_schema = type("Cfg", (), {})

    async def execute(self, **kwargs) -> ToolResult:
        return ToolResult(success=True, data={})


@pytest.fixture()
def registry() -> PluginRegistry:
    reg = PluginRegistry()
    reg.register(
        PluginType.AGENT,
        "phd_student",
        AgentConfig(
            name="phd_student",
            role="Core researcher",
            system_prompt="You are a PhD student.",
            memory_scope=MemoryScope(read=["literature_review.*"]),
        ),
    )
    reg.register(PluginType.TOOL, "dummy_tool", DummyTool)
    return reg


class TestResolveAgent:
    def test_resolve_config_agent(self, registry: PluginRegistry):
        agent = resolve_agent(registry, "phd_student")
        assert isinstance(agent, ConfigAgent)
        assert agent.name == "phd_student"

    def test_resolve_with_llm_provider(self, registry: PluginRegistry):
        fake_provider = object()
        agent = resolve_agent(registry, "phd_student", llm_provider=fake_provider)
        assert isinstance(agent, ConfigAgent)
        assert agent.llm_provider is fake_provider

    def test_resolve_class_based_agent(self):
        reg = PluginRegistry()

        class _FakeAgent(BaseAgent):
            def __init__(self):
                super().__init__(
                    name="fake",
                    role="fake",
                    system_prompt="fake",
                    tools=[],
                    memory_scope=MemoryScope(),
                )

            async def inference(self, prompt, context):
                return "fake"

        reg.register(PluginType.AGENT, "fake", _FakeAgent)
        agent = resolve_agent(reg, "fake")
        assert isinstance(agent, _FakeAgent)

    def test_resolve_unknown_type_raises(self):
        reg = PluginRegistry()
        reg.register(PluginType.AGENT, "bad", "not a class or config")
        with pytest.raises(TypeError):
            resolve_agent(reg, "bad")


class TestResolveTool:
    def test_resolve_tool_class(self, registry: PluginRegistry):
        tool = resolve_tool(registry, "dummy_tool")
        assert isinstance(tool, DummyTool)

    def test_resolve_tool_instance(self):
        reg = PluginRegistry()
        instance = DummyTool()
        reg.register(PluginType.TOOL, "dummy_tool", instance)
        tool = resolve_tool(reg, "dummy_tool")
        assert tool is instance

    def test_resolve_tool_unknown_type_raises(self):
        reg = PluginRegistry()
        reg.register(PluginType.TOOL, "bad", 42)
        with pytest.raises(TypeError):
            resolve_tool(reg, "bad")


class TestBuildAgentContext:
    def test_context_filtered_by_scope(self, registry: PluginRegistry):
        agent = resolve_agent(registry, "phd_student")
        state = create_initial_state(session_id="s1", user_id="u1", research_topic="MATH benchmark")
        ctx = build_agent_context(state, agent, phase="literature_review")
        assert ctx.phase == "literature_review"
        assert "research_topic" in ctx.state


class TestResolveAgentsForStage:
    def test_resolves_multiple_agents(self, registry: PluginRegistry):
        fake_provider = object()
        context = StageContext(
            settings={},
            event_bus=None,
            registry=registry,
            llm_provider=fake_provider,
        )
        agents = resolve_agents_for_stage(context, ["phd_student"])
        assert "phd_student" in agents
        assert isinstance(agents["phd_student"], ConfigAgent)
        assert agents["phd_student"].llm_provider is fake_provider

    def test_raises_without_registry(self):
        context = StageContext(settings={}, event_bus=None, registry=None)
        with pytest.raises(ValueError, match="no registry"):
            resolve_agents_for_stage(context, ["phd_student"])
