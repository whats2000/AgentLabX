"""Base stage contract for pipeline stages."""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Literal
from pydantic import BaseModel
from agentlabx.core.state import CrossStageRequest, PipelineState


class StageContext(BaseModel):
    settings: Any
    event_bus: Any
    registry: Any
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
