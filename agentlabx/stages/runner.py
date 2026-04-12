"""StageRunner — LangGraph-compatible node wrapper for BaseStage instances."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from agentlabx.core.state import PipelineState, StageError
from agentlabx.stages.base import BaseStage, StageContext


class StageRunner:
    """Wraps a BaseStage for execution within a LangGraph graph.

    Returns a PARTIAL state dict containing only the fields that changed.
    LangGraph merges this into the full state using the reducer annotations
    defined on PipelineState (Annotated[list[X], operator.add] for accumulating
    fields, plain types for overwrite fields).
    """

    def __init__(self, stage: BaseStage, context: StageContext | None = None) -> None:
        self.stage = stage
        self.context = context or StageContext(settings={}, event_bus=None, registry=None)

    async def run(self, state: PipelineState) -> dict[str, Any]:
        """Execute stage, return PARTIAL state update (LangGraph merges via reducers)."""
        # Build update dict — only include fields we're changing
        update: dict[str, Any] = {"current_stage": self.stage.name}

        # Increment iterations (these are overwrite fields, not reducer fields)
        stage_iters = dict(state.get("stage_iterations", {}))
        stage_iters[self.stage.name] = stage_iters.get(self.stage.name, 0) + 1
        update["stage_iterations"] = stage_iters
        update["total_iterations"] = state.get("total_iterations", 0) + 1

        # Call on_enter (may modify state — but we pass original state)
        entered_state = self.stage.on_enter(state)

        try:
            result = await self.stage.run(entered_state, self.context)
            # Routing hints (overwrite fields)
            update["next_stage"] = result.next_hint
            # Cross-stage requests (reducer field — return only NEW requests)
            if result.requests:
                update["pending_requests"] = list(result.requests)
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

        # Call on_exit
        self.stage.on_exit(state)
        return update
