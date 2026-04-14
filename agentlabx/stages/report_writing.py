"""Real report writing stage — professor + PhD student outline, draft, polish.

Plan 7E B3 migration: build_plan itemises one item per report section with per-section
prior-bypass logic; execute_plan stays at default (delegates to legacy .run()), so plan
items are OBSERVABILITY-ONLY in 7E.
"""

from __future__ import annotations

import re

from agentlabx.core.state import PipelineState, ReportResult, StagePlan, StagePlanItem
from agentlabx.stages._helpers import build_agent_context, resolve_agent
from agentlabx.stages.base import BaseStage, StageContext, StageResult, sync_agent_memory_to_state

_SECTIONS = [
    ("abstract", "Write abstract"),
    ("introduction", "Write introduction"),
    ("methodology", "Write methodology section"),
    ("results", "Write results section"),
    ("discussion", "Write discussion"),
    ("conclusion", "Write conclusion"),
]


class ReportWritingStage(BaseStage):
    """Plan 7E B3 migration: build_plan itemises report sections with per-section
    prior-bypass; execute_plan stays at the default (delegates to legacy .run()),
    so plan items are OBSERVABILITY-ONLY in 7E.
    """

    name = "report_writing"
    zone = "synthesis"
    description = "Professor and PhD student write the research paper in LaTeX."
    required_agents = ["professor", "phd_student"]
    required_tools = []

    def build_plan(
        self, state: PipelineState, *, feedback: str | None = None
    ) -> StagePlan:
        """Itemise report sections with per-section prior-bypass.

        For each of the six canonical sections: if the section key (normalised
        lowercase) is present in state["report"][-1].sections AND no feedback is
        given, the corresponding item is marked done referencing the existing
        artifact. This encodes "don't rewrite a section you already have."
        """
        prior_sections: set[str] = set()
        prior_report = state.get("report", [])
        if prior_report and not feedback:
            latest = prior_report[-1]
            sections = getattr(latest, "sections", None) or (
                latest.get("sections") if isinstance(latest, dict) else None
            ) or {}
            prior_sections = {k.lower() for k in sections.keys()}

        items: list[StagePlanItem] = []
        for key, desc in _SECTIONS:
            if key in prior_sections:
                items.append(StagePlanItem(
                    id=f"report:{key}",
                    description=desc,
                    status="done",
                    source="prior",
                    existing_artifact_ref=f"report[-1].sections[{key}]",
                    edit_note=None,
                    removed_reason=None,
                ))
            else:
                items.append(StagePlanItem(
                    id=f"report:{key}",
                    description=desc,
                    status="todo",
                    source="contract",
                    existing_artifact_ref=None,
                    edit_note=None,
                    removed_reason=None,
                ))

        if feedback:
            items.append(StagePlanItem(
                id="report:feedback-driven",
                description=f"Revise per feedback: {feedback}",
                status="todo",
                source="feedback",
                existing_artifact_ref=None,
                edit_note=None,
                removed_reason=None,
            ))

        rationale = "Report writing plan"
        if feedback:
            rationale += " (revising under feedback)"
        elif prior_sections:
            rationale += f" ({len(prior_sections)} of 6 sections already drafted)"

        return StagePlan(
            items=items,
            rationale=rationale,
            hash_of_consumed_inputs=state.get("research_topic", ""),
        )

    async def run(self, state: PipelineState, context: StageContext) -> StageResult:
        registry = context.registry
        if registry is None:
            return StageResult(
                output={},
                status="backtrack",
                next_hint=None,
                reason="No registry in StageContext",
            )

        professor = resolve_agent(
            registry,
            "professor",
            llm_provider=context.llm_provider,
            cost_tracker=context.cost_tracker,
            state=state,
            event_bus=context.event_bus,
            storage=context.storage,
        )
        phd = resolve_agent(
            registry,
            "phd_student",
            llm_provider=context.llm_provider,
            cost_tracker=context.cost_tracker,
            state=state,
            event_bus=context.event_bus,
            storage=context.storage,
        )

        # Step 1: Professor drafts outline
        outline_prompt = self._build_outline_prompt(state)
        outline = await professor.inference(
            outline_prompt,
            build_agent_context(state, professor, phase="report_writing"),
        )

        # Step 2: PhD fills sections into a complete draft
        draft_prompt = self._build_draft_prompt(outline)
        draft_latex = await phd.inference(
            draft_prompt,
            build_agent_context(state, phd, phase="report_writing"),
        )

        # Step 3: Professor polishes
        polish_prompt = self._build_polish_prompt(draft_latex)
        final_latex = await professor.inference(
            polish_prompt,
            build_agent_context(state, professor, phase="report_writing"),
        )

        sections = self._extract_sections(final_latex)

        report = ReportResult(
            latex_source=final_latex,
            sections=sections,
            compiled_pdf_path=None,
        )

        sync_agent_memory_to_state(state, {"professor": professor, "phd_student": phd})
        return StageResult(
            output={"report": [report]},
            status="done",
            reason="Report written by professor-PhD collaboration (outline → draft → polish)",
        )

    def _build_outline_prompt(self, state: PipelineState) -> str:
        lit_count = len(state.get("literature_review", []))
        plan_count = len(state.get("plan", []))
        exp_count = len(state.get("experiment_results", []))
        interp_count = len(state.get("interpretation", []))
        return (
            f"Topic: {state['research_topic']}\n\n"
            f"Available materials:\n"
            f"- Literature review: {lit_count} reviews\n"
            f"- Plan: {plan_count} plans\n"
            f"- Experiment results: {exp_count} runs\n"
            f"- Interpretation: {interp_count} entries\n\n"
            f"Draft a LaTeX paper outline with these sections: Abstract, Introduction, "
            f"Related Work, Methodology, Experiments, Results, Discussion, Conclusion. "
            f"Return only the LaTeX section headers and a one-line description under each."
        )

    def _build_draft_prompt(self, outline: str) -> str:
        return (
            f"Outline:\n{outline}\n\n"
            r"Write a complete LaTeX paper (\documentclass{article} ... \end{document}) "
            r"based on this outline and the project's materials. Use \section{} for each "
            r"section. Keep it concise (~1000 words body). Include an \begin{abstract} ... "
            r"\end{abstract} environment."
        )

    def _build_polish_prompt(self, draft_latex: str) -> str:
        return (
            f"Draft LaTeX:\n{draft_latex}\n\n"
            f"Improve academic tone, fix structure issues, ensure all sections flow. "
            f"Return the complete revised LaTeX document only."
        )

    def _extract_sections(self, latex: str) -> dict[str, str]:
        sections: dict[str, str] = {}
        for match in re.finditer(
            r"\\section\{([^}]+)\}(.*?)(?=\\section\{|\\end\{document\})",
            latex,
            re.DOTALL,
        ):
            title = match.group(1).strip()
            body = match.group(2).strip()
            sections[title] = body
        return sections
