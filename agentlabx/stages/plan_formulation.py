"""Real plan formulation — postdoc + PhD dialogue produces structured plan."""

from __future__ import annotations

import json
import re

from agentlabx.core.state import Hypothesis, PipelineState, ResearchPlan
from agentlabx.stages._helpers import build_agent_context, resolve_agent
from agentlabx.stages.base import BaseStage, StageContext, StageResult, sync_agent_memory_to_state

PLAN_JSON_FORMAT = (
    '{"goals": ["goal 1", "goal 2", ...], '
    '"methodology": "2-3 sentence description", '
    '"hypotheses": ["hypothesis 1", "hypothesis 2"]}'
)


class PlanFormulationStage(BaseStage):
    name = "plan_formulation"
    description = "Postdoc and PhD student collaborate to formulate the research plan."
    required_agents = ["postdoc", "phd_student"]
    required_tools = []

    async def run(self, state: PipelineState, context: StageContext) -> StageResult:
        registry = context.registry
        if registry is None:
            return StageResult(
                output={},
                status="backtrack",
                next_hint=None,
                reason="No registry in StageContext",
            )

        postdoc = resolve_agent(
            registry,
            "postdoc",
            llm_provider=context.llm_provider,
            cost_tracker=context.cost_tracker,
            state=state,
        )
        phd = resolve_agent(
            registry,
            "phd_student",
            llm_provider=context.llm_provider,
            cost_tracker=context.cost_tracker,
            state=state,
        )

        topic = state["research_topic"]
        lit_reviews = state.get("literature_review", [])
        lit_summary = lit_reviews[-1].summary if lit_reviews else "No literature review available."

        # Step 1: Postdoc proposes initial plan in JSON
        postdoc_prompt = (
            f"Research topic: {topic}\n\n"
            f"Literature review summary:\n{lit_summary}\n\n"
            f"Propose an initial research plan. Respond ONLY with JSON of the form:\n"
            f"{PLAN_JSON_FORMAT}\n\n"
            f"No prose, no markdown."
        )
        initial_plan_text = await postdoc.inference(
            postdoc_prompt,
            build_agent_context(state, postdoc, phase="plan_formulation"),
        )

        # Step 2: PhD reviews and provides feedback (free-form)
        phd_prompt = (
            f"Topic: {topic}\n\nPostdoc's proposed plan:\n{initial_plan_text}\n\n"
            f"As the PhD student, provide 1-2 constructive suggestions "
            f"to improve the plan. Be concise."
        )
        phd_feedback = await phd.inference(
            phd_prompt,
            build_agent_context(state, phd, phase="plan_formulation"),
        )

        # Step 3: Postdoc finalizes with feedback — back to JSON
        finalize_prompt = (
            f"Initial plan:\n{initial_plan_text}\n\n"
            f"PhD feedback:\n{phd_feedback}\n\n"
            f"Incorporate the feedback and output the final plan. Respond ONLY with JSON:\n"
            f"{PLAN_JSON_FORMAT}\n\nNo prose, no markdown."
        )
        final_plan_text = await postdoc.inference(
            finalize_prompt,
            build_agent_context(state, postdoc, phase="plan_formulation"),
        )

        # Parse JSON (with fallback)
        parsed = self._parse_plan_json(final_plan_text)
        goals = parsed.get("goals", []) or ["Goal extracted from plan"]
        methodology = parsed.get("methodology", "") or "Methodology extracted from plan"
        hypothesis_statements = parsed.get("hypotheses", []) or ["Hypothesis from plan"]

        plan = ResearchPlan(
            goals=goals,
            methodology=methodology,
            hypotheses=hypothesis_statements,
            full_text=final_plan_text,
        )

        hypothesis_objects = [
            Hypothesis(
                id=f"H{i + 1}",
                statement=h,
                status="active",
                created_at_stage="plan_formulation",
            )
            for i, h in enumerate(hypothesis_statements)
        ]

        sync_agent_memory_to_state(state, {"postdoc": postdoc, "phd_student": phd})
        return StageResult(
            output={"plan": [plan], "hypotheses": hypothesis_objects},
            status="done",
            reason="Plan formulated with postdoc-PhD collaboration",
        )

    def _parse_plan_json(self, text: str) -> dict:
        """Parse JSON plan with markdown-wrapping fallback."""
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
