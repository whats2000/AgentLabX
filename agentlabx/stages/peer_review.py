"""Real peer review stage — 3 blind reviewers, majority decision."""

from __future__ import annotations

import json
import re

from agentlabx.agents.base import AgentContext, MemoryScope
from agentlabx.agents.config_agent import ConfigAgent
from agentlabx.agents.context import ContextAssembler
from agentlabx.core.registry import PluginType
from agentlabx.core.state import PipelineState, ReviewResult
from agentlabx.stages.base import BaseStage, StageContext, StageResult

REVIEW_JSON_FORMAT = (
    '{"decision": "accept" | "revise" | "reject", '
    '"scores": {"originality": 1-4, "quality": 1-4, "clarity": 1-4, "significance": 1-4}, '
    '"overall": 1-10, "feedback": "2-3 sentences"}'
)


class PeerReviewStage(BaseStage):
    name = "peer_review"
    zone = "synthesis"
    description = "Blind peer review — 3 reviewers see only the final report."
    required_agents = ["reviewers"]
    required_tools = []

    NUM_REVIEWERS = 3

    async def run(self, state: PipelineState, context: StageContext) -> StageResult:
        registry = context.registry
        if registry is None:
            return StageResult(
                output={},
                status="backtrack",
                next_hint=None,
                reason="No registry in StageContext",
            )

        reports = state.get("report", [])
        if not reports:
            return StageResult(
                output={},
                status="backtrack",
                next_hint="report_writing",
                reason="No report to review",
            )
        latest_report = reports[-1]

        # Resolve reviewer template from registry (AgentConfig instance).
        # NOTE: reviewers deliberately skip agent_memory hydration/write-back.
        # Blind peer review (spec §4.1, §8.2) requires fresh instances per
        # session — carrying scratchpad notes across reviews would leak prior
        # opinions and break the "see only the final report" invariant.
        reviewer_entry = registry.resolve(PluginType.AGENT, "reviewers")

        # Strict blind scope — reviewers see ONLY the final report
        blind_scope = MemoryScope(read=["report"])
        assembler = ContextAssembler()

        reviews: list[ReviewResult] = []
        for i in range(self.NUM_REVIEWERS):
            # Create a fresh reviewer instance per reviewer (no shared history)
            reviewer_name = f"reviewer_{i + 1}"
            if hasattr(reviewer_entry, "system_prompt"):
                # AgentConfig path
                reviewer = ConfigAgent(
                    name=reviewer_name,
                    role=reviewer_entry.role,
                    system_prompt=reviewer_entry.system_prompt,
                    tools=[],
                    memory_scope=blind_scope,
                    max_history_length=reviewer_entry.conversation_history_length,
                    llm_provider=context.llm_provider,
                    cost_tracker=context.cost_tracker,
                )
            else:
                # Fallback for class-based registration
                reviewer = reviewer_entry()

            blind_context_dict = assembler.assemble(state, blind_scope)
            ctx = AgentContext(
                phase="peer_review",
                state=blind_context_dict,
                working_memory={},
            )

            review_prompt = self._build_review_prompt(latest_report.latex_source, i)
            review_text = await reviewer.inference(review_prompt, ctx)

            reviews.append(self._parse_review(review_text, reviewer_name))

        # Majority vote
        decisions = [r.decision for r in reviews]
        if decisions.count("accept") >= 2:
            overall = "accept"
        elif decisions.count("reject") >= 2:
            overall = "reject"
        else:
            overall = "revise"

        aggregated_feedback = "\n\n".join(f"[{r.reviewer_id}] {r.feedback}" for r in reviews)

        return StageResult(
            output={"review": reviews, "review_feedback": reviews},
            status="done" if overall == "accept" else "backtrack",
            next_hint=None if overall == "accept" else "report_writing",
            reason=f"Peer review complete: {overall} ({decisions})",
            feedback=None if overall == "accept" else aggregated_feedback,
        )

    def _build_review_prompt(self, latex_source: str, reviewer_idx: int) -> str:
        focus_areas = [
            "experimental rigor",
            "impact and significance",
            "novelty and originality",
        ]
        focus = focus_areas[reviewer_idx % len(focus_areas)]
        return (
            f"You are an anonymous peer reviewer focused on {focus}.\n\n"
            f"Paper to review:\n{latex_source[:5000]}\n\n"
            f"Respond ONLY with JSON:\n{REVIEW_JSON_FORMAT}\n\nNo prose outside the JSON."
        )

    def _parse_review(self, text: str, reviewer_id: str) -> ReviewResult:
        parsed = self._parse_json(text)

        decision = parsed.get("decision", "revise")
        if decision not in ("accept", "revise", "reject"):
            decision = "revise"

        scores_raw = parsed.get("scores", {})
        scores: dict[str, float] = {}
        for metric in ("originality", "quality", "clarity", "significance"):
            try:
                scores[metric] = float(scores_raw.get(metric, 2.0))
            except (TypeError, ValueError):
                scores[metric] = 2.0
        try:
            scores["overall"] = float(parsed.get("overall", 5.0))
        except (TypeError, ValueError):
            scores["overall"] = 5.0

        feedback = parsed.get("feedback") or text[:300]

        return ReviewResult(
            decision=decision,
            scores=scores,
            feedback=feedback,
            reviewer_id=reviewer_id,
        )

    def _parse_json(self, text: str) -> dict:
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
