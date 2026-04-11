from __future__ import annotations
import pytest
from agentlabx.agents.base import AgentContext, BaseAgent, MemoryScope


class TestMemoryScope:
    def test_create_scope(self):
        scope = MemoryScope(
            read=["plan.methodology", "experiment_code.*"],
            write=["experiment_code", "experiment_results"],
            summarize={"literature_review": "abstract", "plan": "goals_only"},
        )
        assert "plan.methodology" in scope.read
        assert "experiment_code" in scope.write
        assert scope.summarize["literature_review"] == "abstract"

    def test_default_empty_scope(self):
        scope = MemoryScope()
        assert scope.read == []
        assert scope.write == []
        assert scope.summarize == {}

    def test_can_read(self):
        scope = MemoryScope(read=["plan.*", "experiment_code.main"])
        assert scope.can_read("plan.methodology") is True
        assert scope.can_read("plan.goals") is True
        assert scope.can_read("experiment_code.main") is True
        assert scope.can_read("experiment_code.other") is False
        assert scope.can_read("report") is False

    def test_wildcard_read_all(self):
        scope = MemoryScope(read=["*"])
        assert scope.can_read("anything") is True

    def test_can_write(self):
        scope = MemoryScope(write=["experiment_code"])
        assert scope.can_write("experiment_code") is True
        assert scope.can_write("report") is False


class DummyAgent(BaseAgent):
    async def inference(self, prompt: str, context: AgentContext) -> str:
        return f"Response to: {prompt}"


class IncompleteAgent(BaseAgent):
    pass


class TestBaseAgent:
    def test_concrete_agent_instantiates(self):
        scope = MemoryScope(read=["plan.*"], write=["experiment_code"])
        agent = DummyAgent(name="test_agent", role="test role", system_prompt="You are a test agent.", tools=[], memory_scope=scope)
        assert agent.name == "test_agent"
        assert agent.role == "test role"

    def test_abstract_agent_cannot_instantiate(self):
        with pytest.raises(TypeError):
            IncompleteAgent(name="x", role="x", system_prompt="x", tools=[], memory_scope=MemoryScope())

    async def test_inference_returns_string(self):
        agent = DummyAgent(name="test", role="test", system_prompt="test", tools=[], memory_scope=MemoryScope())
        ctx = AgentContext(phase="experimentation", state={}, working_memory={})
        result = await agent.inference("hello", ctx)
        assert result == "Response to: hello"

    def test_get_context_default(self):
        agent = DummyAgent(name="test", role="test", system_prompt="You are a test.", tools=[], memory_scope=MemoryScope())
        ctx_str = agent.get_context("experimentation")
        assert "You are a test." in ctx_str

    def test_reset_clears_history(self):
        agent = DummyAgent(name="test", role="test", system_prompt="test", tools=[], memory_scope=MemoryScope())
        agent.conversation_history.append({"role": "user", "content": "hello"})
        assert len(agent.conversation_history) == 1
        agent.reset()
        assert len(agent.conversation_history) == 0
