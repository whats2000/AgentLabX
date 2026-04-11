"""Tests for ContextAssembler — filters PipelineState by MemoryScope."""

from __future__ import annotations

from datetime import datetime

import pytest

from agentlabx.agents.base import MemoryScope
from agentlabx.agents.context import ContextAssembler
from agentlabx.core.state import (
    CostTracker,
    LitReviewResult,
    ResearchPlan,
)


@pytest.fixture
def populated_state() -> dict:
    """A minimal populated pipeline state dict for testing."""
    lit_review = LitReviewResult(
        papers=[{"title": "A paper", "abstract": "Abstract text"}],
        summary="Key findings from literature",
    )
    plan = ResearchPlan(
        goals=["Goal 1", "Goal 2"],
        methodology="Experimental methodology",
        hypotheses=["H1: something will happen"],
        full_text="Full research plan text",
    )
    return {
        "session_id": "sess-001",
        "user_id": "user-001",
        "research_topic": "Neural scaling laws",
        "hypotheses": [],
        "literature_review": [lit_review],
        "plan": [plan],
        "data_exploration": [],
        "dataset_code": [],
        "experiment_results": [],
        "interpretation": [],
        "report": [],
        "review": [],
        "pending_requests": [],
        "completed_requests": [],
        "current_stage": "plan_formulation",
        "stage_config": {"max_iterations": 3},
        "next_stage": None,
        "human_override": None,
        "default_sequence": ["literature_review", "plan_formulation"],
        "completed_stages": ["literature_review"],
        "stage_iterations": {"literature_review": 1},
        "total_iterations": 1,
        "max_stage_iterations": {},
        "max_total_iterations": 50,
        "transition_log": [],
        "review_feedback": [],
        "messages": [],
        "errors": [],
        "cost_tracker": CostTracker(),
    }


class TestContextAssembler:
    def setup_method(self):
        self.assembler = ContextAssembler()

    def test_filter_by_read_scope(self, populated_state):
        scope = MemoryScope(
            read=["literature_review.*", "plan.*"],
            write=["interpretation"],
        )
        context = self.assembler.assemble(populated_state, scope)
        # Should include always-visible keys
        assert "research_topic" in context
        assert "current_stage" in context
        # Should include stage outputs matching read scope
        assert "literature_review" in context
        assert "plan" in context
        # Should NOT include keys not in read scope
        assert "experiment_results" not in context
        assert "report" not in context
        # Should NOT include internal keys
        assert "session_id" not in context
        assert "user_id" not in context
        assert "stage_config" not in context

    def test_wildcard_read_all(self, populated_state):
        scope = MemoryScope(read=["*"], write=[])
        context = self.assembler.assemble(populated_state, scope)
        # All stage output keys should be present
        assert "literature_review" in context
        assert "plan" in context
        assert "experiment_results" in context
        assert "report" in context
        # Internal keys still excluded
        assert "session_id" not in context
        assert "stage_config" not in context

    def test_empty_scope_returns_minimal(self, populated_state):
        scope = MemoryScope(read=[], write=[], summarize={})
        context = self.assembler.assemble(populated_state, scope)
        # Only always-visible keys
        assert "research_topic" in context
        assert "hypotheses" in context
        assert "current_stage" in context
        # No stage-specific data
        assert "literature_review" not in context
        assert "plan" not in context

    def test_summarize_scope_marks_as_summary(self, populated_state):
        scope = MemoryScope(
            read=[],
            write=[],
            summarize={"literature_review": "abstracts and key findings"},
        )
        context = self.assembler.assemble(populated_state, scope)
        # Summarized field should be present and marked
        assert "literature_review" in context
        assert context["literature_review"].get("_summarized") is True
        assert context["literature_review"].get("summary_instruction") == "abstracts and key findings"

    def test_format_for_prompt(self, populated_state):
        scope = MemoryScope(read=["literature_review.*", "plan.*"], write=[])
        context = self.assembler.assemble(populated_state, scope)
        formatted = self.assembler.format_for_prompt(context)
        assert isinstance(formatted, str)
        assert "Neural scaling laws" in formatted
        assert len(formatted) > 0
