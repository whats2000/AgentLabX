from __future__ import annotations

from datetime import UTC, datetime

import pytest

from agentlabx.core.state import (
    CostTracker,
    CrossStageRequest,
    EvidenceLink,
    ExperimentResult,
    Hypothesis,
    ReproducibilityRecord,
    Transition,
    create_initial_state,
)


class TestHypothesis:
    def test_create_active_hypothesis(self):
        h = Hypothesis(
            id="H1",
            statement="CoT improves MATH accuracy by >5%",
            status="active",
            created_at_stage="plan_formulation",
        )
        assert h.status == "active"
        assert h.evidence_for == []
        assert h.evidence_against == []
        assert h.parent_hypothesis is None
        assert h.resolved_at_stage is None

    def test_add_evidence(self):
        link = EvidenceLink(
            experiment_result_index=0,
            metric="accuracy",
            value=0.782,
            interpretation="Accuracy improved by 4.8%, supporting H1",
        )
        h = Hypothesis(
            id="H1",
            statement="CoT improves accuracy",
            status="supported",
            evidence_for=[link],
            created_at_stage="plan_formulation",
            resolved_at_stage="results_interpretation",
        )
        assert len(h.evidence_for) == 1
        assert h.evidence_for[0].value == 0.782


class TestReproducibilityRecord:
    def test_create_record(self):
        rec = ReproducibilityRecord(
            random_seed=42,
            environment_hash="abc123",
            run_command="python train.py --seed 42",
            timestamp=datetime(2026, 4, 12, tzinfo=UTC),
        )
        assert rec.random_seed == 42
        assert rec.container_image is None
        assert rec.git_ref is None


class TestExperimentResult:
    def test_create_with_tag(self):
        rec = ReproducibilityRecord(
            random_seed=42,
            environment_hash="abc123",
            run_command="python train.py",
            timestamp=datetime(2026, 4, 12, tzinfo=UTC),
        )
        result = ExperimentResult(
            tag="baseline",
            metrics={"accuracy": 0.75},
            description="Baseline run without CoT",
            reproducibility=rec,
        )
        assert result.tag == "baseline"
        assert result.metrics["accuracy"] == 0.75


class TestCrossStageRequest:
    def test_create_request(self):
        req = CrossStageRequest(
            from_stage="report_writing",
            to_stage="experimentation",
            request_type="experiment",
            description="Need ablation study removing CoT component",
            status="pending",
        )
        assert req.status == "pending"
        assert req.from_stage == "report_writing"


class TestCostTracker:
    def test_initial_cost(self):
        ct = CostTracker()
        assert ct.total_tokens_in == 0
        assert ct.total_tokens_out == 0
        assert ct.total_cost == 0.0

    def test_add_usage(self):
        ct = CostTracker()
        ct.add_usage(tokens_in=1000, tokens_out=500, cost=0.05)
        assert ct.total_tokens_in == 1000
        assert ct.total_tokens_out == 500
        assert ct.total_cost == 0.05
        ct.add_usage(tokens_in=200, tokens_out=100, cost=0.01)
        assert ct.total_tokens_in == 1200
        assert ct.total_cost == pytest.approx(0.06)


class TestTransition:
    def test_create_transition(self):
        t = Transition(
            from_stage="experimentation",
            to_stage="data_preparation",
            reason="Dataset quality issues found",
            triggered_by="agent",
            timestamp=datetime(2026, 4, 12, tzinfo=UTC),
        )
        assert t.triggered_by == "agent"


class TestCreateInitialState:
    def test_creates_valid_state(self):
        state = create_initial_state(
            session_id="sess-001",
            user_id="default",
            research_topic="MATH benchmark improvement",
        )
        assert state["session_id"] == "sess-001"
        assert state["user_id"] == "default"
        assert state["research_topic"] == "MATH benchmark improvement"
        assert state["hypotheses"] == []
        assert state["literature_review"] == []
        assert state["experiment_results"] == []
        assert state["current_stage"] == ""
        assert state["total_iterations"] == 0
        assert state["pending_requests"] == []
        assert state["completed_requests"] == []
        assert state["transition_log"] == []

    def test_state_has_all_stage_output_keys(self):
        state = create_initial_state(session_id="s1", user_id="u1", research_topic="test")
        for key in [
            "literature_review",
            "plan",
            "data_exploration",
            "dataset_code",
            "experiment_results",
            "interpretation",
            "report",
            "review",
        ]:
            assert key in state, f"Missing state key: {key}"
            assert state[key] == []


class TestActiveHypotheses:
    def test_returns_latest_by_id(self):
        from agentlabx.core.state import Hypothesis, active_hypotheses

        h1_old = Hypothesis(
            id="H1",
            statement="old statement",
            status="active",
            created_at_stage="plan_formulation",
        )
        h1_new = Hypothesis(
            id="H1",
            statement="old statement",
            status="supported",
            created_at_stage="plan_formulation",
            resolved_at_stage="results_interpretation",
        )
        h2 = Hypothesis(
            id="H2",
            statement="second",
            status="active",
            created_at_stage="plan_formulation",
        )
        result = active_hypotheses([h1_old, h2, h1_new])
        # H1 should appear once with the updated status
        by_id = {h.id: h for h in result}
        assert by_id["H1"].status == "supported"
        assert by_id["H2"].status == "active"
        assert len(result) == 2

    def test_empty_list(self):
        from agentlabx.core.state import active_hypotheses

        assert active_hypotheses([]) == []

    def test_preserves_order_of_first_occurrence(self):
        """Order in output follows first-occurrence order of IDs."""
        from agentlabx.core.state import Hypothesis, active_hypotheses

        ha = Hypothesis(id="A", statement="a", status="active", created_at_stage="s")
        hb = Hypothesis(id="B", statement="b", status="active", created_at_stage="s")
        ha2 = Hypothesis(id="A", statement="a", status="supported", created_at_stage="s")
        result = active_hypotheses([ha, hb, ha2])
        assert [h.id for h in result] == ["A", "B"]
        assert result[0].status == "supported"
