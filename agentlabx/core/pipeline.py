"""PipelineBuilder — assembles a LangGraph StateGraph with dynamic routing."""

from __future__ import annotations

from typing import Any

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from agentlabx.core.events import Event, EventBus
from agentlabx.core.event_types import EventTypes
from agentlabx.core.registry import PluginRegistry, PluginType
from agentlabx.core.session import SessionPreferences
from datetime import UTC, datetime

from agentlabx.core.state import (
    CostTracker,
    PipelineState,
    StageError,
    Transition,
    apply_partial_rollback,
)
from agentlabx.providers.llm.base import BaseLLMProvider
from agentlabx.stages.base import StageContext
from agentlabx.stages.runner import StageRunner
from agentlabx.stages.transition import TransitionHandler


class PipelineBuilder:
    """Builds a LangGraph StateGraph from registered stages.

    The graph topology:
        START → first_stage → transition → (conditional) → next_stage | END
        Each stage → transition (static edge)
        transition → conditional edges based on state["next_stage"]
    """

    def __init__(
        self,
        registry: PluginRegistry,
        preferences: SessionPreferences | None = None,
        pi_advisor: Any = None,  # PIAgent | None — Any to keep import light
    ) -> None:
        self.registry = registry
        self.preferences = preferences or SessionPreferences()
        self.pi_advisor = pi_advisor

    def build(
        self,
        stage_sequence: list[str],
        *,
        checkpointer: Any | None = None,
        llm_provider: BaseLLMProvider | None = None,
        cost_tracker: CostTracker | None = None,
        event_bus: EventBus | None = None,
        stage_context: StageContext | None = None,
    ) -> Any:
        """Create and compile a StateGraph for the given stage sequence.

        Parameters
        ----------
        stage_sequence:
            Ordered list of stage names (must be registered under PluginType.STAGE).
        checkpointer:
            LangGraph checkpointer instance. Defaults to MemorySaver().
        llm_provider:
            LLM provider to wire into all stage contexts.
        cost_tracker:
            Shared cost tracker to wire into all stage contexts.
        event_bus:
            Event bus to wire into all stage contexts.
        stage_context:
            If provided, used as-is (allows executor to inject a context with
            paused_event etc.). Otherwise, one is constructed from the other kwargs.

        Returns
        -------
        Compiled LangGraph graph, ready for ainvoke/astream.
        """
        if checkpointer is None:
            checkpointer = MemorySaver()

        if stage_context is None:
            # Only wire the registry into the stage context when at least one
            # provider or bus is explicitly supplied. This preserves backward
            # compatibility for tests that rely on registry=None causing real
            # stages to degrade gracefully instead of hard-failing on missing
            # agent/tool registrations.
            wired_registry = (
                self.registry
                if (llm_provider is not None or cost_tracker is not None or event_bus is not None)
                else None
            )
            stage_context = StageContext(
                settings={},
                event_bus=event_bus,
                registry=wired_registry,
                llm_provider=llm_provider,
                cost_tracker=cost_tracker,
            )

        builder = StateGraph(PipelineState)

        # Resolve stage classes and create runners with the shared context.
        # Invocable-only stages (§5.5) are registered but excluded from the
        # top-level graph wiring — they are callable subgraphs invoked on demand.
        runners: dict[str, StageRunner] = {}
        effective_sequence: list[str] = []
        for stage_name in stage_sequence:
            stage_cls = self.registry.resolve(PluginType.STAGE, stage_name)
            if getattr(stage_cls, "invocable_only", False):
                # Callable subgraph — not wired into the top-level graph.
                # Invoked from stage work nodes when requested (§5.5).
                continue
            stage_instance = stage_cls()
            runners[stage_name] = StageRunner(stage_instance, context=stage_context)
            effective_sequence.append(stage_name)

        if not effective_sequence:
            raise ValueError(
                "stage_sequence has no runnable (non-invocable-only) stages"
            )

        # Add stage nodes
        for stage_name, runner in runners.items():
            builder.add_node(stage_name, runner.run)

        # Add transition node
        transition_handler = TransitionHandler(
            preferences=self.preferences,
            pi_advisor=self.pi_advisor,
        )

        async def transition_node(state: PipelineState) -> dict[str, Any]:
            """Route to next stage; maintain counters, log, partial rollback."""
            decision = await transition_handler.decide_async(state)

            # Emit checkpoint_reached when the transition decision requires
            # human approval (Plan 7D T7). The CheckpointModal listens for
            # this event via the WebSocket event stream.
            if decision.needs_approval and event_bus is not None:
                current_stage = state.get("current_stage", "")
                pi_decisions: list[dict] = state.get("pi_decisions") or []
                latest_pi = pi_decisions[-1] if pi_decisions else None
                await event_bus.emit(
                    Event(
                        type=EventTypes.CHECKPOINT_REACHED,
                        data={
                            "stage": current_stage,
                            "next_stage": decision.next_stage,
                            "reason": decision.reason,
                            "pi_recommendation": (
                                latest_pi.get("reasoning") if latest_pi else None
                            ),
                        },
                        source="transition_node",
                    )
                )
            current = state.get("current_stage", "")
            update: dict[str, Any] = {
                "next_stage": decision.next_stage,
                "human_override": None,
            }

            # completed_stages is a reducer (operator.add) field — append current
            if current:
                update["completed_stages"] = [current]

            if decision.action == "backtrack" and decision.next_stage:
                # Partial rollback: rewind current_stage + keep feedback; all
                # other state (hypotheses, experiment_log, etc.) preserved.
                rollback = apply_partial_rollback(
                    state,
                    target=decision.next_stage,
                    feedback=state.get("backtrack_feedback"),
                )
                update.update(rollback)
                # (no manual next_stage overwrite needed — the helper returns
                # next_stage=target so routing flows correctly.)

                edge_key = f"{current}->{decision.next_stage}"
                attempts = dict(state.get("backtrack_attempts", {}))
                attempts[edge_key] = attempts.get(edge_key, 0) + 1
                update["backtrack_attempts"] = attempts

            elif decision.action in ("advance", "forced_advance") and current:
                # Forward advance: clear any stale feedback, reset counters
                # for edges originating at the now-completed stage.
                update["backtrack_feedback"] = None
                attempts = dict(state.get("backtrack_attempts", {}))
                stale = [k for k in attempts if k.startswith(f"{current}->")]
                for k in stale:
                    attempts.pop(k, None)
                if stale:
                    update["backtrack_attempts"] = attempts

            elif decision.action == "backtrack_limit_exceeded":
                # Handler already computed a concrete fallback; apply it +
                # log an error explaining the escalation.
                update["backtrack_feedback"] = None
                update["errors"] = [
                    StageError(
                        stage=current,
                        error_type="backtrack_limit_exceeded",
                        message=decision.reason,
                        timestamp=datetime.now(UTC),
                        recovered=False,
                    )
                ]

            # transition_log: append one entry per transition (except complete).
            if decision.action != "complete" and current and decision.next_stage:
                triggered_by_map = {
                    "human_override": "human",
                    "forced_advance": "system",
                    "backtrack_limit_exceeded": "system",
                    "advance": "agent",
                    "backtrack": "agent",
                }
                update["transition_log"] = [
                    Transition(
                        from_stage=current,
                        to_stage=decision.next_stage,
                        reason=decision.reason,
                        triggered_by=triggered_by_map.get(decision.action, "system"),
                        timestamp=datetime.now(UTC),
                    )
                ]

            return update

        builder.add_node("transition", transition_node)

        # Wire edges: START → first stage
        builder.add_edge(START, effective_sequence[0])

        # Each stage → transition
        for stage_name in effective_sequence:
            builder.add_edge(stage_name, "transition")

        # Conditional edges from transition → stage or END
        route_map: dict[str, str] = {name: name for name in effective_sequence}
        route_map["__end__"] = END

        def route_after_transition(state: PipelineState) -> str:
            next_stage = state.get("next_stage")
            if next_stage is None or next_stage not in route_map:
                return "__end__"
            return next_stage

        builder.add_conditional_edges("transition", route_after_transition, route_map)

        return builder.compile(checkpointer=checkpointer)
