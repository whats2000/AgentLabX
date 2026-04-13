"""Real report writing stage — professor + PhD student outline, draft, polish."""

from __future__ import annotations

import re

from agentlabx.core.state import PipelineState, ReportResult
from agentlabx.stages._helpers import build_agent_context, resolve_agent
from agentlabx.stages.base import BaseStage, StageContext, StageResult, sync_agent_memory_to_state


class ReportWritingStage(BaseStage):
    name = "report_writing"
    description = "Professor and PhD student write the research paper in LaTeX."
    required_agents = ["professor", "phd_student"]
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

        professor = resolve_agent(
            registry,
            "professor",
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
