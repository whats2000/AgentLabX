"""Tests for real plan formulation stage."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentlabx.agents.config_loader import AgentConfigLoader
from agentlabx.core.registry import PluginRegistry
from agentlabx.core.state import LitReviewResult, create_initial_state
from agentlabx.providers.llm.mock_provider import MockLLMProvider
from agentlabx.stages.base import StageContext
from agentlabx.stages.plan_formulation import PlanFormulationStage

CONFIGS_DIR = Path(__file__).parent.parent.parent / "agentlabx" / "agents" / "configs"


def valid_plan_json(goals=None, hypotheses=None) -> str:
    return json.dumps(
        {
            "goals": goals or ["Investigate CoT on benchmarks", "Establish baseline"],
            "methodology": "We will run systematic ablation studies.",
            "hypotheses": hypotheses or ["CoT improves accuracy on MATH", "Token count matters"],
        }
    )


@pytest.fixture()
def registry() -> PluginRegistry:
    reg = PluginRegistry()
    loader = AgentConfigLoader()
    configs = loader.load_all(CONFIGS_DIR)
    loader.register_all(configs, reg)
    return reg


class TestPlanFormulationStage:
    async def test_runs_end_to_end(self, registry):
        provider = MockLLMProvider(
            responses=[
                valid_plan_json(),  # postdoc initial proposal
                "Consider adding ablation study for temperature.",  # phd feedback
                valid_plan_json(  # postdoc finalized plan
                    goals=[
                        "Investigate CoT on benchmarks",
                        "Establish baseline",
                        "Ablation on temp",
                    ],
                    hypotheses=["CoT improves accuracy", "Lower temperature helps"],
                ),
            ]
        )
        context = StageContext(
            settings={},
            event_bus=None,
            registry=registry,
            llm_provider=provider,
        )
        state = create_initial_state(
            session_id="s1",
            user_id="u1",
            research_topic="Chain of thought in LLMs",
        )

        stage = PlanFormulationStage()
        result = await stage.run(state, context)

        assert result.status == "done"
        assert "plan" in result.output
        assert "hypotheses" in result.output
        plan = result.output["plan"][0]
        assert len(plan.goals) >= 2
        assert "Ablation" in " ".join(plan.goals)
        hyps = result.output["hypotheses"]
        assert len(hyps) == 2
        assert all(h.status == "active" for h in hyps)
        assert all(h.created_at_stage == "plan_formulation" for h in hyps)

    async def test_parses_markdown_wrapped_json(self, registry):
        wrapped = "```json\n" + valid_plan_json() + "\n```"
        provider = MockLLMProvider(
            responses=[
                wrapped,
                "Feedback: looks good.",
                wrapped,
            ]
        )
        context = StageContext(
            settings={},
            event_bus=None,
            registry=registry,
            llm_provider=provider,
        )
        state = create_initial_state(session_id="s1", user_id="u1", research_topic="test")

        stage = PlanFormulationStage()
        result = await stage.run(state, context)

        assert result.status == "done"
        plan = result.output["plan"][0]
        assert len(plan.goals) >= 1

    async def test_creates_hypothesis_objects_from_plan(self, registry):
        provider = MockLLMProvider(
            responses=[
                valid_plan_json(
                    hypotheses=["H1: CoT helps", "H2: Scale matters", "H3: Data quality"]
                ),
                "Good plan.",
                valid_plan_json(
                    hypotheses=["H1: CoT helps", "H2: Scale matters", "H3: Data quality"]
                ),
            ]
        )
        context = StageContext(
            settings={},
            event_bus=None,
            registry=registry,
            llm_provider=provider,
        )
        state = create_initial_state(session_id="s1", user_id="u1", research_topic="test")

        stage = PlanFormulationStage()
        result = await stage.run(state, context)

        hyps = result.output["hypotheses"]
        assert len(hyps) == 3
        assert [h.id for h in hyps] == ["H1", "H2", "H3"]

    async def test_no_registry_returns_backtrack(self):
        context = StageContext(settings={}, event_bus=None, registry=None)
        state = create_initial_state(session_id="s1", user_id="u1", research_topic="test")
        stage = PlanFormulationStage()
        result = await stage.run(state, context)
        assert result.status == "backtrack"

    async def test_fallback_on_bad_json(self, registry):
        """All JSON malformed — stage should still return done with defaults."""
        provider = MockLLMProvider(
            responses=[
                "not json at all",
                "feedback here",
                "also not json",
            ]
        )
        context = StageContext(
            settings={},
            event_bus=None,
            registry=registry,
            llm_provider=provider,
        )
        state = create_initial_state(session_id="s1", user_id="u1", research_topic="test")

        stage = PlanFormulationStage()
        result = await stage.run(state, context)

        assert result.status == "done"
        plan = result.output["plan"][0]
        assert len(plan.goals) >= 1
        assert plan.methodology != ""
        hyps = result.output["hypotheses"]
        assert len(hyps) >= 1

    async def test_uses_lit_review_summary(self, registry):
        """When a literature review is present in state, it is passed to the postdoc."""
        provider = MockLLMProvider(
            responses=[
                valid_plan_json(),
                "OK",
                valid_plan_json(),
            ]
        )
        context = StageContext(
            settings={},
            event_bus=None,
            registry=registry,
            llm_provider=provider,
        )
        state = create_initial_state(session_id="s1", user_id="u1", research_topic="test")
        state["literature_review"] = [
            LitReviewResult(papers=[], summary="Key theme: scaling laws.")
        ]

        stage = PlanFormulationStage()
        await stage.run(state, context)

        # The first call should contain the lit review summary
        first_prompt = provider.calls[0]["prompt"]
        assert "scaling laws" in first_prompt

    def test_parse_plan_json_direct_json(self):
        stage = PlanFormulationStage()
        text = valid_plan_json()
        parsed = stage._parse_plan_json(text)
        assert "goals" in parsed
        assert "methodology" in parsed
        assert "hypotheses" in parsed

    def test_parse_plan_json_extracts_from_prose(self):
        stage = PlanFormulationStage()
        payload = valid_plan_json()
        text = f"Here is the plan:\n{payload}\nEnd of plan."
        parsed = stage._parse_plan_json(text)
        assert "goals" in parsed

    def test_parse_plan_json_returns_empty_on_garbage(self):
        stage = PlanFormulationStage()
        parsed = stage._parse_plan_json("totally not json")
        assert parsed == {}
