from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from agentlabx.core.session import SessionPreferences
from agentlabx.core.state import PipelineState
from agentlabx.stages.transition import TransitionHandler


class PIDecision(BaseModel):
    next_stage: str | None
    action: str
    reason: str
    confidence: float
    budget_note: str | None = None
    used_fallback: bool = False


class PIAgent:
    def __init__(self, transition_handler: TransitionHandler, confidence_threshold: float = 0.6) -> None:
        self.transition_handler = transition_handler
        self.confidence_threshold = confidence_threshold
        self.decision_history: list[PIDecision] = []

    async def decide(
        self,
        state: PipelineState,
        preferences: SessionPreferences,
        budget_warning: bool = False,
    ) -> PIDecision:
        rule_decision = self.transition_handler.decide(state)
        confidence = 0.85  # Mock — Plan 3 adds real LLM confidence

        budget_note = None
        if budget_warning:
            budget_note = "Budget warning active — biasing toward completion"

        used_fallback = False
        if confidence < self.confidence_threshold:
            used_fallback = True

        decision = PIDecision(
            next_stage=rule_decision.next_stage,
            action=rule_decision.action,
            reason=rule_decision.reason,
            confidence=confidence,
            budget_note=budget_note,
            used_fallback=used_fallback,
        )
        self.decision_history.append(decision)
        return decision
