"""BaseStage subgraph hooks — default implementations preserve .run() semantics."""
from __future__ import annotations

import pytest

from agentlabx.core.state import create_initial_state
from agentlabx.stages.base import (
    BaseStage,
    StageContext,
    StageEvaluation,
    StageExecution,
    StageResult,
)


class _LegacyStage(BaseStage):
    """Pre-7B stage: implements only .run(), relies on default hooks."""

    name = "legacy"
    description = "legacy stage using only .run()"
    required_agents: list[str] = []
    required_tools: list[str] = []
    zone = "discovery"

    async def run(self, state, context):
        return StageResult(
            output={"literature_review": [{"papers": [], "summary": "legacy ran"}]},
            status="done",
            reason="legacy",
        )


def _state():
    return create_initial_state(
        session_id="s1", user_id="u1", research_topic="t"
    )


def test_default_build_plan_returns_single_todo_item():
    stage = _LegacyStage()
    plan = stage.build_plan(_state(), feedback=None)
    assert len(plan["items"]) == 1
    assert plan["items"][0]["status"] == "todo"
    assert "run" in plan["items"][0]["description"].lower()


@pytest.mark.asyncio
async def test_default_execute_plan_delegates_to_run():
    stage = _LegacyStage()
    state = _state()
    plan = stage.build_plan(state, feedback=None)
    execution = await stage.execute_plan(
        state, plan, StageContext(settings={}, event_bus=None, registry=None)
    )
    assert execution.output == {
        "literature_review": [{"papers": [], "summary": "legacy ran"}]
    }
    assert execution.status == "done"


def test_default_evaluate_returns_empty_evaluation():
    stage = _LegacyStage()
    execution = StageExecution(
        output={}, status="done", reason="ok"
    )
    evaluation = stage.evaluate(
        _state(), plan={"items": [], "rationale": "x", "hash_of_consumed_inputs": ""},
        execution=execution,
    )
    assert evaluation.dead_end is False
    assert evaluation.override_status is None


def test_default_decide_builds_stage_result_from_execution():
    stage = _LegacyStage()
    execution = StageExecution(
        output={"plan": [{"full_text": "x"}]},
        status="done",
        reason="ok",
    )
    evaluation = StageEvaluation()
    result = stage.decide(
        _state(),
        plan={"items": [], "rationale": "x", "hash_of_consumed_inputs": ""},
        execution=execution,
        evaluation=evaluation,
    )
    assert result.output == {"plan": [{"full_text": "x"}]}
    assert result.status == "done"


def test_evaluation_override_status_wins_in_decide():
    stage = _LegacyStage()
    execution = StageExecution(
        output={"plan": [{"full_text": "x"}]},
        status="done",
        reason="stage says done",
    )
    evaluation = StageEvaluation(
        dead_end=True,
        override_status="backtrack",
        override_next_hint="literature_review",
        override_reason="evaluate detected missing prereq",
    )
    result = stage.decide(
        _state(),
        plan={"items": [], "rationale": "x", "hash_of_consumed_inputs": ""},
        execution=execution,
        evaluation=evaluation,
    )
    assert result.status == "backtrack"
    assert result.next_hint == "literature_review"
    assert result.reason == "evaluate detected missing prereq"
