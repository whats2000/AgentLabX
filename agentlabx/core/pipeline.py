"""PipelineBuilder — assembles a LangGraph StateGraph with dynamic routing."""

from __future__ import annotations

from typing import Any

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from agentlabx.core.registry import PluginRegistry, PluginType
from agentlabx.core.session import SessionPreferences
from agentlabx.core.state import PipelineState
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
    ) -> None:
        self.registry = registry
        self.preferences = preferences or SessionPreferences()

    def build(
        self,
        stage_sequence: list[str],
        checkpointer: Any | None = None,
    ) -> Any:
        """Create and compile a StateGraph for the given stage sequence.

        Parameters
        ----------
        stage_sequence:
            Ordered list of stage names (must be registered under PluginType.STAGE).
        checkpointer:
            LangGraph checkpointer instance. Defaults to MemorySaver().

        Returns
        -------
        Compiled LangGraph graph, ready for ainvoke/astream.
        """
        if checkpointer is None:
            checkpointer = MemorySaver()

        builder = StateGraph(PipelineState)

        # Resolve stage classes and create runners
        runners: dict[str, StageRunner] = {}
        for stage_name in stage_sequence:
            stage_cls = self.registry.resolve(PluginType.STAGE, stage_name)
            stage_instance = stage_cls()
            runners[stage_name] = StageRunner(stage_instance)

        # Add stage nodes
        for stage_name, runner in runners.items():
            builder.add_node(stage_name, runner.run)

        # Add transition node
        transition_handler = TransitionHandler(preferences=self.preferences)

        def transition_node(state: PipelineState) -> dict[str, Any]:
            """Run transition logic: decide next stage, update tracking fields."""
            decision = transition_handler.decide(state)
            current = state.get("current_stage", "")
            update: dict[str, Any] = {
                "next_stage": decision.next_stage,
                "human_override": None,
            }
            # completed_stages is a reducer (operator.add) field — append current
            if current:
                update["completed_stages"] = [current]
            return update

        builder.add_node("transition", transition_node)

        # Wire edges: START → first stage
        builder.add_edge(START, stage_sequence[0])

        # Each stage → transition
        for stage_name in stage_sequence:
            builder.add_edge(stage_name, "transition")

        # Conditional edges from transition → stage or END
        route_map: dict[str, str] = {name: name for name in stage_sequence}
        route_map["__end__"] = END

        def route_after_transition(state: PipelineState) -> str:
            next_stage = state.get("next_stage")
            if next_stage is None or next_stage not in route_map:
                return "__end__"
            return next_stage

        builder.add_conditional_edges("transition", route_after_transition, route_map)

        return builder.compile(checkpointer=checkpointer)
