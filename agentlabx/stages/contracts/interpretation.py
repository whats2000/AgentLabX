"""Stage I/O contracts for the `interpretation` stage.

Capabilities (A8 allow-list reference):
  Required: memory_read
  Optional: code_exec (sanity-check derivations)

Tool grounding:
- findings: LLM-synthesised findings grounded in metrics and artifact content
- confidence_notes: LLM-generated caveats; empty list is legitimate for
  confident findings
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from agentlabx.stages.contracts._shared import (
    ArtifactRef,
    Finding,
    Hypothesis,
    Metric,
)


class InterpretationInput(BaseModel):  # type: ignore[explicit-any]
    """Input contract for the interpretation stage."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    metrics: list[Metric]
    artifacts: list[ArtifactRef]
    hypotheses: list[Hypothesis]


class InterpretationOutput(BaseModel):  # type: ignore[explicit-any]
    """Output contract for the interpretation stage."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    findings: list[Finding]  # ≥1; [LLM grounded in metrics]
    confidence_notes: list[str]  # [LLM]


__all__ = [
    "InterpretationInput",
    "InterpretationOutput",
]
