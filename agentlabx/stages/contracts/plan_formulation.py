"""Stage I/O contracts for the `plan_formulation` stage.

Capabilities (A8 allow-list reference):
  Required: memory_read
  Optional: paper_search (related-work expansion)

Tool grounding:
- hypotheses: LLM-synthesised from citations and research question
- methodology: LLM-generated experimental plan
- success_criteria: LLM-generated criteria for evaluating hypotheses
- accepted_citation_ids: LLM-selected subset of input citation paper_ids

PI ratification is NOT carried on the output — A8 emits as event per Q6
pushback.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from agentlabx.stages.contracts._shared import (
    Citation,
    Hypothesis,
    ResearchQuestion,
)


class PlanFormulationInput(BaseModel):  # type: ignore[explicit-any]
    """Input contract for the plan_formulation stage."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    citations: list[Citation]
    corpus_id: str
    question: ResearchQuestion


class PlanFormulationOutput(BaseModel):  # type: ignore[explicit-any]
    """Output contract for the plan_formulation stage."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    hypotheses: list[Hypothesis]  # ≥1; [LLM]
    methodology: str  # [LLM]
    success_criteria: list[str]  # [LLM]
    accepted_citation_ids: list[str]  # subset of input citations[*].paper_id


__all__ = [
    "PlanFormulationInput",
    "PlanFormulationOutput",
]
