"""Stage I/O contracts for the `peer_review` stage.

Capabilities (A8 allow-list reference): fs_read, memory_read.

Tool grounding:
- critique: LLM review narrative over the report markdown and findings
- action_items: LLM-generated list of prioritised review items
- recommended_backtrack: BacktrackSignal or None; target_stage may be any
  earlier stage. Required-no-default: must be present (None allowed, omission
  rejected).

M-1 fix: metrics and methodology mirror ReportWritingInput so the reviewer can
emit "fundamental issue" backtracks grounded in numeric results and methods.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from agentlabx.stages.contracts._shared import (
    ActionItem,
    ArtifactRef,
    Finding,
    Metric,
)
from agentlabx.stages.protocol import BacktrackSignal


class PeerReviewInput(BaseModel):  # type: ignore[explicit-any]
    """Input contract for the peer_review stage."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    report_markdown: ArtifactRef
    findings: list[Finding]
    metrics: list[Metric]  # M-1 fix — needed to emit "fundamental issue" backtracks
    methodology: str  # M-1 fix — mirrors ReportWritingInput


class PeerReviewOutput(BaseModel):  # type: ignore[explicit-any]
    """Output contract for the peer_review stage.

    ``recommended_backtrack`` is required-no-default (bare ``BacktrackSignal | None``):
    it must be present; None signals "no backtrack recommended".
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    critique: str  # [LLM]
    action_items: list[ActionItem]  # [LLM]
    # required-no-default; target_stage may be any earlier stage
    recommended_backtrack: BacktrackSignal | None


__all__ = [
    "PeerReviewInput",
    "PeerReviewOutput",
]
