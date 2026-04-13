"""PI Agent — intelligent transition handler with confidence scoring."""

from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel

from agentlabx.agents.config_loader import AgentConfig
from agentlabx.agents.context import ContextAssembler
from agentlabx.core.events import Event, EventBus
from agentlabx.core.session import SessionPreferences
from agentlabx.core.state import PipelineState
from agentlabx.providers.llm.base import BaseLLMProvider
from agentlabx.server.events import EventTypes
from agentlabx.stages.transition import TransitionHandler


class PIDecision(BaseModel):
    next_stage: str | None
    action: str
    reason: str
    confidence: float
    budget_note: str | None = None
    used_fallback: bool = False


PI_DECISION_SYSTEM_PROMPT = (
    "You are a research director. Respond ONLY with a JSON object of the form: "
    '{"agree_with_rule": true|false, "next_stage": "<stage name or null>", '
    '"confidence": <float between 0.0 and 1.0>, "reasoning": "<1-3 sentences>"}. '
    "No prose, no markdown, no explanation outside the JSON."
)

PI_DECISION_PROMPT = (
    "You are the Principal Investigator directing this research project."
    " Decide what the lab should do next.\n\n"
    "Current research state:\n{context}\n\n"
    "The rule-based handler suggests: transition to '{rule_next_stage}'"
    " (action: {rule_action}, reason: {rule_reason}).\n\n"
    "Evaluate this decision. Consider:\n"
    "1. Are the research goals being met?\n"
    "2. Is the rule-based suggestion appropriate given what we've accomplished?\n"
    "3. What is the confidence in this decision (0.0-1.0)?\n\n"
    "{budget_note}\n\n"
    "Respond with valid JSON only."
)


class PIAgent:
    """PI agent — wraps TransitionHandler with LLM judgment + confidence scoring.

    When llm_provider is None, falls back to rule-based decisions (Plan 2 behavior).
    When llm_provider is present, the PI agent evaluates the rule-based
    suggestion and may override it.
    """

    def __init__(
        self,
        transition_handler: TransitionHandler,
        pi_agent_config: AgentConfig | None = None,
        llm_provider: BaseLLMProvider | None = None,
        model: str = "claude-sonnet-4-6",
        confidence_threshold: float | None = None,
        event_bus: EventBus | None = None,
    ) -> None:
        self.transition_handler = transition_handler
        self.llm_provider = llm_provider
        self.model = model
        self._event_bus = event_bus
        # Threshold priority: explicit arg > config.confidence_threshold > default
        if confidence_threshold is not None:
            self.confidence_threshold = confidence_threshold
        elif pi_agent_config and pi_agent_config.confidence_threshold is not None:
            self.confidence_threshold = pi_agent_config.confidence_threshold
        else:
            self.confidence_threshold = 0.6
        # Memory scope from YAML (default to empty if no config provided)
        if pi_agent_config is not None:
            self._memory_scope = pi_agent_config.memory_scope
        else:
            from agentlabx.agents.base import MemoryScope

            self._memory_scope = MemoryScope()
        self._context_assembler = ContextAssembler()
        self.decision_history: list[PIDecision] = []

    async def _finalize(self, decision: PIDecision, state: PipelineState) -> PIDecision:
        """Persist decision to state and emit event; called from every return path."""
        decision_dict = decision.model_dump()
        decision_dict["decision_id"] = uuid.uuid4().hex
        decision_dict["ts"] = datetime.now(UTC).isoformat()
        state.setdefault("pi_decisions", []).append(decision_dict)
        self.decision_history.append(decision)

        if self._event_bus is not None:
            await self._event_bus.emit(
                Event(
                    type=EventTypes.PI_DECISION,
                    data=decision_dict,
                    source="pi_agent",
                )
            )
        return decision

    async def decide(
        self,
        state: PipelineState,
        preferences: SessionPreferences,
        budget_warning: bool = False,
    ) -> PIDecision:
        rule_decision = self.transition_handler.decide(state)

        # Mock path (no LLM): Plan 2 behavior
        if self.llm_provider is None:
            confidence = 0.85
            used_fallback = confidence < self.confidence_threshold
            decision = PIDecision(
                next_stage=rule_decision.next_stage,
                action=rule_decision.action,
                reason=rule_decision.reason,
                confidence=confidence,
                budget_note="Budget warning active" if budget_warning else None,
                used_fallback=used_fallback,
            )
            return await self._finalize(decision, state)

        # LLM path: assemble context, query, parse JSON
        context_dict = self._context_assembler.assemble(state, self._memory_scope)
        context_text = self._context_assembler.format_for_prompt(context_dict)

        budget_note_text = (
            "Budget is tight (>70% spent). Bias toward completing rather than iterating."
            if budget_warning
            else ""
        )
        prompt = PI_DECISION_PROMPT.format(
            context=context_text,
            rule_next_stage=rule_decision.next_stage or "END",
            rule_action=rule_decision.action,
            rule_reason=rule_decision.reason,
            budget_note=budget_note_text,
        )

        try:
            response = await self.llm_provider.query(
                model=self.model,
                prompt=prompt,
                system_prompt=PI_DECISION_SYSTEM_PROMPT,
                temperature=0.1,
            )
            parsed = self._parse_decision(response.content)
            confidence = float(parsed.get("confidence", 0.5))

            used_fallback = False
            agree = parsed.get("agree_with_rule", True)

            if confidence < self.confidence_threshold:
                # Low confidence → use rule decision
                used_fallback = True
                next_stage = rule_decision.next_stage
                action = rule_decision.action
                reason = rule_decision.reason
            elif agree:
                next_stage = rule_decision.next_stage
                action = rule_decision.action
                reason = rule_decision.reason
            else:
                next_stage = parsed.get("next_stage")
                action = "pi_override"
                reason = parsed.get("reasoning", "PI disagreed with rule-based suggestion")
        except Exception as e:
            next_stage = rule_decision.next_stage
            action = rule_decision.action
            reason = f"Rule fallback (LLM error: {e})"
            confidence = 0.0
            used_fallback = True

        decision = PIDecision(
            next_stage=next_stage,
            action=action,
            reason=reason,
            confidence=confidence,
            budget_note="Budget warning active" if budget_warning else None,
            used_fallback=used_fallback,
        )
        return await self._finalize(decision, state)

    def _parse_decision(self, text: str) -> dict[str, Any]:
        """Extract JSON from the LLM response.

        Tries direct JSON parse first, then regex extraction as defensive
        fallback for LLMs that wrap JSON in markdown despite the system prompt.
        """
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        # Defensive fallback: extract {...} block
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
        return {}
