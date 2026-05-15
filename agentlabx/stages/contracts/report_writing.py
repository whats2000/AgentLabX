"""Stage I/O contracts for the `report_writing` stage.

Capabilities (A8 allow-list reference):
  Required: fs_read, fs_write
  Optional: code_exec, web_fetch

Tool grounding:
- report_markdown: filesystem.write_file path wrapped as ArtifactRef
- report_latex: filesystem.write_file path or None if LaTeX not generated
- report_pdf: filesystem.write_file path or None if PDF not generated
- cited_chunk_ids: union of findings[*].cited_chunk_ids (internal aggregation)
- pandoc_log: code.exec payload from pandoc invocation; None iff PDF render did not run

Required-no-default fields: report_latex, report_pdf, pandoc_log must be PRESENT
(None is allowed, omission is rejected) per FR-7 pattern.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from agentlabx.stages.contracts._shared import (
    ArtifactRef,
    Citation,
    ExecLog,
    Finding,
    Metric,
)


class ReportWritingInput(BaseModel):  # type: ignore[explicit-any]
    """Input contract for the report_writing stage."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    findings: list[Finding]
    citations: list[Citation]
    metrics: list[Metric]
    methodology: str


class ReportWritingOutput(BaseModel):  # type: ignore[explicit-any]
    """Output contract for the report_writing stage.

    ``report_latex``, ``report_pdf``, and ``pandoc_log`` are required-no-default
    (bare ``T | None``): they must be present in the payload; None signals
    "not generated / not run" per FR-7.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    report_markdown: ArtifactRef  # [← filesystem.write_file]
    report_latex: ArtifactRef | None  # required-no-default; None iff LaTeX not generated
    report_pdf: ArtifactRef | None  # required-no-default; None iff PDF not generated
    cited_chunk_ids: list[str]  # [internal — union of findings[*].cited_chunk_ids]
    # required-no-default; None iff PDF render did not run; [← code.exec]
    pandoc_log: ExecLog | None


__all__ = [
    "ReportWritingInput",
    "ReportWritingOutput",
]
