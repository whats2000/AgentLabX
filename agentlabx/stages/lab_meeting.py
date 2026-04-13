from __future__ import annotations

from agentlabx.core.state import PipelineState
from agentlabx.stages.base import BaseStage, StageContext, StageResult


class LabMeetingTrigger:
    def __init__(self, consecutive_failures: int = 3, score_plateau_rounds: int = 2) -> None:
        self.consecutive_failures = consecutive_failures
        self.score_plateau_rounds = score_plateau_rounds

    def should_trigger(self, state: PipelineState) -> bool:
        errors = state.get("errors", [])
        if len(errors) >= self.consecutive_failures:
            recent = errors[-self.consecutive_failures :]
            if all(e.stage == recent[0].stage for e in recent):
                return True
        return False


class LabMeeting(BaseStage):
    name = "lab_meeting"
    zone = None
    invocable_only = True
    description = "Cross-zone collaboration meeting when a stage is stuck"
    required_agents = []
    required_tools = []

    async def run(self, state: PipelineState, context: StageContext) -> StageResult:
        current_stage = state.get("current_stage", "unknown")
        topic = state.get("research_topic", "the research")

        return StageResult(
            output={
                "action_items": [
                    f"Review approach for {current_stage}",
                    "Consider alternative methodology",
                    "Check if data quality is sufficient",
                ],
                "discussion_summary": (
                    f"Lab meeting held to discuss challenges in {current_stage} "
                    f"for '{topic}'. Team suggested reviewing approach and "
                    f"considering alternatives."
                ),
                "participants": ["pi_agent", "postdoc", "phd_student", "ml_engineer"],
            },
            status="done",
            reason=f"Lab meeting complete — 3 action items for {current_stage}",
        )
