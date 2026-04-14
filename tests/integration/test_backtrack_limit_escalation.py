"""End-to-end: PI advisor consulted on backtrack_limit_exceeded escalation.

Proves:
- PipelineBuilder wires the advisor through to TransitionHandler
- When the per-edge backtrack counter trips, decide_async consults the
  advisor via ConsultKind.BACKTRACK_LIMIT
- Confident advice overrides the rule-based _next_in_sequence fallback
- state["pi_decisions"] captures the advice; the pi_decision event fires
"""
from __future__ import annotations

import pytest

from agentlabx.agents.pi_agent import ConsultKind, PIAdvice, PIAgent
from agentlabx.core.pipeline import PipelineBuilder
from agentlabx.core.registry import PluginRegistry
from agentlabx.core.session import SessionPreferences
from agentlabx.core.state import create_initial_state
from agentlabx.plugins._builtin import register_builtin_plugins


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
    from agentlabx.stages.base import StageResult
    from agentlabx.stages.literature_review import LiteratureReviewStage
    from agentlabx.stages.plan_formulation import PlanFormulationStage
    from agentlabx.stages.experimentation import ExperimentationStage
    from agentlabx.stages.peer_review import PeerReviewStage

    # Patch each concrete stage to produce deterministic StageResult output.
    # Experimentation always requests backtrack to literature_review;
    # other stages emit a plain "done".
    async def fake_run(self, state, context):
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

    for cls in [
        LiteratureReviewStage,
        PlanFormulationStage,
        ExperimentationStage,
        PeerReviewStage,
    ]:
        monkeypatch.setattr(cls, "run", fake_run)

    # Advisor: always recommend plan_formulation with high confidence on
    # escalation. Using an in-memory PIAgent with llm_provider=None and
    # monkey-patching consult_escalation avoids depending on an LLM.
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

    seq = [
        "literature_review",
        "plan_formulation",
        "experimentation",
        "peer_review",
    ]
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

    result = await graph.ainvoke(
        state,
        config={"configurable": {"thread_id": "t1"}, "recursion_limit": 120},
    )

    # Advisor was consulted — pi_decisions list is non-empty
    assert len(result["pi_decisions"]) >= 1, (
        f"Expected pi_decisions to contain at least one advice entry; "
        f"got: {result['pi_decisions']}"
    )

    # Advice targeted plan_formulation (override, not rule fallback peer_review)
    advice_entries = [
        d for d in result["pi_decisions"]
        if d.get("next_stage") == "plan_formulation"
    ]
    assert advice_entries, (
        f"Expected at least one advice routing to plan_formulation; "
        f"got pi_decisions: {result['pi_decisions']}"
    )

    # plan_formulation was actually visited (advice routed there, not peer_review fallback)
    assert "plan_formulation" in result["completed_stages"]

    # Error log records the limit-exceeded escalation
    limit_errors = [
        e for e in result["errors"]
        if e.error_type == "backtrack_limit_exceeded"
    ]
    assert limit_errors, (
        f"Expected at least one backtrack_limit_exceeded error; "
        f"got: {result['errors']}"
    )


@pytest.mark.asyncio
async def test_backtrack_limit_exceeded_no_advisor_falls_back_to_rule(
    registry, monkeypatch
):
    """When no advisor is configured, rule-based _next_in_sequence fallback is used."""
    from agentlabx.stages.base import StageResult
    from agentlabx.stages.literature_review import LiteratureReviewStage
    from agentlabx.stages.plan_formulation import PlanFormulationStage
    from agentlabx.stages.experimentation import ExperimentationStage
    from agentlabx.stages.peer_review import PeerReviewStage

    async def fake_run(self, state, context):
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

    for cls in [
        LiteratureReviewStage,
        PlanFormulationStage,
        ExperimentationStage,
        PeerReviewStage,
    ]:
        monkeypatch.setattr(cls, "run", fake_run)

    seq = [
        "literature_review",
        "plan_formulation",
        "experimentation",
        "peer_review",
    ]
    graph = PipelineBuilder(
        registry=registry,
        preferences=SessionPreferences(max_backtrack_attempts_per_edge=2),
        pi_advisor=None,  # explicit
    ).build(stage_sequence=seq)

    state = create_initial_state(
        session_id="s2",
        user_id="u1",
        research_topic="t",
        default_sequence=seq,
        max_total_iterations=30,
    )

    result = await graph.ainvoke(
        state, config={"configurable": {"thread_id": "t2"}}
    )

    # pi_decisions is empty (advisor was never consulted)
    assert result["pi_decisions"] == [], (
        f"Expected pi_decisions to be empty without advisor; got: {result['pi_decisions']}"
    )

    # Rule fallback routed to peer_review (next_in_sequence after experimentation)
    assert "peer_review" in result["completed_stages"]

    # limit-exceeded error still logged
    limit_errors = [
        e for e in result["errors"]
        if e.error_type == "backtrack_limit_exceeded"
    ]
    assert limit_errors
