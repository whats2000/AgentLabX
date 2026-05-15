"""Deterministic echo stage stubs for AgentLabX pipeline stages (A4 Tasks 7+8).

Each stub is a concrete :class:`~agentlabx.stages.protocol.Stage` subclass that:
- Declares the canonical I/O contract from ``agentlabx.stages.contracts.<stage>``.
- Imports ``backtrack_targets`` from :data:`~agentlabx.stages.registry.CANONICAL_BACKTRACK_TARGETS`
  so any future canonical change is automatically reflected.
- Produces a minimum-valid, deterministic output from its input with no LLM or MCP calls.
- Emits exactly one ``stage.echo.completed`` event per execution.
- Returns ``ReproducibilityContract`` only for ``EchoExperimentationStage``.

These stubs satisfy entry-point registration and serve as the Layer-B placeholder
implementations until real LLM-backed impls are shipped.
"""

from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel

from agentlabx.stages.contracts._shared import (
    ActionItem,
    ArtifactRef,
    Citation,
    CitationSummary,
    ExecLog,
    Finding,
    Hypothesis,
    Metric,
)
from agentlabx.stages.contracts.data_exploration import (
    DataExplorationInput,
    DataExplorationOutput,
)
from agentlabx.stages.contracts.data_preparation import (
    DataPreparationInput,
    DataPreparationOutput,
)
from agentlabx.stages.contracts.experimentation import (
    ExperimentationInput,
    ExperimentationOutput,
)
from agentlabx.stages.contracts.interpretation import (
    InterpretationInput,
    InterpretationOutput,
)
from agentlabx.stages.contracts.literature_review import (
    LiteratureReviewInput,
    LiteratureReviewOutput,
)
from agentlabx.stages.contracts.peer_review import (
    PeerReviewInput,
    PeerReviewOutput,
)
from agentlabx.stages.contracts.plan_formulation import (
    PlanFormulationInput,
    PlanFormulationOutput,
)
from agentlabx.stages.contracts.report_writing import (
    ReportWritingInput,
    ReportWritingOutput,
)
from agentlabx.stages.protocol import (
    Stage,
    StageContext,
    StageOutput,
    StageResult,
)
from agentlabx.stages.registry import CANONICAL_BACKTRACK_TARGETS
from agentlabx.stages.reproducibility import ReproducibilityContract


class EchoLiteratureReviewStage(Stage[LiteratureReviewInput, LiteratureReviewOutput]):
    """Echo stub for the ``literature_review`` stage.

    Synthesises a minimum-valid ``LiteratureReviewOutput`` deterministically
    from the input with no LLM or MCP calls.
    """

    stage_name: ClassVar[str] = "literature_review"
    input_model: ClassVar[type[BaseModel]] = LiteratureReviewInput
    output_model: ClassVar[type[BaseModel]] = LiteratureReviewOutput
    backtrack_targets: ClassVar[frozenset[str]] = CANONICAL_BACKTRACK_TARGETS["literature_review"]
    required_capabilities: ClassVar[frozenset[str]] = frozenset(
        {"paper_search", "paper_fetch", "memory_read"}
    )
    requires_reproducibility: ClassVar[bool] = False

    async def execute(
        self,
        payload: LiteratureReviewInput,
        ctx: StageContext,
    ) -> StageResult[LiteratureReviewOutput]:
        """Return a minimum-valid LiteratureReviewOutput and emit one echo event."""
        citations = [
            Citation(
                paper_id=f"echo-paper-{i}",
                title=f"Echo Paper {i}",
                authors=["Echo Author"],
                year=2026,
                source="other",
                url=None,
            )
            for i in range(payload.target_count_min)
        ]
        summaries = [
            CitationSummary(
                citation_id=c.paper_id,
                paragraph=f"Echo summary for {c.title}",
                chunk_refs=[],
            )
            for c in citations
        ]
        corpus_id = f"echo-corpus-{payload.question.project_id}"
        output = LiteratureReviewOutput(
            citations=citations,
            summaries=summaries,
            corpus_id=corpus_id,
        )
        await ctx.emit_event("stage.echo.completed", {"stage_name": self.stage_name})
        return StageOutput[LiteratureReviewOutput](payload=output, reproducibility=None)


class EchoPlanFormulationStage(Stage[PlanFormulationInput, PlanFormulationOutput]):
    """Echo stub for the ``plan_formulation`` stage."""

    stage_name: ClassVar[str] = "plan_formulation"
    input_model: ClassVar[type[BaseModel]] = PlanFormulationInput
    output_model: ClassVar[type[BaseModel]] = PlanFormulationOutput
    backtrack_targets: ClassVar[frozenset[str]] = CANONICAL_BACKTRACK_TARGETS["plan_formulation"]
    required_capabilities: ClassVar[frozenset[str]] = frozenset({"memory_read", "paper_search"})
    requires_reproducibility: ClassVar[bool] = False

    async def execute(
        self,
        payload: PlanFormulationInput,
        ctx: StageContext,
    ) -> StageResult[PlanFormulationOutput]:
        """Return a minimum-valid PlanFormulationOutput and emit one echo event."""
        hypotheses = [
            Hypothesis(
                id="echo-h1",
                statement="Echo hypothesis: applying X to Y yields Z",
                baselines=["baseline-A"],
                ablations=["ablation-A"],
            )
        ]
        accepted_citation_ids = [payload.citations[0].paper_id] if payload.citations else []
        output = PlanFormulationOutput(
            hypotheses=hypotheses,
            methodology="Echo methodology: train baseline + 1 ablation",
            success_criteria=["Echo: metric improves over baseline"],
            accepted_citation_ids=accepted_citation_ids,
        )
        await ctx.emit_event("stage.echo.completed", {"stage_name": self.stage_name})
        return StageOutput[PlanFormulationOutput](payload=output, reproducibility=None)


class EchoDataExplorationStage(Stage[DataExplorationInput, DataExplorationOutput]):
    """Echo stub for the ``data_exploration`` stage."""

    stage_name: ClassVar[str] = "data_exploration"
    input_model: ClassVar[type[BaseModel]] = DataExplorationInput
    output_model: ClassVar[type[BaseModel]] = DataExplorationOutput
    backtrack_targets: ClassVar[frozenset[str]] = CANONICAL_BACKTRACK_TARGETS["data_exploration"]
    required_capabilities: ClassVar[frozenset[str]] = frozenset(
        {"fs_read", "fs_write", "code_exec"}
    )
    requires_reproducibility: ClassVar[bool] = False

    async def execute(
        self,
        payload: DataExplorationInput,
        ctx: StageContext,
    ) -> StageResult[DataExplorationOutput]:
        """Return a minimum-valid DataExplorationOutput and emit one echo event."""
        output = DataExplorationOutput(
            summary_stats={"n_samples": 1000.0, "n_features": 10.0},
            plots=[
                ArtifactRef(
                    artifact_id="echo-plot-1",
                    kind="plot",
                    path="/tmp/echo/plot1.png",
                    content_hash="0" * 64,
                )
            ],
            characterization=f"Echo characterization of {payload.dataset.name}",
            exec_log=ExecLog(stdout="echo stdout", stderr="", exit_code=0),
        )
        await ctx.emit_event("stage.echo.completed", {"stage_name": self.stage_name})
        return StageOutput[DataExplorationOutput](payload=output, reproducibility=None)


class EchoDataPreparationStage(Stage[DataPreparationInput, DataPreparationOutput]):
    """Echo stub for the ``data_preparation`` stage."""

    stage_name: ClassVar[str] = "data_preparation"
    input_model: ClassVar[type[BaseModel]] = DataPreparationInput
    output_model: ClassVar[type[BaseModel]] = DataPreparationOutput
    backtrack_targets: ClassVar[frozenset[str]] = CANONICAL_BACKTRACK_TARGETS["data_preparation"]
    required_capabilities: ClassVar[frozenset[str]] = frozenset(
        {"fs_read", "fs_write", "code_exec"}
    )
    requires_reproducibility: ClassVar[bool] = False

    async def execute(
        self,
        payload: DataPreparationInput,
        ctx: StageContext,
    ) -> StageResult[DataPreparationOutput]:
        """Return a minimum-valid DataPreparationOutput and emit one echo event."""
        output = DataPreparationOutput(
            prep_script=ArtifactRef(
                artifact_id="echo-script-1",
                kind="script",
                path="/tmp/echo/prep.py",
                content_hash="0" * 64,
            ),
            splits={
                "train": ArtifactRef(
                    artifact_id="echo-train",
                    kind="split",
                    path="/tmp/echo/train.parquet",
                    content_hash="1" * 64,
                ),
                "val": ArtifactRef(
                    artifact_id="echo-val",
                    kind="split",
                    path="/tmp/echo/val.parquet",
                    content_hash="2" * 64,
                ),
            },
            transforms=["normalize"],
            exec_log=ExecLog(stdout="echo", stderr="", exit_code=0),
        )
        await ctx.emit_event("stage.echo.completed", {"stage_name": self.stage_name})
        return StageOutput[DataPreparationOutput](payload=output, reproducibility=None)


class EchoExperimentationStage(Stage[ExperimentationInput, ExperimentationOutput]):
    """Echo stub for the ``experimentation`` stage.

    This is the only echo stub that sets ``requires_reproducibility = True`` and
    returns a populated :class:`~agentlabx.stages.reproducibility.ReproducibilityContract`.
    """

    stage_name: ClassVar[str] = "experimentation"
    input_model: ClassVar[type[BaseModel]] = ExperimentationInput
    output_model: ClassVar[type[BaseModel]] = ExperimentationOutput
    backtrack_targets: ClassVar[frozenset[str]] = CANONICAL_BACKTRACK_TARGETS["experimentation"]
    required_capabilities: ClassVar[frozenset[str]] = frozenset(
        {"fs_read", "fs_write", "code_exec", "memory_write"}
    )
    requires_reproducibility: ClassVar[bool] = True

    async def execute(
        self,
        payload: ExperimentationInput,
        ctx: StageContext,
    ) -> StageResult[ExperimentationOutput]:
        """Return a minimum-valid ExperimentationOutput with ReproducibilityContract."""
        output = ExperimentationOutput(
            metrics=[Metric(name="echo_accuracy", value=0.95, unit=None)],
            artifacts=[
                ArtifactRef(
                    artifact_id="echo-model-1",
                    kind="model",
                    path="/tmp/echo/model.pt",
                    content_hash="0" * 64,
                )
            ],
            exec_logs=[ExecLog(stdout="echo run baseline", stderr="", exit_code=0)],
            memory_entries_created=[],
        )
        repro = ReproducibilityContract(
            seed=42,
            env_hash="echohash",
            deps_snapshot={"echo": "1.0"},
            run_command="echo run",
            container_image=None,
            git_ref=None,
        )
        await ctx.emit_event("stage.echo.completed", {"stage_name": self.stage_name})
        return StageOutput[ExperimentationOutput](payload=output, reproducibility=repro)


class EchoInterpretationStage(Stage[InterpretationInput, InterpretationOutput]):
    """Echo stub for the ``interpretation`` stage."""

    stage_name: ClassVar[str] = "interpretation"
    input_model: ClassVar[type[BaseModel]] = InterpretationInput
    output_model: ClassVar[type[BaseModel]] = InterpretationOutput
    backtrack_targets: ClassVar[frozenset[str]] = CANONICAL_BACKTRACK_TARGETS["interpretation"]
    required_capabilities: ClassVar[frozenset[str]] = frozenset({"memory_read", "code_exec"})
    requires_reproducibility: ClassVar[bool] = False

    async def execute(
        self,
        payload: InterpretationInput,
        ctx: StageContext,
    ) -> StageResult[InterpretationOutput]:
        """Return a minimum-valid InterpretationOutput and emit one echo event."""
        findings = [
            Finding(
                id="echo-f1",
                statement="Echo finding",
                cited_metric_names=[m.name for m in payload.metrics],
                cited_artifact_ids=[a.artifact_id for a in payload.artifacts],
                verbatim_values={m.name: m.value for m in payload.metrics},
                cited_chunk_ids=[],
            )
        ]
        output = InterpretationOutput(
            findings=findings,
            confidence_notes=["Echo: deterministic output"],
        )
        await ctx.emit_event("stage.echo.completed", {"stage_name": self.stage_name})
        return StageOutput[InterpretationOutput](payload=output, reproducibility=None)


class EchoReportWritingStage(Stage[ReportWritingInput, ReportWritingOutput]):
    """Echo stub for the ``report_writing`` stage."""

    stage_name: ClassVar[str] = "report_writing"
    input_model: ClassVar[type[BaseModel]] = ReportWritingInput
    output_model: ClassVar[type[BaseModel]] = ReportWritingOutput
    backtrack_targets: ClassVar[frozenset[str]] = CANONICAL_BACKTRACK_TARGETS["report_writing"]
    required_capabilities: ClassVar[frozenset[str]] = frozenset(
        {"fs_read", "fs_write", "code_exec", "web_fetch"}
    )
    requires_reproducibility: ClassVar[bool] = False

    async def execute(
        self,
        payload: ReportWritingInput,
        ctx: StageContext,
    ) -> StageResult[ReportWritingOutput]:
        """Return a minimum-valid ReportWritingOutput and emit one echo event."""
        output = ReportWritingOutput(
            report_markdown=ArtifactRef(
                artifact_id="echo-report-md",
                kind="report",
                path="/tmp/echo/report.md",
                content_hash="0" * 64,
            ),
            report_latex=None,
            report_pdf=None,
            cited_chunk_ids=[],
            pandoc_log=None,
        )
        await ctx.emit_event("stage.echo.completed", {"stage_name": self.stage_name})
        return StageOutput[ReportWritingOutput](payload=output, reproducibility=None)


class EchoPeerReviewStage(Stage[PeerReviewInput, PeerReviewOutput]):
    """Echo stub for the ``peer_review`` stage."""

    stage_name: ClassVar[str] = "peer_review"
    input_model: ClassVar[type[BaseModel]] = PeerReviewInput
    output_model: ClassVar[type[BaseModel]] = PeerReviewOutput
    backtrack_targets: ClassVar[frozenset[str]] = CANONICAL_BACKTRACK_TARGETS["peer_review"]
    required_capabilities: ClassVar[frozenset[str]] = frozenset({"fs_read", "memory_read"})
    requires_reproducibility: ClassVar[bool] = False

    async def execute(
        self,
        payload: PeerReviewInput,
        ctx: StageContext,
    ) -> StageResult[PeerReviewOutput]:
        """Return a minimum-valid PeerReviewOutput and emit one echo event."""
        output = PeerReviewOutput(
            critique="Echo critique: report is internally consistent",
            action_items=[
                ActionItem(
                    id="echo-a1",
                    severity="minor",
                    description="Echo nit",
                    target_section=None,
                )
            ],
            recommended_backtrack=None,
        )
        await ctx.emit_event("stage.echo.completed", {"stage_name": self.stage_name})
        return StageOutput[PeerReviewOutput](payload=output, reproducibility=None)


__all__ = [
    "EchoDataExplorationStage",
    "EchoDataPreparationStage",
    "EchoExperimentationStage",
    "EchoInterpretationStage",
    "EchoLiteratureReviewStage",
    "EchoPeerReviewStage",
    "EchoPlanFormulationStage",
    "EchoReportWritingStage",
]
