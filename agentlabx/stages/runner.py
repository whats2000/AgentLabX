"""StageRunner — LangGraph-compatible node wrapper for BaseStage instances."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from agentlabx.core.events import Event
from agentlabx.core.state import PipelineState, StageError
from agentlabx.stages.base import BaseStage, StageContext, StageResult
from agentlabx.stages.subgraph import StageSubgraphBuilder


class StageRunner:
    """Wraps a BaseStage for execution within a LangGraph graph.

    Returns a PARTIAL state dict. Emits stage_started / stage_completed /
    stage_failed events via context.event_bus (mutually exclusive: success
    emits started+completed, failure emits started+failed). Awaits
    context.paused_event before invoking the stage (cooperative pause).
    """

    def __init__(self, stage: BaseStage, context: StageContext | None = None) -> None:
        self.stage = stage
        self.context = context or StageContext(settings={}, event_bus=None, registry=None)
        # Compile the stage's LangGraph subgraph once at construction —
        # the compiled object is reused across every run() call. See
        # agentlabx/stages/subgraph.py and spec §3.2.1.
        self._compiled_subgraph = StageSubgraphBuilder().compile(stage)

    async def run(self, state: PipelineState) -> dict[str, Any]:
        """Execute stage, return PARTIAL state update (LangGraph merges via reducers).

        The stage's StageResult.output is merged into the update dict when it
        contains keys matching PipelineState fields. Reducer fields (e.g.,
        literature_review, plan, hypotheses) get appended; overwrite fields
        replace the prior value. Runner-owned tracking fields (current_stage,
        stage_iterations, total_iterations, next_stage) take precedence over
        anything the stage writes with the same name.
        """
        update: dict[str, Any] = {}
        session_id = state.get("session_id", "")

        # Emit stage_started
        if self.context.event_bus is not None:
            await self.context.event_bus.emit(
                Event(
                    type="stage_started",
                    data={"stage": self.stage.name, "session_id": session_id},
                    source=self.stage.name,
                )
            )

        # Snapshot cost_tracker.total_cost for backtrack-cost accounting
        # Must be taken before on_enter so any cost incurred during on_enter
        # is attributed to the stage run, not hidden in the baseline.
        cost_tracker_at_entry = state.get("cost_tracker")
        cost_at_entry = (
            float(cost_tracker_at_entry.total_cost) if cost_tracker_at_entry else 0.0
        )

        # Call on_enter (may modify state — but we pass original state)
        entered_state = self.stage.on_enter(state)

        # Cooperative pause — wait if paused (Fix A)
        paused_event = self.context.paused_event
        if paused_event is not None:
            await paused_event.wait()

        try:
            # Include stage iteration count so backtrack-induced re-entries get distinct
            # thread_ids. The subgraph has no child checkpointer today (see subgraph.py),
            # so thread_id is just ephemeral message-passing scope — but reuse across
            # invocations would cause channel state leakage if a checkpointer is added later.
            stage_iter = state.get("stage_iterations", {}).get(self.stage.name, 0)
            subgraph_result = await self._compiled_subgraph.ainvoke(
                {"state": entered_state, "context": self.context},
                config={
                    "configurable": {
                        "thread_id": f"{state.get('session_id', 's')}:{self.stage.name}:{stage_iter}"
                    }
                },
            )
            result: StageResult = subgraph_result["stage_result"]

            # Propagate stage_plans back to the outer pipeline state.
            # The subgraph's plan_node mutates s["state"]["stage_plans"] in-place
            # and that mutation is reflected in subgraph_result["state"]. LangGraph
            # only applies node return dicts — in-place mutations on the input state
            # are discarded — so we must explicitly include stage_plans in the update.
            # stage_plans is a plain dict field (no reducer), so returning the whole
            # updated dict causes a safe overwrite (stages run sequentially).
            updated_stage_plans = subgraph_result.get("state", {}).get("stage_plans")
            if updated_stage_plans is not None:
                update["stage_plans"] = updated_stage_plans

            # Merge stage output — this is how literature_review, plan, hypotheses,
            # review, etc. flow back into state. Reducer annotations on PipelineState
            # handle appending for list fields.
            if isinstance(result.output, dict):
                for key, value in result.output.items():
                    update[key] = value

            # Routing hints (overwrite fields — runner owns these)
            update["next_stage"] = result.next_hint

            # Cross-stage requests (reducer field — return only NEW requests)
            if result.requests:
                update["pending_requests"] = list(result.requests)

            # Backtrack-specific state plumbing (Plan 7A)
            if result.status == "backtrack":
                # Feedback handoff: target stage reads this on re-entry
                update["backtrack_feedback"] = result.feedback

                # Cost attribution: the cost of this run led to the backtrack
                current_total = (
                    float(cost_tracker_at_entry.total_cost)
                    if cost_tracker_at_entry else 0.0
                )
                delta = max(0.0, current_total - cost_at_entry)
                prior = float(state.get("backtrack_cost_spent", 0.0))
                update["backtrack_cost_spent"] = prior + delta

            # Emit stage_completed (only on success path — Fix K: never both)
            if self.context.event_bus is not None:
                await self.context.event_bus.emit(
                    Event(
                        type="stage_completed",
                        data={
                            "stage": self.stage.name,
                            "session_id": session_id,
                            "status": result.status,
                            "reason": result.reason,
                            "next_hint": result.next_hint,
                        },
                        source=self.stage.name,
                    )
                )
        except Exception as e:
            error = StageError(
                stage=self.stage.name,
                error_type=type(e).__name__,
                message=str(e),
                timestamp=datetime.now(UTC),
                recovered=False,
            )
            # errors is a reducer field — return only the NEW error
            update["errors"] = [error]

            # Clear next_stage on failure so the transition handler falls through
            # to priority-5 advance (or priority-6 complete). Without this, a
            # stale next_stage value from a prior transition would re-route back
            # to this same stage indefinitely.
            update["next_stage"] = None

            # Emit stage_failed (only on exception path — Fix K: never both)
            if self.context.event_bus is not None:
                await self.context.event_bus.emit(
                    Event(
                        type="stage_failed",
                        data={
                            "stage": self.stage.name,
                            "session_id": session_id,
                            "error_type": type(e).__name__,
                            "message": str(e),
                        },
                        source=self.stage.name,
                    )
                )

        # Runner-owned tracking fields — these always take precedence over
        # anything the stage may have written with the same key.
        update["current_stage"] = self.stage.name
        stage_iters = dict(state.get("stage_iterations", {}))
        stage_iters[self.stage.name] = stage_iters.get(self.stage.name, 0) + 1
        update["stage_iterations"] = stage_iters
        update["total_iterations"] = state.get("total_iterations", 0) + 1

        # Call on_exit
        self.stage.on_exit(state)
        return update
