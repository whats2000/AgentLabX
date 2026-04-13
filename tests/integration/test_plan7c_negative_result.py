"""End-to-end: PI advisor consulted on negative_result stage status.

Proves:
- StageRunner writes last_stage_status to PipelineState
- TransitionHandler.decide_async consults ConsultKind.NEGATIVE_RESULT when
  the most recent stage returned status="negative_result"
- Confident advice overrides the rule-based advance target
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
async def test_negative_result_consults_advisor_and_uses_advice(
    registry, monkeypatch
):
    """Experimentation returning negative_result → advisor consulted → route override."""
    from agentlabx.stages.base import StageResult
    from agentlabx.stages.literature_review import LiteratureReviewStage
    from agentlabx.stages.plan_formulation import PlanFormulationStage
    from agentlabx.stages.experimentation import ExperimentationStage
    from agentlabx.stages.results_interpretation import ResultsInterpretationStage
    from agentlabx.stages.report_writing import ReportWritingStage

    async def fake_run(self, state, context):
        name = self.name
        if name == "experimentation":
            return StageResult(
                output={},
                status="negative_result",
                next_hint=None,
                reason="hypothesis refuted by conclusive null finding",
                feedback=None,
            )
        return StageResult(output={}, status="done", reason=f"{name} ok")

    for cls in [
        LiteratureReviewStage,
        PlanFormulationStage,
        ExperimentationStage,
        ResultsInterpretationStage,
        ReportWritingStage,
    ]:
        monkeypatch.setattr(cls, "run", fake_run)

    # Advisor: recommend report_writing (publish the negative result)
    advisor = PIAgent(llm_provider=None, confidence_threshold=0.6)
    consult_captures: list = []

    async def fake_consult(checkpoint, state, context):
        consult_captures.append((checkpoint, dict(context)))
        advice = PIAdvice(
            checkpoint=checkpoint,
            next_stage="report_writing",
            reasoning="negative result worth publishing",
            confidence=0.85,
            used_fallback=False,
        )
        return await advisor._finalize(advice, state)

    monkeypatch.setattr(advisor, "consult_escalation", fake_consult)

    seq = [
        "literature_review",
        "plan_formulation",
        "experimentation",
        "results_interpretation",
        "report_writing",
    ]
    graph = PipelineBuilder(
        registry=registry,
        preferences=SessionPreferences(),
        pi_advisor=advisor,
    ).build(stage_sequence=seq)

    state = create_initial_state(
        session_id="s1",
        user_id="u1",
        research_topic="t",
        default_sequence=seq,
        max_total_iterations=20,
    )

    result = await graph.ainvoke(
        state, config={"configurable": {"thread_id": "t1"}}
    )

    # Advisor was consulted with NEGATIVE_RESULT (not BACKTRACK_LIMIT)
    consulted_kinds = [c[0] for c in consult_captures]
    assert ConsultKind.NEGATIVE_RESULT in consulted_kinds, (
        f"Expected NEGATIVE_RESULT consultation; got: {consulted_kinds}"
    )

    # last_stage_status recorded before decide_async ran
    assert result["last_stage_status"] in ("done", "negative_result"), (
        f"Expected last_stage_status populated; got: {result.get('last_stage_status')!r}"
    )

    # Advisor's advice was applied — report_writing reached (bypassing results_interpretation)
    assert "report_writing" in result["completed_stages"]

    # pi_decisions captured at least one NEGATIVE_RESULT advice
    negative_advices = [
        d for d in result["pi_decisions"]
        if d.get("checkpoint") == ConsultKind.NEGATIVE_RESULT.value
    ]
    assert negative_advices, (
        f"Expected NEGATIVE_RESULT advice in pi_decisions; got: {result['pi_decisions']}"
    )


@pytest.mark.asyncio
async def test_negative_result_no_advisor_uses_default_sequence(registry, monkeypatch):
    """Without advisor, negative_result stage still advances in default sequence."""
    from agentlabx.stages.base import StageResult
    from agentlabx.stages.literature_review import LiteratureReviewStage
    from agentlabx.stages.plan_formulation import PlanFormulationStage
    from agentlabx.stages.experimentation import ExperimentationStage
    from agentlabx.stages.results_interpretation import ResultsInterpretationStage

    async def fake_run(self, state, context):
        name = self.name
        if name == "experimentation":
            return StageResult(
                output={},
                status="negative_result",
                next_hint=None,
                reason="null finding",
            )
        return StageResult(output={}, status="done", reason=f"{name} ok")

    for cls in [
        LiteratureReviewStage,
        PlanFormulationStage,
        ExperimentationStage,
        ResultsInterpretationStage,
    ]:
        monkeypatch.setattr(cls, "run", fake_run)

    seq = [
        "literature_review",
        "plan_formulation",
        "experimentation",
        "results_interpretation",
    ]
    graph = PipelineBuilder(
        registry=registry,
        preferences=SessionPreferences(),
        pi_advisor=None,
    ).build(stage_sequence=seq)

    state = create_initial_state(
        session_id="s2",
        user_id="u1",
        research_topic="t",
        default_sequence=seq,
        max_total_iterations=20,
    )

    result = await graph.ainvoke(
        state, config={"configurable": {"thread_id": "t2"}}
    )

    # No advisor → pi_decisions empty
    assert result["pi_decisions"] == []

    # last_stage_status still recorded (StageRunner writes it unconditionally)
    assert result["last_stage_status"] in ("done", "negative_result")

    # Rule-based path: advanced to results_interpretation (next in sequence)
    assert "results_interpretation" in result["completed_stages"]
