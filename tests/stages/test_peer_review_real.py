"""Tests for real blind peer review stage."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentlabx.agents.config_loader import AgentConfigLoader
from agentlabx.core.registry import PluginRegistry
from agentlabx.core.state import ReportResult, create_initial_state
from agentlabx.providers.llm.mock_provider import MockLLMProvider
from agentlabx.stages.base import StageContext
from agentlabx.stages.peer_review import PeerReviewStage

CONFIGS_DIR = Path(__file__).parent.parent.parent / "agentlabx" / "agents" / "configs"


def review_json(decision: str, overall: int = 7) -> str:
    return json.dumps(
        {
            "decision": decision,
            "scores": {"originality": 3, "quality": 3, "clarity": 3, "significance": 3},
            "overall": overall,
            "feedback": f"{decision} because reasons.",
        }
    )


@pytest.fixture()
def registry() -> PluginRegistry:
    reg = PluginRegistry()
    loader = AgentConfigLoader()
    configs = loader.load_all(CONFIGS_DIR)
    loader.register_all(configs, reg)
    return reg


@pytest.fixture()
def state_with_report():
    state = create_initial_state(session_id="s1", user_id="u1", research_topic="MATH")
    state["report"] = [
        ReportResult(
            latex_source=r"\documentclass{article}\begin{document}Test paper.\end{document}",
            sections={"Introduction": "Intro"},
            compiled_pdf_path=None,
        )
    ]
    return state


class TestPeerReviewStage:
    async def test_unanimous_accept(self, registry, state_with_report):
        provider = MockLLMProvider(
            responses=[
                review_json("accept"),
                review_json("accept"),
                review_json("accept"),
            ]
        )
        context = StageContext(
            settings={},
            event_bus=None,
            registry=registry,
            llm_provider=provider,
        )
        stage = PeerReviewStage()
        result = await stage.run(state_with_report, context)
        assert result.status == "done"
        assert len(result.output["review"]) == 3

    async def test_majority_reject(self, registry, state_with_report):
        provider = MockLLMProvider(
            responses=[
                review_json("reject"),
                review_json("reject"),
                review_json("accept"),
            ]
        )
        context = StageContext(
            settings={},
            event_bus=None,
            registry=registry,
            llm_provider=provider,
        )
        stage = PeerReviewStage()
        result = await stage.run(state_with_report, context)
        assert result.status == "backtrack"
        assert result.next_hint == "report_writing"

    async def test_split_decision_revises(self, registry, state_with_report):
        provider = MockLLMProvider(
            responses=[
                review_json("accept"),
                review_json("reject"),
                review_json("revise"),
            ]
        )
        context = StageContext(
            settings={},
            event_bus=None,
            registry=registry,
            llm_provider=provider,
        )
        stage = PeerReviewStage()
        result = await stage.run(state_with_report, context)
        assert result.status == "backtrack"

    async def test_no_report_returns_backtrack(self, registry):
        context = StageContext(
            settings={},
            event_bus=None,
            registry=registry,
            llm_provider=MockLLMProvider(responses=[]),
        )
        state = create_initial_state(session_id="s1", user_id="u1", research_topic="t")
        stage = PeerReviewStage()
        result = await stage.run(state, context)
        assert result.status == "backtrack"
        assert result.next_hint == "report_writing"

    async def test_no_registry_returns_backtrack(self):
        context = StageContext(settings={}, event_bus=None, registry=None)
        state = create_initial_state(session_id="s1", user_id="u1", research_topic="t")
        stage = PeerReviewStage()
        result = await stage.run(state, context)
        assert result.status == "backtrack"

    async def test_blind_scope_enforced(self, registry, state_with_report):
        """Reviewer prompts should not contain internal state keys."""
        provider = MockLLMProvider(
            responses=[
                review_json("accept"),
                review_json("accept"),
                review_json("accept"),
            ]
        )
        context = StageContext(
            settings={},
            event_bus=None,
            registry=registry,
            llm_provider=provider,
        )
        # Add internal state that should be hidden
        state_with_report["errors"] = []
        state_with_report["transition_log"] = []

        stage = PeerReviewStage()
        await stage.run(state_with_report, context)

        # Inspect prompts sent to reviewers — should only contain the report text
        for call in provider.calls:
            # Should not leak transition_log or errors into the prompt
            assert "transition_log" not in call["prompt"].lower()
            assert "errors" not in call["prompt"].lower()

    async def test_malformed_json_falls_back_to_revise(self, registry, state_with_report):
        provider = MockLLMProvider(
            responses=[
                "not json",
                "also not json",
                "still not json",
            ]
        )
        context = StageContext(
            settings={},
            event_bus=None,
            registry=registry,
            llm_provider=provider,
        )
        stage = PeerReviewStage()
        result = await stage.run(state_with_report, context)
        # All reviews default to "revise" on malformed JSON
        assert all(r.decision == "revise" for r in result.output["review"])

    async def test_review_feedback_field_populated(self, registry, state_with_report):
        """review_feedback key is also set in output for accumulation."""
        provider = MockLLMProvider(
            responses=[
                review_json("accept"),
                review_json("accept"),
                review_json("accept"),
            ]
        )
        context = StageContext(
            settings={},
            event_bus=None,
            registry=registry,
            llm_provider=provider,
        )
        stage = PeerReviewStage()
        result = await stage.run(state_with_report, context)
        assert "review_feedback" in result.output
        assert len(result.output["review_feedback"]) == 3

    async def test_reviewer_ids_are_unique(self, registry, state_with_report):
        provider = MockLLMProvider(
            responses=[
                review_json("accept"),
                review_json("revise"),
                review_json("reject"),
            ]
        )
        context = StageContext(
            settings={},
            event_bus=None,
            registry=registry,
            llm_provider=provider,
        )
        stage = PeerReviewStage()
        result = await stage.run(state_with_report, context)
        ids = [r.reviewer_id for r in result.output["review"]]
        assert len(ids) == len(set(ids)), "Reviewer IDs must be unique"
        assert ids == ["reviewer_1", "reviewer_2", "reviewer_3"]
