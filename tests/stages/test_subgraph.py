"""StageSubgraphBuilder compiles enter → stage_plan → gate → work → evaluate → decide."""
from __future__ import annotations

import pytest

from agentlabx.core.state import StagePlan, StagePlanItem, create_initial_state
from agentlabx.stages.base import BaseStage, StageContext, StageResult
from agentlabx.stages.subgraph import StageSubgraphBuilder


class _EchoStage(BaseStage):
    name = "echo"
    description = "echo"
    required_agents: list[str] = []
    required_tools: list[str] = []
    zone = "discovery"

    async def run(self, state, context):
        return StageResult(
            output={"literature_review": [{"papers": [], "summary": "echo"}]},
            status="done",
            reason="ok",
        )


@pytest.mark.asyncio
async def test_compiled_subgraph_has_expected_nodes():
    stage = _EchoStage()
    compiled = StageSubgraphBuilder().compile(stage)
    node_ids = set(compiled.get_graph().nodes)
    # "gate" is a routing function (add_conditional_edges), not a node;
    # LangGraph does not surface it in get_graph().nodes.
    assert {"enter", "stage_plan", "work", "evaluate", "decide"}.issubset(node_ids)


@pytest.mark.asyncio
async def test_compiled_subgraph_runs_default_path_and_writes_stage_plan():
    stage = _EchoStage()
    compiled = StageSubgraphBuilder().compile(stage)
    state = create_initial_state(
        session_id="s1", user_id="u1", research_topic="t"
    )
    state["current_stage"] = "echo"
    result = await compiled.ainvoke(
        {
            "state": state,
            "context": StageContext(settings={}, event_bus=None, registry=None),
        },
        config={"configurable": {"thread_id": "t1"}},
    )
    # Subgraph must record a StagePlan for this entry
    assert "echo" in result["state"]["stage_plans"]
    assert len(result["state"]["stage_plans"]["echo"]) == 1
    # and produce a final StageResult with status=done
    assert result["stage_result"].status == "done"
    assert result["stage_result"].output == {
        "literature_review": [{"papers": [], "summary": "echo"}]
    }


@pytest.mark.asyncio
async def test_subgraph_bypass_when_plan_is_empty_of_actionable_items():
    class _BypassStage(_EchoStage):
        name = "bypass"

        def build_plan(self, state, *, feedback=None):
            # Plan with only 'done' items — gate routes directly to decide
            return StagePlan(
                items=[
                    StagePlanItem(
                        id="already",
                        description="already done",
                        status="done",
                        source="prior",
                        existing_artifact_ref=None,
                        edit_note=None,
                        removed_reason=None,
                    )
                ],
                rationale="bypass: outputs already valid",
                hash_of_consumed_inputs="",
            )

    stage = _BypassStage()
    compiled = StageSubgraphBuilder().compile(stage)
    state = create_initial_state(
        session_id="s1", user_id="u1", research_topic="t"
    )
    state["current_stage"] = "bypass"
    result = await compiled.ainvoke(
        {
            "state": state,
            "context": StageContext(settings={}, event_bus=None, registry=None),
        },
        config={"configurable": {"thread_id": "t1"}},
    )
    assert result["stage_result"].status == "done"
    assert result["stage_result"].reason.startswith("plan-empty:")


@pytest.mark.asyncio
async def test_subgraph_records_multiple_entries_as_versioned_list():
    """stage_plans[name] accumulates across re-entries."""
    stage = _EchoStage()
    compiled = StageSubgraphBuilder().compile(stage)
    state = create_initial_state(
        session_id="s1", user_id="u1", research_topic="t"
    )
    state["current_stage"] = "echo"

    # First invocation
    result1 = await compiled.ainvoke(
        {"state": state, "context": StageContext(settings={}, event_bus=None, registry=None)},
        config={"configurable": {"thread_id": "t1"}},
    )
    state_after_1 = result1["state"]
    assert len(state_after_1["stage_plans"]["echo"]) == 1

    # Second invocation on the mutated state
    result2 = await compiled.ainvoke(
        {"state": state_after_1, "context": StageContext(settings={}, event_bus=None, registry=None)},
        config={"configurable": {"thread_id": "t2"}},
    )
    assert len(result2["state"]["stage_plans"]["echo"]) == 2
