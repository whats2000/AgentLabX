"""Base stage contract for pipeline stages."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, ClassVar, Literal

from pydantic import BaseModel

from agentlabx.core.state import CrossStageRequest, PipelineState

if TYPE_CHECKING:
    from agentlabx.agents.base import BaseAgent


def sync_agent_memory_to_state(state: dict, agents: dict[str, BaseAgent]) -> None:
    """Write each dirty agent's snapshot into state[agent_memory][name]. Clears dirty flags.

    Args:
        state: The pipeline state dict to update.
        agents: A dict mapping agent names to BaseAgent instances.
    """
    # INVARIANT (2026-04-13, Plan 6A): this helper mutates state["agent_memory"]
    # in place. PipelineState declares `agent_memory: dict[str, AgentMemoryRecord]`
    # WITHOUT an `Annotated[..., reducer]` wrapper, so LangGraph's default
    # behavior is whole-value overwrite — NOT dict merge. The current pipeline
    # is safe only because (1) stages run sequentially and (2) every stage calls
    # this helper which setdefault's the live dict before mutating.
    #
    # DO NOT refactor this helper to build a fresh dict and return it, OR return
    # `{"agent_memory": memory}` as a partial state update from a stage — either
    # change will silently wipe entries for agents that didn't run in this stage.
    #
    # If Plan 6B/7 introduces event-driven paths that return partial state dicts,
    # switch PipelineState.agent_memory to `Annotated[dict, _merge_agent_memory]`
    # with a proper dict-merge reducer BEFORE relying on partial updates.
    memory = state.setdefault("agent_memory", {})
    for name, agent in agents.items():
        if getattr(agent, "dirty", False):
            memory[name] = agent.snapshot_memory()
            agent.dirty = False


class StageContext(BaseModel):
    """Runtime context passed to every stage.

    Stages receive this with all the infrastructure they need.

    Fields:
    - registry: PluginRegistry for resolving agents and tools
    - event_bus: EventBus for emitting progress events
    - settings: Application settings
    - llm_provider: BaseLLMProvider instance — stages pass this to agents
      when instantiating them. None → agents run in mock mode (Plan 2 default).
    - cost_tracker: Shared CostTracker accumulated across agent calls.
      None → no cost accumulation. PipelineBuilder wires this to the session's
      state["cost_tracker"] so budget policies can see live spend.
    - paused_event: asyncio.Event — set=running, cleared=paused. StageRunner
      awaits this between on_enter and stage.run for cooperative pause.
      None = no pause support (default).
    """

    settings: Any = None
    event_bus: Any = None
    storage: Any = None
    registry: Any = None
    llm_provider: Any = None
    cost_tracker: Any = None
    paused_event: Any = None
    model_config = {"arbitrary_types_allowed": True}


class StageResult(BaseModel):
    output: Any
    status: Literal["done", "backtrack", "negative_result", "request"]
    next_hint: str | None = None
    reason: str
    feedback: str | None = None
    requests: list[CrossStageRequest] | None = None


ZoneName = Literal["discovery", "implementation", "synthesis"]


class BaseStage(ABC):
    name: str
    description: str
    required_agents: list[str]
    required_tools: list[str]
    zone: ClassVar[ZoneName | None] = None

    @abstractmethod
    async def run(self, state: PipelineState, context: StageContext) -> StageResult: ...

    def validate(self, state: PipelineState) -> bool:
        return True

    def on_enter(self, state: PipelineState) -> PipelineState:
        return state

    def on_exit(self, state: PipelineState) -> PipelineState:
        return state
