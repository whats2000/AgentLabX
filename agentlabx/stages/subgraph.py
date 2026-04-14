"""Compile per-stage LangGraph subgraphs: enter → stage_plan → gate → work → evaluate → decide.

Each stage's subgraph runs atomically from the parent pipeline's perspective —
no child checkpointer; inner transitions don't produce independent persisted
steps. State flows through the subgraph's TypedDict, and PipelineState is
mutated in place under the `state` key.

See spec §3.2.1 for the node shape and §3.2.2 for StagePlan semantics.
"""
from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from agentlabx.core.state import PipelineState, StagePlan
from agentlabx.stages.base import (
    BaseStage,
    StageContext,
    StageEvaluation,
    StageExecution,
    StageResult,
)


class _SubgraphState(TypedDict, total=False):
    """Working state for a single stage's subgraph execution.

    `state` is the full PipelineState (mutated as the subgraph runs so the
    caller sees observability updates written by the stage_plan node).
    `context` is the StageContext injected by StageRunner.
    Intermediate hooks stash their outputs under their own keys so later
    nodes can read.
    """
    state: PipelineState
    context: StageContext
    plan: StagePlan
    execution: StageExecution
    evaluation: StageEvaluation
    stage_result: StageResult


class StageSubgraphBuilder:
    """Compose a BaseStage into a compiled LangGraph subgraph.

    Usage:
        compiled = StageSubgraphBuilder().compile(stage)
        result = await compiled.ainvoke(
            {"state": pipeline_state, "context": stage_context},
            config={"configurable": {"thread_id": "..."}},
        )
        stage_result: StageResult = result["stage_result"]
    """

    def compile(self, stage: BaseStage) -> Any:
        builder: StateGraph = StateGraph(_SubgraphState)

        def enter_node(s: _SubgraphState) -> dict[str, Any]:
            s["state"]["current_stage_internal_node"] = "enter"
            # Placeholder — reserved for memory hydration on re-entry (Plan 7C+).
            # Feedback pickup is handled in stage_plan, not here.
            return {}

        async def plan_node(s: _SubgraphState) -> dict[str, Any]:
            s["state"]["current_stage_internal_node"] = "stage_plan"
            feedback = s["state"].get("backtrack_feedback")
            plan = stage.build_plan(s["state"], feedback=feedback)
            # Persist the plan on state for observability (versioned per entry).
            # INVARIANT (spec §3.2.2 / Plan 7B T1): stage_plans is a plain dict
            # with in-place mutation; DO NOT return {"state": {"stage_plans": ...}}
            # as a partial update — that would wipe other stages' entries.
            plans: dict = dict(s["state"].get("stage_plans", {}))
            history = list(plans.get(stage.name, []))
            history.append(plan)
            plans[stage.name] = history
            s["state"]["stage_plans"] = plans
            return {"plan": plan}

        def gate_node(s: _SubgraphState) -> str:
            """Route: no actionable items → decide (bypass); else → work."""
            plan = s["plan"]
            actionable = [
                i for i in plan["items"]
                if i["status"] in ("todo", "edit")
            ]
            if not actionable:
                return "decide"
            return "work"

        async def work_node(s: _SubgraphState) -> dict[str, Any]:
            s["state"]["current_stage_internal_node"] = "work"
            execution = await stage.execute_plan(
                s["state"], s["plan"], s["context"]
            )
            return {"execution": execution}

        def evaluate_node(s: _SubgraphState) -> dict[str, Any]:
            s["state"]["current_stage_internal_node"] = "evaluate"
            evaluation = stage.evaluate(
                s["state"], plan=s["plan"], execution=s["execution"]
            )
            return {"evaluation": evaluation}

        def decide_node(s: _SubgraphState) -> dict[str, Any]:
            s["state"]["current_stage_internal_node"] = "decide"
            execution = s.get("execution")
            evaluation = s.get("evaluation")
            if execution is None:
                # Bypass path: no work ran. Synthesise a 'done' execution
                # carrying the plan's rationale as the reason.
                rationale = s["plan"]["rationale"]
                execution = StageExecution(
                    output={},
                    status="done",
                    reason=f"plan-empty: {rationale}",
                )
            if evaluation is None:
                evaluation = StageEvaluation()
            result = stage.decide(
                s["state"],
                plan=s["plan"],
                execution=execution,
                evaluation=evaluation,
            )
            return {"stage_result": result}

        builder.add_node("enter", enter_node)
        builder.add_node("stage_plan", plan_node)
        builder.add_node("work", work_node)
        builder.add_node("evaluate", evaluate_node)
        builder.add_node("decide", decide_node)

        builder.add_edge(START, "enter")
        builder.add_edge("enter", "stage_plan")
        builder.add_conditional_edges(
            "stage_plan",
            gate_node,
            {"work": "work", "decide": "decide"},
        )
        builder.add_edge("work", "evaluate")
        builder.add_edge("evaluate", "decide")
        builder.add_edge("decide", END)

        # Compile WITHOUT a checkpointer — subgraph runs atomically from the
        # parent pipeline's perspective. The parent's AsyncSqliteSaver
        # persists at parent-node boundaries; pause/resume mid-stage
        # restarts the subgraph from `enter`.
        return builder.compile()
