"""Stage I/O contracts for the `literature_review` stage.

Capabilities (A8 allow-list reference): paper_search, paper_fetch, memory_read.

Tool grounding:
- citations: list[Citation] from arxiv.search_papers / semantic_scholar.paper_relevance_search
- summaries: LLM-synthesised over arxiv.read_paper.content + A5 RAG chunks
- corpus_id: assigned by A5 RAG ingestion

# Capabilities: paper_search, paper_fetch, memory_read
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from agentlabx.stages.contracts._shared import (
    Citation,
    CitationSummary,
    ResearchQuestion,
)


class LiteratureReviewInput(BaseModel):  # type: ignore[explicit-any]
    """Input contract for the literature_review stage."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    question: ResearchQuestion
    prior_corpus_ids: list[str] = Field(default_factory=list)
    target_count_min: int = 10


class LiteratureReviewOutput(BaseModel):  # type: ignore[explicit-any]
    """Output contract for the literature_review stage.

    Raw arxiv/S2 hits are NOT carried — they live in the event log per Q5
    pushback.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    # len ≥ target_count_min; [← arxiv.search_papers / S2 paper_relevance_search]
    citations: list[Citation]
    summaries: list[CitationSummary]  # [LLM over arxiv.read_paper.content + RAG]
    corpus_id: str  # [internal — A5 RAG assigns]


__all__ = [
    "LiteratureReviewInput",
    "LiteratureReviewOutput",
]
