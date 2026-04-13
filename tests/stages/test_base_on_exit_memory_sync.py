"""Tests for sync_agent_memory_to_state helper."""

from agentlabx.stages.base import sync_agent_memory_to_state
from agentlabx.stages._helpers import resolve_agent
from agentlabx.agents.base import BaseAgent, MemoryScope, AgentContext


def test_sync_dirty_agent_writes_to_state(sample_registry):
    state = {"agent_memory": {}}
    agent = resolve_agent(sample_registry, "phd_student", state=state)
    agent.add_note("key insight")
    agent.last_active_stage = "plan_formulation"

    sync_agent_memory_to_state(state, {"phd_student": agent})
    assert state["agent_memory"]["phd_student"]["notes"] == ["key insight"]
    assert state["agent_memory"]["phd_student"]["last_active_stage"] == "plan_formulation"
    assert agent.dirty is False  # cleared after sync


def test_sync_skips_clean_agents(sample_registry):
    # Pre-populate state; resolve; don't mutate; sync should be no-op
    state = {
        "agent_memory": {
            "phd_student": {
                "notes": ["existing"],
                "working_memory": {},
                "last_active_stage": "",
                "turn_count": 0,
            }
        }
    }
    agent = resolve_agent(sample_registry, "phd_student", state=state)
    # No mutations — agent stays clean
    sync_agent_memory_to_state(state, {"phd_student": agent})
    assert state["agent_memory"]["phd_student"]["notes"] == ["existing"]  # untouched


def test_sync_initializes_agent_memory_key_if_absent():
    """If state doesn't have agent_memory key yet, helper adds it."""

    class _A(BaseAgent):
        async def inference(self, prompt, context):
            return ""

    a = _A(
        name="a",
        role="",
        system_prompt="",
        tools=[],
        memory_scope=MemoryScope(read=[], summarize={}, write=[]),
    )
    a.add_note("x")
    state = {}
    sync_agent_memory_to_state(state, {"a": a})
    assert "agent_memory" in state
    assert state["agent_memory"]["a"]["notes"] == ["x"]
