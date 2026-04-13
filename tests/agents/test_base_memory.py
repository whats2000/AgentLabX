# tests/agents/test_base_memory.py
from agentlabx.agents.base import MemoryScope
from agentlabx.agents.config_agent import ConfigAgent
from agentlabx.agents.config_loader import AgentConfig


def test_base_agent_has_dirty_flag_and_helpers():
    cfg = AgentConfig(
        name="tester", role="tester", system_prompt="sp",
        memory_scope=MemoryScope(read=[], summarize={}, write=[]),
        tools=[], phases=[],
    )
    a = ConfigAgent.from_config(cfg)
    assert a.dirty is False
    assert a.notes == []
    assert a.turn_count == 0
    assert a.last_active_stage == ""

    a.add_note("hello")
    assert a.dirty is True
    assert a.notes == ["hello"]

    a.dirty = False
    a.working_memory["foo"] = "bar"   # direct mutation doesn't set dirty
    a.mark_dirty()
    assert a.dirty is True


def test_snapshot_memory_returns_agent_memory_record_shape():
    cfg = AgentConfig(
        name="tester", role="tester", system_prompt="sp",
        memory_scope=MemoryScope(read=[], summarize={}, write=[]),
        tools=[], phases=[],
    )
    a = ConfigAgent.from_config(cfg)
    a.working_memory["key"] = "val"
    a.notes.append("note")
    a.last_active_stage = "plan_formulation"
    a.turn_count = 3

    snap = a.snapshot_memory()
    assert snap == {
        "working_memory": {"key": "val"},
        "notes": ["note"],
        "last_active_stage": "plan_formulation",
        "turn_count": 3,
    }


def test_load_memory_restores_and_clears_dirty():
    cfg = AgentConfig(
        name="tester", role="tester", system_prompt="sp",
        memory_scope=MemoryScope(read=[], summarize={}, write=[]),
        tools=[], phases=[],
    )
    a = ConfigAgent.from_config(cfg)
    a.dirty = True  # force dirty to confirm it gets cleared
    a.load_memory({
        "working_memory": {"focus": "MATH"},
        "notes": ["found 3 papers"],
        "last_active_stage": "literature_review",
        "turn_count": 7,
    })
    assert a.working_memory == {"focus": "MATH"}
    assert a.notes == ["found 3 papers"]
    assert a.last_active_stage == "literature_review"
    assert a.turn_count == 7
    assert a.dirty is False
