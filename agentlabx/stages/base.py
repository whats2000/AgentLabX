"""Base stage contract for pipeline stages."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Literal

from pydantic import BaseModel

from agentlabx.core.state import CrossStageRequest, PipelineState


class StageContext(BaseModel):
    """Runtime context passed to every stage.

    Stages receive this with all the infrastructure they need:
    - registry: PluginRegistry for resolving agents and tools
    - event_bus: EventBus for emitting progress events
    - settings: Application settings
    - llm_provider: BaseLLMProvider instance — stages pass this to agents when
      instantiating them. None → agents run in mock mode (Plan 2 default).
    - cost_tracker: Shared CostTracker that agents update after each LLM call.
      None → no cost accumulation. PipelineBuilder wires this to the session's
      state["cost_tracker"] so budget policies can see live spend.
    """

    settings: Any = None
    event_bus: Any = None
    registry: Any = None
    llm_provider: Any = None
    cost_tracker: Any = None
    model_config = {"arbitrary_types_allowed": True}


class StageResult(BaseModel):
    output: Any
    status: Literal["done", "backtrack", "negative_result", "request"]
    next_hint: str | None = None
    reason: str
    feedback: str | None = None
    requests: list[CrossStageRequest] | None = None


class BaseStage(ABC):
    name: str
    description: str
    required_agents: list[str]
    required_tools: list[str]

    @abstractmethod
    async def run(self, state: PipelineState, context: StageContext) -> StageResult: ...

    def validate(self, state: PipelineState) -> bool:
        return True

    def on_enter(self, state: PipelineState) -> PipelineState:
        return state

    def on_exit(self, state: PipelineState) -> PipelineState:
        return state
