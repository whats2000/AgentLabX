"""Real literature review stage — PhD student iteratively searches and synthesizes."""

from __future__ import annotations

from agentlabx.core.state import LitReviewResult, PipelineState
from agentlabx.stages._helpers import build_agent_context, resolve_agent, resolve_tool
from agentlabx.stages.base import BaseStage, StageContext, StageResult, sync_agent_memory_to_state


class LiteratureReviewStage(BaseStage):
    name = "literature_review"
    description = "PhD student iteratively searches and synthesizes related work."
    required_agents = ["phd_student"]
    required_tools = ["arxiv_search"]

    MAX_ITERATIONS = 3
    MIN_PAPERS = 5

    async def run(self, state: PipelineState, context: StageContext) -> StageResult:
        registry = context.registry
        if registry is None:
            return StageResult(
                output={},
                status="backtrack",
                next_hint=None,
                reason="No registry in StageContext",
            )

        phd = resolve_agent(
            registry,
            "phd_student",
            llm_provider=context.llm_provider,
            cost_tracker=context.cost_tracker,
            state=state,
        )
        arxiv_tool = resolve_tool(registry, "arxiv_search", event_bus=context.event_bus, storage=context.storage)

        topic = state["research_topic"]
        papers: list[dict] = []

        for iteration in range(self.MAX_ITERATIONS):
            query_prompt = self._build_query_prompt(topic, papers, iteration)
            ctx = build_agent_context(state, phd, phase="literature_review")
            query_response = await phd.inference(query_prompt, ctx)
            search_query = self._extract_query(query_response)

            arxiv_result = await arxiv_tool.execute(query=search_query, max_results=5)
            if arxiv_result.success and arxiv_result.data:
                papers.extend(arxiv_result.data.get("papers", []))

            if len(papers) >= self.MIN_PAPERS:
                break

        summary_prompt = self._build_summary_prompt(topic, papers)
        summary_ctx = build_agent_context(state, phd, phase="literature_review")
        summary = await phd.inference(summary_prompt, summary_ctx)

        result = LitReviewResult(papers=papers[:10], summary=summary)
        num_iterations = min(iteration + 1, self.MAX_ITERATIONS)
        sync_agent_memory_to_state(state, {"phd_student": phd})
        return StageResult(
            output={"literature_review": [result]},
            status="done",
            reason=f"Reviewed {len(papers)} papers over {num_iterations} iterations",
        )

    def _build_query_prompt(self, topic: str, existing: list, iteration: int) -> str:
        existing_summary = "\n".join(f"- {p.get('title', '')}" for p in existing[:5])
        return (
            f"Research topic: {topic}\n\n"
            f"Papers found so far (iteration {iteration + 1}):\n"
            f"{existing_summary or 'None'}\n\n"
            f"Generate a concise search query (3-8 words) to find more relevant papers. "
            f"Output only the query, no explanation."
        )

    def _build_summary_prompt(self, topic: str, papers: list) -> str:
        papers_text = "\n\n".join(
            f"Title: {p.get('title', '')}\nAbstract: {(p.get('abstract', '') or '')[:300]}"
            for p in papers[:10]
        )
        return (
            f"Topic: {topic}\n\n"
            f"Papers:\n{papers_text}\n\n"
            f"Write a 200-word literature review synthesizing these papers, "
            f"identifying key themes, gaps, and relevance to the research topic."
        )

    def _extract_query(self, response: str) -> str:
        # Take the first non-empty line, strip punctuation/quotes
        for line in response.strip().split("\n"):
            line = line.strip().strip("\"'`")
            if line:
                return line
        return response.strip()
