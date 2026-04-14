from __future__ import annotations

from tests.harness.harness.steering import (
    ContextShape,
    HitlDirective,
    apply_context_shape,
)


def test_hitl_directive_approve():
    d = HitlDirective.approve()
    assert d.action == "approve"
    assert d.payload() == {"action": "approve"}


def test_hitl_directive_redirect_with_note():
    d = HitlDirective.redirect(target_stage="plan_formulation", reason="need deeper lit review")
    payload = d.payload()
    assert payload["action"] == "redirect"
    assert payload["target_stage"] == "plan_formulation"
    assert payload["reason"] == "need deeper lit review"


def test_apply_context_shape_sets_max_iterations():
    state = {"current_stage": "experimentation"}
    shape = ContextShape(max_stage_iterations=2)
    out = apply_context_shape(state, shape)
    assert out["max_stage_iterations"] == 2


def test_apply_context_shape_clears_prior_artifact_to_force_gate_run():
    state = {"artifacts": {"literature_review": {"summary": "..."}}}
    shape = ContextShape(clear_artifacts=["literature_review"])
    out = apply_context_shape(state, shape)
    assert "literature_review" not in out.get("artifacts", {})


def test_apply_context_shape_does_not_mutate_input():
    state = {"artifacts": {"lr": {}}, "max_stage_iterations": 5}
    shape = ContextShape(max_stage_iterations=2, clear_artifacts=["lr"])
    apply_context_shape(state, shape)
    assert state["max_stage_iterations"] == 5
    assert "lr" in state["artifacts"]
