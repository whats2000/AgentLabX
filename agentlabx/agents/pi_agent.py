"""PI Advisor — participating helper consulted at specific checkpoints.

Reframed in Plan 7C from "intelligent transition handler" to "advisor."
The transition handler (agentlabx/stages/transition.py) is the routing
engine. PI is consulted at checkpoints — currently:
  - ConsultKind.BACKTRACK_LIMIT — when per-edge retry or cost fraction
    exceeded (spec §3.3.7). Advisor suggests where to route instead of
    the default-sequence force-advance.
  - ConsultKind.NEGATIVE_RESULT — when a stage returns status="negative_result"
    (spec §3.3 + §5.5). Advisor decides publish / pivot / redirect.

Future consultation kinds (deferred to Plan 7C² / 7D):
  - ConsultKind.ZONE_TRANSITION — at zone boundaries (discovery →
    implementation → synthesis)
  - ConsultKind.HITL_APPROVE — accompanying the CheckpointModal with a
    recommendation

**Observability contract (Plan 6B + 7C):** PI is NOT a turn-grained agent.
Its LLM calls do NOT appear in /api/sessions/{id}/agents/pi_agent/history
because consult_escalation() does not push a TurnContext. PI decisions are
observable via:
  - REST: GET /api/sessions/{id}/pi/history → state["pi_decisions"]
  - WebSocket: pi_decision event (emitted from _finalize)
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel

from agentlabx.agents.config_loader import AgentConfig
from agentlabx.agents.context import ContextAssembler
from agentlabx.core.event_types import EventTypes
from agentlabx.core.events import Event, EventBus
from agentlabx.core.state import PipelineState
from agentlabx.providers.llm.base import BaseLLMProvider


class ConsultKind(StrEnum):
    BACKTRACK_LIMIT = "backtrack_limit"
    NEGATIVE_RESULT = "negative_result"
    # Reserved for future plans:
    # ZONE_TRANSITION = "zone_transition"
    # HITL_APPROVE = "hitl_approve"


class PIAdvice(BaseModel):
    checkpoint: ConsultKind
    next_stage: str | None
    reasoning: str
    confidence: float
    used_fallback: bool = False


# Dedicated prompts per checkpoint kind.

_BACKTRACK_LIMIT_SYSTEM = (
    "You are the Principal Investigator of a research lab. The per-edge "
    "backtrack retry limit has been exceeded, meaning the lab has tried and "
    "failed to re-run an earlier stage multiple times. Respond ONLY with JSON: "
    '{"next_stage": "<stage name>", "confidence": <0.0-1.0>, '
    '"reasoning": "<1-3 sentences>"}.'
)

_BACKTRACK_LIMIT_PROMPT = (
    "The stage '{origin}' has requested backtrack to '{target}' "
    "{attempts}/{max_attempts} times. Default-sequence fallback would route "
    "to '{rule_fallback}'.\n\n"
    "Current research state:\n{context}\n\n"
    "Given the research goals and what we've learned, where should we go? "
    "You may keep '{rule_fallback}' or suggest a different stage. "
    "Respond with valid JSON only."
)

_NEGATIVE_RESULT_SYSTEM = (
    "You are the Principal Investigator. A stage returned a conclusive "
    "negative result — the hypothesis was refuted. Decide whether to "
    "publish the negative finding, pivot the hypothesis, or redirect to "
    "a different angle. Respond ONLY with JSON: "
    '{"next_stage": "<stage name>", "confidence": <0.0-1.0>, '
    '"reasoning": "<1-3 sentences; include publish|pivot|redirect explicitly>"}.'
)

_NEGATIVE_RESULT_PROMPT = (
    "Stage '{origin}' concluded hypothesis '{hypothesis_id}' is refuted.\n\n"
    "Research state:\n{context}\n\n"
    "Should the lab: (a) publish this negative result (route to "
    "'report_writing'), (b) pivot the hypothesis (route to 'plan_formulation'), "
    "or (c) redirect to collect more evidence (route to a stage of your "
    "choice)? Default fallback: '{rule_fallback}'.\n\n"
    "Respond with valid JSON only."
)

# Required context keys per ConsultKind. Passed to `.format_map(fmt_vars)` in
# consult_escalation(); missing keys are filled with "" via _SPARSE_DEFAULTS
# (see format_map call below) so an LLM never sees a KeyError, but callers
# SHOULD provide the full set for useful advice.
#
# ConsultKind.BACKTRACK_LIMIT:
#   origin: str         — the stage that requested backtrack
#   target: str         — the backtrack target the stage named
#   attempts: int       — per-edge retry count so far
#   max_attempts: int   — per-edge limit from SessionPreferences
#   rule_fallback: str  — the rule-based next stage if advisor defers
#
# ConsultKind.NEGATIVE_RESULT:
#   origin: str         — the stage concluding the negative result
#   hypothesis_id: str  — the refuted hypothesis (may be "unknown")
#   rule_fallback: str  — the rule-based next stage if advisor defers
_PROMPTS: dict[ConsultKind, tuple[str, str]] = {
    ConsultKind.BACKTRACK_LIMIT: (_BACKTRACK_LIMIT_SYSTEM, _BACKTRACK_LIMIT_PROMPT),
    ConsultKind.NEGATIVE_RESULT: (_NEGATIVE_RESULT_SYSTEM, _NEGATIVE_RESULT_PROMPT),
}


class PIAgent:
    """Advisor consulted at narrow decision checkpoints.

    `consult_escalation(checkpoint, state, context)` returns `PIAdvice`.
    When `llm_provider is None` or confidence < threshold, the advice
    defaults to `context["rule_fallback"]` and sets `used_fallback=True`.

    Every call writes to `state["pi_decisions"]` and emits a `pi_decision`
    WebSocket event. That's the sole observability channel (see module
    docstring).
    """

    def __init__(
        self,
        llm_provider: BaseLLMProvider | None = None,
        model: str | None = None,
        confidence_threshold: float | None = None,
        pi_agent_config: AgentConfig | None = None,
        event_bus: EventBus | None = None,
    ) -> None:
        self.llm_provider = llm_provider
        self.model = model
        self._event_bus = event_bus

        if confidence_threshold is not None:
            self.confidence_threshold = confidence_threshold
        elif pi_agent_config and pi_agent_config.confidence_threshold is not None:
            self.confidence_threshold = pi_agent_config.confidence_threshold
        else:
            self.confidence_threshold = 0.6

        if pi_agent_config is not None:
            self._memory_scope = pi_agent_config.memory_scope
        else:
            from agentlabx.agents.base import MemoryScope

            self._memory_scope = MemoryScope()
        self._context_assembler = ContextAssembler()

    async def consult_escalation(
        self,
        checkpoint: ConsultKind,
        state: PipelineState,
        context: dict[str, Any],
    ) -> PIAdvice:
        rule_fallback = context.get("rule_fallback")

        # Mock / no-LLM path
        if self.llm_provider is None:
            advice = PIAdvice(
                checkpoint=checkpoint,
                next_stage=rule_fallback,
                reasoning="No LLM provider; using rule-based fallback.",
                confidence=0.0,
                used_fallback=True,
            )
            return await self._finalize(advice, state)

        # LLM path
        system_prompt, prompt_template = _PROMPTS[checkpoint]
        context_dict = self._context_assembler.assemble(state, self._memory_scope)
        context_text = self._context_assembler.format_for_prompt(context_dict)

        fmt_vars: dict[str, Any] = {k: "" for k in ("origin", "target", "attempts", "max_attempts", "hypothesis_id", "rule_fallback")}
        fmt_vars.update(context)
        fmt_vars["context"] = context_text
        prompt = prompt_template.format_map(fmt_vars)

        try:
            response = await self.llm_provider.query(
                model=self.model,
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=0.1,
            )
            parsed = self._parse_decision(response.content)
            confidence = float(parsed.get("confidence", 0.5))
            proposed = parsed.get("next_stage")
            reasoning = parsed.get("reasoning", "")

            if confidence < self.confidence_threshold or not proposed:
                advice = PIAdvice(
                    checkpoint=checkpoint,
                    next_stage=rule_fallback,
                    reasoning=reasoning or "Low confidence; using rule-based fallback.",
                    confidence=confidence,
                    used_fallback=True,
                )
            else:
                advice = PIAdvice(
                    checkpoint=checkpoint,
                    next_stage=proposed,
                    reasoning=reasoning,
                    confidence=confidence,
                    used_fallback=False,
                )
        except Exception as e:
            advice = PIAdvice(
                checkpoint=checkpoint,
                next_stage=rule_fallback,
                reasoning=f"LLM error; using rule-based fallback: {e}",
                confidence=0.0,
                used_fallback=True,
            )

        return await self._finalize(advice, state)

    async def _finalize(self, advice: PIAdvice, state: PipelineState) -> PIAdvice:
        """Persist advice to state and emit event; called from every return path."""
        advice_dict = advice.model_dump(mode="json")
        advice_dict["decision_id"] = uuid.uuid4().hex
        advice_dict["ts"] = datetime.now(UTC).isoformat()
        state.setdefault("pi_decisions", []).append(advice_dict)

        if self._event_bus is not None:
            await self._event_bus.emit(
                Event(
                    type=EventTypes.PI_DECISION,
                    data=advice_dict,
                    source="pi_agent",
                )
            )
        return advice

    def _parse_decision(self, text: str) -> dict[str, Any]:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
        return {}
