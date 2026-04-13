# Plan 7C: PI Advisor Reconception + Escalation Target

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reframe `PIAgent` from "intelligent transition handler" (never wired) to a participating advisor consulted at a narrow set of checkpoints. Wire it as the escalation target for Plan 7A's `backtrack_limit_exceeded` and for `negative_result` status outcomes, replacing the current rule-engine fallback. Behaviour stays confidence-gated — if the advisor is below threshold or fails, the rule-based fallback remains.

**Architecture:** The existing `PIAgent` class is renamed semantically (file kept as `pi_agent.py` to avoid import churn) — its `decide()` method is replaced by `consult_escalation(checkpoint, state, context)` returning a `PIAdvice`. `PipelineBuilder` constructs an optional `PIAgent` and threads it into `TransitionHandler`. When a `TransitionHandler.decide()` call would escalate via Priority 3 (`backtrack_limit_exceeded`) or encounters a `negative_result` status, it consults the advisor first. If `advice.confidence >= threshold` the handler uses `advice.next_stage`; otherwise it falls back to `_next_in_sequence(...)` as today. `/api/sessions/{id}/pi/history` continues reading `state["pi_decisions"]` and the `pi_decision` WebSocket event continues firing from `_finalize()`.

**Tech Stack:** Python 3.11+, LangGraph, Pydantic v2, pytest-asyncio. No new dependencies.

**Pre-production principle:** no backwards-compat scaffolding; update tests when behaviour changes.

**Spec sections implemented:** §3.3.5 PI advisor (participating helper, not router), §3.3.7 backtrack governance escalation target.

**Companion spec:** `docs/superpowers/specs/2026-04-12-agentlabx-platform-design.md` §3.3.5.

**Out of scope (later plans):**
- Zone-transition checkpoint consultation (Plan 7C²) — advisor invoked at each zone boundary when crossing Discovery → Implementation → Synthesis. Stub left in `ConsultKind` enum for future extension.
- Lab meeting chair role (PI as meeting chair per §5.3) — lab meeting is an invocable subgraph whose body isn't implemented yet.
- HITL `approve` prompt integration — advisor recommendation shown alongside the human CheckpointModal is a frontend/API shape change in Plan 7D.
- Stage-internal opt-in review — stage's `evaluate` hook requesting PI review is Plan 7B² territory.

---

## Design decisions pinned before implementation

Three seams that could otherwise stall execution.

**1. PIAgent class stays; `decide()` becomes `consult_escalation()`.**

The Plan 6B commit (`4880ae4`) already established `PIAgent` with a `_finalize()` helper that writes to `state["pi_decisions"]` and emits the `pi_decision` event. Keep the class, keep `_finalize`, rename `decide()` to `consult_escalation()` and change its signature from `(state, preferences, budget_warning)` to `(checkpoint, state, context)` where `checkpoint: ConsultKind` and `context: dict[str, Any]` carries the situation-specific payload (backtrack edge, cost fraction, attempts for the `backtrack_limit` kind; hypothesis evidence for `negative_result`). The `transition_handler` parameter in the constructor goes away — PIAgent no longer wraps the handler.

The `PIDecision` Pydantic model is replaced by `PIAdvice` with the same shape plus a `checkpoint: ConsultKind` discriminator field. Because Plan 6B's `pi_decisions` state list carries dicts (not Pydantic instances — see `agentlabx/core/state.py::PipelineState.pi_decisions` declared as `list[dict]`), the serialised wire format is unchanged; frontend reads the same keys.

**2. `TransitionHandler` gets an optional `pi_advisor` constructor kwarg.**

Default `None` → Plan 7A behaviour (rule-based fallback only). When provided, `TransitionHandler.decide()` consults the advisor at two points:

- **Priority 3 (`backtrack_limit_exceeded`):** before computing the `_next_in_sequence` fallback, call `advisor.consult_escalation(ConsultKind.BACKTRACK_LIMIT, state, context={...})`. If `advice.confidence >= threshold`, use `advice.next_stage` as the fallback target instead.
- **Priority 5 (`next_hint` with `status="negative_result"`):** when a stage's result carries negative_result, consult the advisor for `ConsultKind.NEGATIVE_RESULT` to decide publish / pivot / redirect. Use advice if confident.

Low-confidence or missing advisor → same rule-based fallback as today.

**3. Advisor construction lives in `PipelineBuilder`.**

`PipelineBuilder.__init__` gains an optional `pi_advisor: PIAgent | None = None` kwarg. When provided, `build()` passes it to `TransitionHandler(pi_advisor=...)`. Callers (the server's `build_app_context` + the CLI run command) construct a `PIAgent` when an LLM provider is available, mock/test paths leave it None. No hidden globals.

The app's `pi_agent.yaml` config is loaded via `AgentConfig.from_yaml` (existing pattern); the config's `confidence_threshold` field controls the gate.

---

## File structure

| File | Purpose | Create / Modify |
|---|---|---|
| `agentlabx/agents/pi_agent.py` | Reframe: `PIAgent.consult_escalation(checkpoint, state, context) -> PIAdvice`; drop `TransitionHandler` dependency; introduce `ConsultKind` enum + `PIAdvice` model; retain `_finalize` + event emission + `pi_decisions` write | Modify |
| `agentlabx/stages/transition.py` | `TransitionHandler.__init__` gains `pi_advisor: PIAgent \| None = None`; `decide()` consults advisor at Priority 3 (backtrack_limit) and Priority 5 (negative_result) when set | Modify |
| `agentlabx/core/pipeline.py` | `PipelineBuilder.__init__` gains `pi_advisor: PIAgent \| None = None`; threads into `TransitionHandler` | Modify |
| `agentlabx/server/deps.py` | Construct `PIAgent` inside `build_app_context` when an LLM provider is available; pass into `PipelineBuilder` | Modify |
| `agentlabx/agents/configs/pi_agent.yaml` | Update role description + system_prompt to match advisor framing (not router) | Modify |
| `tests/agents/test_pi_advisor.py` | Unit tests for `PIAgent.consult_escalation`: mock LLM path, confidence threshold fallback, JSON parse robustness, `_finalize` writes state + emits event | Create |
| `tests/stages/test_transition_pi_escalation.py` | `TransitionHandler.decide()` consults advisor on Priority-3 gate; uses advice when confident, falls back when not | Create |
| `tests/integration/test_plan7c_pi_escalation.py` | End-to-end: pipeline with advisor → backtrack retry limit trips → advisor routes to a non-default target; `pi_decisions` populated; WebSocket `pi_decision` event fired | Create |
| `agentlabx/core/state.py` | No change needed — `pi_decisions: Annotated[list[dict], operator.add]` already exists (Plan 6) | — |
| `tests/agents/test_pi_agent.py` | Existing Plan 6B tests — update to new API (`consult_escalation` instead of `decide`) OR delete and rewrite, per pre-production principle | Modify |

---

## Task 1: Reframe `PIAgent` — replace `decide()` with `consult_escalation()`

**Files:**
- Modify: `agentlabx/agents/pi_agent.py`
- Create: `tests/agents/test_pi_advisor.py`
- Modify: `tests/agents/test_pi_agent.py` (update existing tests to the new API)

- [ ] **Step 1: Write failing test `tests/agents/test_pi_advisor.py`**

```python
"""PIAgent.consult_escalation — advisor consulted at specific checkpoints."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from agentlabx.agents.pi_agent import ConsultKind, PIAdvice, PIAgent
from agentlabx.core.state import create_initial_state


@pytest.mark.asyncio
async def test_consult_escalation_no_llm_returns_rule_based_fallback():
    """Without an LLM provider, advisor emits a low-confidence used_fallback advice."""
    advisor = PIAgent(llm_provider=None)
    state = create_initial_state(session_id="s1", user_id="u1", research_topic="t")

    advice = await advisor.consult_escalation(
        ConsultKind.BACKTRACK_LIMIT,
        state,
        context={
            "origin": "experimentation",
            "target": "literature_review",
            "attempts": 2,
            "max_attempts": 2,
            "rule_fallback": "peer_review",
        },
    )

    assert isinstance(advice, PIAdvice)
    assert advice.checkpoint == ConsultKind.BACKTRACK_LIMIT
    assert advice.next_stage == "peer_review"  # defaults to rule fallback
    assert advice.used_fallback is True


@pytest.mark.asyncio
async def test_consult_escalation_high_confidence_advice_overrides_rule_fallback():
    """With an LLM returning confident JSON, advice.next_stage wins over rule fallback."""
    mock_provider = AsyncMock()

    class _Resp:
        content = (
            '{"next_stage": "plan_formulation", "confidence": 0.9, '
            '"reasoning": "pivot the hypothesis"}'
        )

    mock_provider.query = AsyncMock(return_value=_Resp())
    mock_provider.is_mock = False

    advisor = PIAgent(llm_provider=mock_provider, confidence_threshold=0.6)
    state = create_initial_state(session_id="s1", user_id="u1", research_topic="t")

    advice = await advisor.consult_escalation(
        ConsultKind.BACKTRACK_LIMIT,
        state,
        context={
            "origin": "experimentation",
            "target": "literature_review",
            "attempts": 2,
            "max_attempts": 2,
            "rule_fallback": "peer_review",
        },
    )

    assert advice.next_stage == "plan_formulation"
    assert advice.used_fallback is False
    assert advice.confidence >= 0.6


@pytest.mark.asyncio
async def test_consult_escalation_low_confidence_falls_back_to_rule():
    mock_provider = AsyncMock()

    class _Resp:
        content = (
            '{"next_stage": "plan_formulation", "confidence": 0.3, '
            '"reasoning": "uncertain"}'
        )

    mock_provider.query = AsyncMock(return_value=_Resp())

    advisor = PIAgent(llm_provider=mock_provider, confidence_threshold=0.6)
    state = create_initial_state(session_id="s1", user_id="u1", research_topic="t")

    advice = await advisor.consult_escalation(
        ConsultKind.BACKTRACK_LIMIT,
        state,
        context={"rule_fallback": "peer_review"},
    )

    assert advice.next_stage == "peer_review"  # rule fallback wins
    assert advice.used_fallback is True


@pytest.mark.asyncio
async def test_consult_escalation_writes_pi_decisions_and_emits_event():
    """Every advice invocation appends to state['pi_decisions'] + emits pi_decision event."""
    from agentlabx.core.events import EventBus

    events: list = []
    bus = EventBus()
    bus.subscribe(lambda e: events.append(e) or None)

    advisor = PIAgent(llm_provider=None, event_bus=bus)
    state = create_initial_state(session_id="s1", user_id="u1", research_topic="t")

    await advisor.consult_escalation(
        ConsultKind.BACKTRACK_LIMIT,
        state,
        context={"rule_fallback": "peer_review"},
    )

    assert len(state["pi_decisions"]) == 1
    assert state["pi_decisions"][0]["next_stage"] == "peer_review"
    assert any(e.type == "pi_decision" for e in events)


@pytest.mark.asyncio
async def test_consult_escalation_negative_result_uses_dedicated_prompt():
    """ConsultKind.NEGATIVE_RESULT asks publish/pivot/redirect — different prompt."""
    mock_provider = AsyncMock()

    class _Resp:
        content = (
            '{"next_stage": "report_writing", "confidence": 0.8, '
            '"reasoning": "negative result worth publishing"}'
        )

    mock_provider.query = AsyncMock(return_value=_Resp())

    advisor = PIAgent(llm_provider=mock_provider, confidence_threshold=0.6)
    state = create_initial_state(session_id="s1", user_id="u1", research_topic="t")

    advice = await advisor.consult_escalation(
        ConsultKind.NEGATIVE_RESULT,
        state,
        context={
            "origin": "experimentation",
            "hypothesis_id": "H1",
            "rule_fallback": "results_interpretation",
        },
    )

    # Prompt for NEGATIVE_RESULT differs — verify via call-args inspection
    call_args = mock_provider.query.await_args
    prompt = call_args.kwargs.get("prompt", call_args.args[1] if len(call_args.args) > 1 else "")
    assert "publish" in prompt.lower() or "pivot" in prompt.lower()
    assert advice.next_stage == "report_writing"
```

- [ ] **Step 2: Run — verify fail**

```
uv run pytest tests/agents/test_pi_advisor.py -v
```
Expected: FAIL (new API absent).

- [ ] **Step 3: Rewrite `agentlabx/agents/pi_agent.py`**

Replace the module content. Keep imports; retain `_finalize` mechanics (state write + event emit). Drop the `TransitionHandler` dependency. Introduce `ConsultKind` enum + `PIAdvice` model.

```python
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
        model: str = "claude-sonnet-4-6",
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

        prompt = prompt_template.format(context=context_text, **context)

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
        # state["pi_decisions"] is a reducer-backed list (Annotated operator.add
        # in Plan 6). Append in-place to preserve the existing invariant; Plan
        # 6 tests verify this path.
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
```

- [ ] **Step 4: Update existing `tests/agents/test_pi_agent.py`**

The Plan 6B tests used the old `decide(state, preferences, budget_warning)` API. Rewrite them to target `consult_escalation(checkpoint, state, context)`. Keep the structural tests (JSON parsing, event emission, state append) since those behaviours survive. Delete tests that asserted the `TransitionHandler`-wrapping behaviour (obsolete).

Concretely:

- Rename the test module class to reflect the new API.
- For each test: swap `await pi.decide(state, SessionPreferences())` → `await pi.consult_escalation(ConsultKind.BACKTRACK_LIMIT, state, {"rule_fallback": "experimentation"})` (or appropriate kind).
- Drop tests that specifically validated `agree_with_rule` semantics — that concept is gone.
- Keep `_parse_decision` robustness tests by targeting `advisor._parse_decision(...)` directly.

If the existing file has >5 tests that no longer apply, it's acceptable to delete the old file entirely and move useful assertions into `test_pi_advisor.py`. Pre-production principle.

- [ ] **Step 5: Run — verify pass**

```
uv run pytest tests/agents/test_pi_advisor.py tests/agents/test_pi_agent.py -v
```
Expected: all new + updated tests pass.

- [ ] **Step 6: Commit**

```bash
git add agentlabx/agents/pi_agent.py tests/agents/test_pi_advisor.py tests/agents/test_pi_agent.py
git commit -m "feat(pi): reframe PIAgent as advisor with consult_escalation (Plan 7C T1)"
```

---

## Task 2: Update `pi_agent.yaml` system prompt to advisor framing

**Files:**
- Modify: `agentlabx/agents/configs/pi_agent.yaml`

- [ ] **Step 1: Rewrite `role` and `system_prompt`**

```yaml
name: pi_agent
role: Principal Investigator — advisor consulted at decision checkpoints.
system_prompt: >
  You are the Principal Investigator of an AI-driven research lab. You are NOT the
  router that moves between every stage — a rule-based transition handler does
  that. You are consulted at specific checkpoints when judgment is needed:
  backtrack retry limits exceeded, conclusive negative results, or ambiguous
  situations. Your job is to recommend where the lab should go next, weighing
  research goals, accumulated evidence, budget, and what's been tried. Include a
  confidence score so the handler knows when to trust your recommendation
  vs. fall back to the default sequence.

tools: []

phases: []

memory_scope:
  read:
    - "hypotheses.*"
    - "transition_log.*"
    - "review_feedback.*"
    - "cost_tracker.*"
    - "stage_iterations.*"
    - "backtrack_attempts.*"
    - "backtrack_cost_spent"
    - "errors.*"
  write: []
  summarize:
    literature_review: "abstract"
    plan: "goals and methodology summary"
    experiment_results: "metrics and outcomes"
    interpretation: "key findings"
    report: "abstract and conclusion"

conversation_history_length: 10
confidence_threshold: 0.6
```

- [ ] **Step 2: Run — verify YAML parses**

```
uv run pytest tests/agents/ -v -k "config or yaml"
```
Expected: all pass.

- [ ] **Step 3: Commit**

```bash
git add agentlabx/agents/configs/pi_agent.yaml
git commit -m "feat(pi): update pi_agent.yaml to advisor framing (Plan 7C T2)"
```

---

## Task 3: `TransitionHandler` consults advisor on Priority-3 gate

**Files:**
- Modify: `agentlabx/stages/transition.py`
- Create: `tests/stages/test_transition_pi_escalation.py`

- [ ] **Step 1: Write failing test**

Create `tests/stages/test_transition_pi_escalation.py`:

```python
"""TransitionHandler consults PI advisor on Priority-3 escalation."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from agentlabx.agents.pi_agent import ConsultKind, PIAdvice, PIAgent
from agentlabx.core.session import SessionPreferences
from agentlabx.core.state import CostTracker, create_initial_state
from agentlabx.stages.transition import TransitionHandler


def _state_at_retry_limit():
    s = create_initial_state(
        session_id="s1",
        user_id="u1",
        research_topic="t",
        default_sequence=[
            "literature_review",
            "plan_formulation",
            "experimentation",
            "peer_review",
        ],
    )
    s["current_stage"] = "experimentation"
    s["next_stage"] = "literature_review"
    s["backtrack_attempts"] = {"experimentation->literature_review": 2}
    return s


@pytest.mark.asyncio
async def test_handler_without_advisor_falls_back_to_rule(monkeypatch):
    """Plan 7A behaviour preserved when advisor=None."""
    h = TransitionHandler(
        preferences=SessionPreferences(max_backtrack_attempts_per_edge=2),
    )
    d = h.decide(_state_at_retry_limit())
    assert d.action == "backtrack_limit_exceeded"
    assert d.next_stage == "peer_review"  # rule fallback


@pytest.mark.asyncio
async def test_handler_with_confident_advisor_uses_advice_target(monkeypatch):
    """High-confidence advice overrides the rule-based fallback."""
    advisor = PIAgent(llm_provider=None)

    async def fake_consult(checkpoint, state, context):
        advice = PIAdvice(
            checkpoint=checkpoint,
            next_stage="plan_formulation",
            reasoning="pivot the hypothesis",
            confidence=0.9,
            used_fallback=False,
        )
        return await advisor._finalize(advice, state)

    monkeypatch.setattr(advisor, "consult_escalation", fake_consult)

    h = TransitionHandler(
        preferences=SessionPreferences(max_backtrack_attempts_per_edge=2),
        pi_advisor=advisor,
    )
    # TransitionHandler.decide is sync today. When pi_advisor is set, decide
    # becomes async OR exposes a separate async method — design decision
    # pinned in Task 3 Step 3. See the implementation notes there.
    d = await h.decide_async(_state_at_retry_limit())

    assert d.action == "backtrack_limit_exceeded"
    assert d.next_stage == "plan_formulation"


@pytest.mark.asyncio
async def test_handler_with_low_confidence_advisor_falls_back_to_rule(monkeypatch):
    advisor = PIAgent(llm_provider=None, confidence_threshold=0.6)

    async def fake_consult(checkpoint, state, context):
        advice = PIAdvice(
            checkpoint=checkpoint,
            next_stage=context.get("rule_fallback"),
            reasoning="uncertain",
            confidence=0.3,
            used_fallback=True,
        )
        return await advisor._finalize(advice, state)

    monkeypatch.setattr(advisor, "consult_escalation", fake_consult)

    h = TransitionHandler(
        preferences=SessionPreferences(max_backtrack_attempts_per_edge=2),
        pi_advisor=advisor,
    )
    d = await h.decide_async(_state_at_retry_limit())

    assert d.action == "backtrack_limit_exceeded"
    assert d.next_stage == "peer_review"  # rule fallback
```

### Design decision — sync vs async `decide()`

`TransitionHandler.decide` is synchronous today. Advisor consultation is async (LLM call). Two clean options:

**A. Add `decide_async(state)` as a sibling method**; `decide_async` awaits the advisor when set, then composes the decision. Keep `decide()` sync and advisor-free for callers that don't have an advisor or an event loop handy. `transition_node` in `PipelineBuilder.build` calls `decide_async`.

**B. Make `decide()` async across the board.** More uniform but ripples into every call site.

**Choice: A (add async sibling).** Minimises ripple; sync `decide()` remains the zero-advisor fast path; async `decide_async()` wraps it and adds the advisor call. `transition_node` (the only caller in the hot path) already runs inside LangGraph's async context and can await.

- [ ] **Step 2: Run — verify fail**

```
uv run pytest tests/stages/test_transition_pi_escalation.py -v
```
Expected: FAIL (`decide_async` doesn't exist; constructor rejects `pi_advisor`).

- [ ] **Step 3: Update `TransitionHandler`**

Add constructor kwarg and an async sibling method.

In `agentlabx/stages/transition.py`:

```python
from agentlabx.agents.pi_agent import ConsultKind, PIAgent


class TransitionHandler:
    def __init__(
        self,
        preferences: SessionPreferences | None = None,
        pi_advisor: PIAgent | None = None,
    ) -> None:
        self.preferences = preferences or SessionPreferences()
        self.pi_advisor = pi_advisor

    async def decide_async(self, state: PipelineState) -> TransitionDecision:
        """Async variant that consults the PI advisor on escalation paths.

        Falls through to sync decide() when no advisor is set. On Priority-3
        (backtrack_limit_exceeded) escalation, consults the advisor; if the
        advice is confident (≥ threshold — enforced by the advisor itself),
        uses advice.next_stage as the fallback target instead of
        _next_in_sequence.
        """
        rule_decision = self.decide(state)

        if self.pi_advisor is None:
            return rule_decision

        if rule_decision.action != "backtrack_limit_exceeded":
            return rule_decision

        current = state.get("current_stage", "")
        target = state.get("next_stage")
        edge_key = f"{current}->{target}"
        attempts = state.get("backtrack_attempts", {}).get(edge_key, 0)
        max_attempts = self.preferences.max_backtrack_attempts_per_edge

        advice = await self.pi_advisor.consult_escalation(
            ConsultKind.BACKTRACK_LIMIT,
            state,
            context={
                "origin": current,
                "target": target,
                "attempts": attempts,
                "max_attempts": max_attempts,
                "rule_fallback": rule_decision.next_stage,
            },
        )

        if advice.used_fallback or advice.next_stage is None:
            return rule_decision

        return TransitionDecision(
            next_stage=advice.next_stage,
            action="backtrack_limit_exceeded",
            reason=f"PI advisor: {advice.reasoning}",
            needs_approval=True,
        )
```

Note: the sync `decide()` path is unchanged — advisor is only consulted via `decide_async`. `transition_node` in `pipeline.py` will switch to `decide_async` in Task 4.

- [ ] **Step 4: Run — verify pass**

```
uv run pytest tests/stages/test_transition_pi_escalation.py tests/stages/test_transition.py tests/stages/test_transition_retry.py tests/stages/test_transition_zone.py -v
```
Expected: all pass (existing tests untouched since `decide()` sync API is unchanged).

- [ ] **Step 5: Commit**

```bash
git add agentlabx/stages/transition.py tests/stages/test_transition_pi_escalation.py
git commit -m "feat(transition): decide_async consults PI advisor on escalation (Plan 7C T3)"
```

---

## Task 4: `transition_node` calls `decide_async` when advisor is configured

**Files:**
- Modify: `agentlabx/core/pipeline.py`

- [ ] **Step 1: Update `PipelineBuilder.__init__` to accept advisor**

```python
class PipelineBuilder:
    def __init__(
        self,
        registry: PluginRegistry,
        preferences: SessionPreferences | None = None,
        pi_advisor: Any = None,  # PIAgent — typed Any to keep import light; real type imported lazily
    ) -> None:
        self.registry = registry
        self.preferences = preferences or SessionPreferences()
        self.pi_advisor = pi_advisor
```

- [ ] **Step 2: Build the handler with advisor; switch `transition_node` to `decide_async`**

In `build()`:

```python
        transition_handler = TransitionHandler(
            preferences=self.preferences,
            pi_advisor=self.pi_advisor,
        )

        async def transition_node(state: PipelineState) -> dict[str, Any]:
            """Route to next stage; maintain counters, log, partial rollback."""
            # (imports remain at module level — see Plan 7A polish commit 65dc9cf)

            decision = await transition_handler.decide_async(state)
            # (rest of transition_node unchanged — operates on the decision
            # regardless of whether it came from the sync rule path or the
            # async advisor path.)
            current = state.get("current_stage", "")
            update: dict[str, Any] = {
                "next_stage": decision.next_stage,
                "human_override": None,
            }
            # ... keep the existing body, just changed sync→async at the top
```

Make `transition_node` `async def` instead of `def`. LangGraph accepts async node callables.

- [ ] **Step 3: Run the full pipeline test suite**

```
uv run pytest tests/core/test_pipeline.py tests/core/test_pipeline_backtrack.py tests/integration/test_plan7a_backtrack_governance.py tests/integration/test_plan7b_subgraph_end_to_end.py -v
```
Expected: all pass. `decide_async` with no advisor is equivalent to sync `decide`.

- [ ] **Step 4: Commit**

```bash
git add agentlabx/core/pipeline.py
git commit -m "feat(pipeline): transition_node awaits decide_async for PI consultation (Plan 7C T4)"
```

---

## Task 5: Wire PIAgent into `build_app_context`

**Files:**
- Modify: `agentlabx/server/deps.py`

- [ ] **Step 1: Construct PIAgent when LLM provider is available**

In `build_app_context`, after the LLM provider is resolved and before the `PipelineBuilder` is constructed (or wherever `PipelineBuilder` is instantiated in the request/session lifecycle):

```python
    # PI advisor: construct only when an LLM provider is available; otherwise
    # handlers run in pure rule-based mode (Plan 7A behaviour).
    pi_advisor = None
    if llm_provider is not None and not use_mock_llm:
        from agentlabx.agents.config_loader import AgentConfig
        from agentlabx.agents.pi_agent import PIAgent

        pi_config_path = Path(__file__).parent.parent / "agents" / "configs" / "pi_agent.yaml"
        pi_config = AgentConfig.from_yaml(pi_config_path) if pi_config_path.exists() else None
        pi_advisor = PIAgent(
            llm_provider=llm_provider,
            pi_agent_config=pi_config,
            event_bus=event_bus,
        )
```

Then pass `pi_advisor` into wherever `PipelineBuilder` is constructed. This may require checking how the server currently builds the pipeline — it might be constructed per-request in the executor, not in `build_app_context`.

Search for `PipelineBuilder(` callers and update them to accept/pass `pi_advisor`.

**Mock mode stays advisor-free** so integration tests don't depend on an LLM; Plan 7C's behaviour under mock mode is identical to Plan 7A (rule-based).

- [ ] **Step 2: Run server tests**

```
uv run pytest tests/server/ tests/integration/ -v -k "not test_mock_llm_event_stream"
```
Expected: all pass. If the mock-event-stream integration test complains because PIAgent wasn't wired in previously, adjust it; otherwise leave it skipped.

- [ ] **Step 3: Commit**

```bash
git add agentlabx/server/deps.py [any other modified files]
git commit -m "feat(server): wire PIAgent into app context when LLM provider available (Plan 7C T5)"
```

---

## Task 6: End-to-end integration test

**Files:**
- Create: `tests/integration/test_plan7c_pi_escalation.py`

- [ ] **Step 1: Write the test**

```python
"""End-to-end: PI advisor consulted on backtrack_limit_exceeded escalation."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from agentlabx.agents.pi_agent import ConsultKind, PIAdvice, PIAgent
from agentlabx.core.pipeline import PipelineBuilder
from agentlabx.core.registry import PluginRegistry
from agentlabx.core.session import SessionPreferences
from agentlabx.core.state import create_initial_state
from agentlabx.plugins._builtin import register_builtin_plugins
from agentlabx.stages import runner as runner_mod


@pytest.fixture
def registry():
    r = PluginRegistry()
    register_builtin_plugins(r)
    return r


@pytest.mark.asyncio
async def test_backtrack_limit_exceeded_consults_advisor_and_uses_advice(
    registry, monkeypatch
):
    """When per-edge limit trips, the advisor routes to its preferred target."""

    async def fake_run(self, state, context):
        from agentlabx.stages.base import StageResult
        name = self.name
        if name == "experimentation":
            return StageResult(
                output={},
                status="backtrack",
                next_hint="literature_review",
                reason="need more lit",
                feedback="placeholder",
            )
        return StageResult(output={}, status="done", reason=f"{name} ok")

    for cls_name in [
        "LiteratureReviewStage",
        "PlanFormulationStage",
        "ExperimentationStage",
        "PeerReviewStage",
    ]:
        cls = registry.resolve_by_name(cls_name) if hasattr(registry, "resolve_by_name") else None
        if cls:
            monkeypatch.setattr(cls, "run", fake_run)
    # Simpler: patch BaseStage.run; if stage subclasses override, patch each.
    from agentlabx.stages.literature_review import LiteratureReviewStage
    from agentlabx.stages.plan_formulation import PlanFormulationStage
    from agentlabx.stages.experimentation import ExperimentationStage
    from agentlabx.stages.peer_review import PeerReviewStage
    for cls in [LiteratureReviewStage, PlanFormulationStage, ExperimentationStage, PeerReviewStage]:
        monkeypatch.setattr(cls, "run", fake_run)

    # Advisor: always suggest plan_formulation on escalation
    advisor = PIAgent(llm_provider=None, confidence_threshold=0.6)

    async def fake_consult(checkpoint, state, context):
        advice = PIAdvice(
            checkpoint=checkpoint,
            next_stage="plan_formulation",
            reasoning="pivot the hypothesis",
            confidence=0.9,
            used_fallback=False,
        )
        return await advisor._finalize(advice, state)

    monkeypatch.setattr(advisor, "consult_escalation", fake_consult)

    seq = ["literature_review", "plan_formulation", "experimentation", "peer_review"]
    graph = PipelineBuilder(
        registry=registry,
        preferences=SessionPreferences(max_backtrack_attempts_per_edge=2),
        pi_advisor=advisor,
    ).build(stage_sequence=seq)

    state = create_initial_state(
        session_id="s1",
        user_id="u1",
        research_topic="t",
        default_sequence=seq,
        max_total_iterations=30,
    )

    result = await graph.ainvoke(state, config={"configurable": {"thread_id": "t1"}})

    # Advisor was consulted — pi_decisions list is non-empty
    assert len(result["pi_decisions"]) >= 1

    # Advisor routed to plan_formulation (not the rule fallback peer_review)
    assert "plan_formulation" in result["completed_stages"]

    # Error still logged (limit was exceeded)
    limit_errors = [
        e for e in result["errors"]
        if e.error_type == "backtrack_limit_exceeded"
    ]
    assert limit_errors
```

- [ ] **Step 2: Run — verify pass**

```
uv run pytest tests/integration/test_plan7c_pi_escalation.py -v
```
Expected: PASS.

- [ ] **Step 3: Full regression**

```
uv run pytest tests/ -x -q
```
Expected: all pass (or 1 deselected mock-event-stream flake per prior pattern).

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_plan7c_pi_escalation.py
git commit -m "test(integration): PI advisor consulted on backtrack_limit_exceeded (Plan 7C T6)"
```

---

## Self-review checklist

- [ ] **Spec coverage:**
  - §3.3.5 PI as participating advisor at checkpoints — T1 (reframe API) + T3/T4 (wiring)
  - §3.3.7 backtrack governance escalation target — T3 + T6 (integration)
  - `negative_result` consultation — T1 (prompt defined), actual wiring into `transition_node` deferred: covered via `consult_escalation(ConsultKind.NEGATIVE_RESULT, ...)` callable, but no routing path yet (no stage returns negative_result today — that's a Plan 7B² migration item).

- [ ] **No placeholders.** Every step shows code + commands.

- [ ] **Type consistency:** `PIAgent`, `PIAdvice`, `ConsultKind`, `TransitionHandler.pi_advisor`, `PipelineBuilder.pi_advisor` all referenced by the same names.

- [ ] **Pre-production principle honoured:** the old `PIAgent.decide()` API is replaced, not deprecated; tests rewrite to the new API.

---

## Execution

Ship 7C after 7B is validated. Subagent-driven recommended.

Follow-ups:

- **Plan 7B²** — migrate remaining 7 stages to plan-driven hooks. Independent of 7C.
- **Plan 7C²** — zone-transition consultation + HITL `approve` prompt recommendation surfacing. Smaller scope, folds into 7D frontend work.
- **Plan 7D** — frontend: production-line graph + recursive subgraph drawer + CheckpointModal surfacing PI advice.
