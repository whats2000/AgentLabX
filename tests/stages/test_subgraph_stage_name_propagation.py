"""B4 regression: stage_internal_node_changed events carry the correct stage name
(not empty, not the previous stage's name)."""
from __future__ import annotations

import pytest

from agentlabx.stages.literature_review import LiteratureReviewStage
from agentlabx.stages.subgraph import StageSubgraphBuilder


@pytest.mark.asyncio
async def test_internal_node_events_include_current_stage_name():
    stage = LiteratureReviewStage()
    compiled = StageSubgraphBuilder().compile(stage)

    events_seen: list[dict] = []

    class StubBus:
        async def emit(self, event):
            # Mirror the shape used by events.Event
            events_seen.append({
                "type": getattr(event, "type", ""),
                "data": getattr(event, "data", {}),
                "source": getattr(event, "source", ""),
            })

    from agentlabx.stages.base import StageContext
    ctx = StageContext(event_bus=StubBus())

    # Minimal starting state — no current_stage set (simulates first stage entering)
    state = {
        "research_topic": "x",
        "current_stage": "",  # empty on first entry
        "goals": [],
        "artifacts": {},
        "stage_plans": {},
        "session_id": "test-session",
    }

    # Invoke the compiled subgraph — it may run minimally if agents are mock, or may
    # try to execute real stage logic. For this test, tolerate graph execution errors
    # but assert the stage field on events that WERE emitted.
    try:
        await compiled.ainvoke({"state": state, "context": ctx})
    except Exception:
        # Real stage execution may fail without an LLM provider. That's OK —
        # we only care about the events emitted up to the failure point.
        pass

    internal = [e for e in events_seen if e.get("type", "") == "stage_internal_node_changed"]
    assert internal, "expected at least one stage_internal_node_changed event"

    # The stage name in each event must be the CURRENT stage (literature_review),
    # not the empty string from the incoming state.
    for e in internal:
        actual_stage = e["data"].get("stage", "")
        assert actual_stage == "literature_review", (
            f"B4 regression: event has stale/empty stage field: {e}"
        )


from tests.harness.contracts.base import HarnessTrace
from tests.harness.contracts.stage_nodes import (
    enter_emits_event,
    stage_plan_persisted,
    work_emits_agent_turn,
    work_prompt_includes_plan_items,
    evaluate_respects_iteration_bound,
    decide_pause_contract,
)


def test_enter_contract_passes_when_event_has_correct_stage():
    trace = HarnessTrace(test_id="t")
    trace.record_event({
        "type": "stage_internal_node_changed",
        "data": {"internal_node": "enter", "stage": "literature_review"},
    })
    c = enter_emits_event(stage_name="literature_review")
    assert c.run(trace).passed


def test_enter_contract_fails_on_empty_stage():
    trace = HarnessTrace(test_id="t")
    trace.record_event({
        "type": "stage_internal_node_changed",
        "data": {"internal_node": "enter", "stage": ""},
    })
    c = enter_emits_event(stage_name="literature_review")
    assert not c.run(trace).passed


def test_work_emits_agent_turn_passes():
    trace = HarnessTrace(test_id="t")
    trace.record_event({"type": "agent_turn_started", "data": {"stage": "literature_review"}})
    c = work_emits_agent_turn(stage_name="literature_review")
    assert c.run(trace).passed


def test_evaluate_bound_fails_on_unbounded_iterations():
    trace = HarnessTrace(test_id="t")
    # snapshot declares max_stage_iterations=2 but 3 evaluate events
    trace.snapshot("after_experimentation", {"max_stage_iterations": 2})
    for _ in range(3):
        trace.record_event({
            "type": "stage_internal_node_changed",
            "data": {"internal_node": "evaluate", "stage": "experimentation"},
        })
    c = evaluate_respects_iteration_bound(stage_name="experimentation")
    result = c.run(trace)
    assert not result.passed
    assert result.severity.value == "P0"


def test_decide_pause_contract_ok_when_no_approval_needed():
    trace = HarnessTrace(test_id="t")
    trace.snapshot("after_lit", {"needs_approval": False})
    c = decide_pause_contract(stage_name="lit")
    assert c.run(trace).passed
