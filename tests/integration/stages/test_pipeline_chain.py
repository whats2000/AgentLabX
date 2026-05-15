"""Integration test: full 8-stage pipeline chain (A4 Task 9).

Chains all 8 echo stubs end-to-end, piping each output into the next stage's
input where shapes overlap.  Validates input and output at every boundary
via the canonical validator functions.  Marked ``@pytest.mark.integration``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest

from agentlabx.stages.contracts._shared import DatasetRef, ResearchQuestion
from agentlabx.stages.contracts.data_exploration import DataExplorationInput
from agentlabx.stages.contracts.data_preparation import DataPreparationInput
from agentlabx.stages.contracts.experimentation import ExperimentationInput
from agentlabx.stages.contracts.interpretation import InterpretationInput
from agentlabx.stages.contracts.literature_review import LiteratureReviewInput
from agentlabx.stages.contracts.peer_review import PeerReviewInput
from agentlabx.stages.contracts.plan_formulation import PlanFormulationInput
from agentlabx.stages.contracts.report_writing import ReportWritingInput
from agentlabx.stages.echo.stages import (
    EchoDataExplorationStage,
    EchoDataPreparationStage,
    EchoExperimentationStage,
    EchoInterpretationStage,
    EchoLiteratureReviewStage,
    EchoPeerReviewStage,
    EchoPlanFormulationStage,
    EchoReportWritingStage,
)
from agentlabx.stages.protocol import (
    JSONValue,
    StageContext,
    StageOutput,
)
from agentlabx.stages.reproducibility import ReproducibilityContract
from agentlabx.stages.validator import validate_input, validate_output

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@dataclass
class _EventRecorder:
    """Records (kind, payload) pairs from emit_event calls."""

    events: list[tuple[str, dict[str, JSONValue]]] = field(default_factory=list)

    async def emit_event(self, kind: str, payload: dict[str, JSONValue]) -> None:
        self.events.append((kind, payload))


def _make_ctx(recorder: _EventRecorder, run_id: str = "run-chain-1") -> StageContext:
    """Build a StageContext backed by the given recorder."""
    return StageContext(
        run_id=run_id,
        project_id="proj-chain-1",
        stage_run_id=f"stage-{run_id}",
        identity_id="user-chain-1",
        run_mode="auto",
        emit_event=recorder.emit_event,
        now=lambda: datetime.now(UTC),
    )


# ---------------------------------------------------------------------------
# Integration test
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_full_pipeline_chains_through_all_8_stages() -> None:
    """Chain all 8 echo stubs end-to-end through the validator.

    Pipes each output into the next stage's input where shapes overlap.
    Asserts the entire pipeline validates without modifying types.
    """
    recorder = _EventRecorder()
    ctx = _make_ctx(recorder)

    # Shared seed inputs
    question = ResearchQuestion(text="Does X improve Y over baseline?", project_id="proj-chain-1")
    dataset = DatasetRef(dataset_id="ds-chain", name="ChainDataset", split_hint=None)

    # ------------------------------------------------------------------ B1
    # literature_review
    # ------------------------------------------------------------------ B1
    b1_input = LiteratureReviewInput(
        question=question,
        prior_corpus_ids=[],
        target_count_min=3,
    )
    b1_validated_input = validate_input("literature_review", b1_input.model_dump(mode="json"))
    assert isinstance(b1_validated_input, LiteratureReviewInput)

    b1_stage = EchoLiteratureReviewStage()
    b1_result = await b1_stage.execute(b1_validated_input, ctx)
    assert isinstance(b1_result, StageOutput)

    b1_repro_dict: dict[str, JSONValue] | None = (
        b1_result.reproducibility.model_dump(mode="json")
        if b1_result.reproducibility is not None
        else None
    )
    validate_output(
        "literature_review",
        b1_result.payload.model_dump(mode="json"),
        b1_repro_dict,
    )

    # Carry-forward variables from B1
    citations = b1_result.payload.citations
    corpus_id = b1_result.payload.corpus_id

    # ------------------------------------------------------------------ B2
    # plan_formulation
    # ------------------------------------------------------------------ B2
    b2_input = PlanFormulationInput(
        citations=citations,
        corpus_id=corpus_id,
        question=question,
    )
    b2_validated_input = validate_input("plan_formulation", b2_input.model_dump(mode="json"))
    assert isinstance(b2_validated_input, PlanFormulationInput)

    b2_stage = EchoPlanFormulationStage()
    b2_result = await b2_stage.execute(b2_validated_input, ctx)
    assert isinstance(b2_result, StageOutput)

    b2_repro_dict: dict[str, JSONValue] | None = (
        b2_result.reproducibility.model_dump(mode="json")
        if b2_result.reproducibility is not None
        else None
    )
    validate_output(
        "plan_formulation",
        b2_result.payload.model_dump(mode="json"),
        b2_repro_dict,
    )

    # Carry-forward variables from B2
    hypotheses = b2_result.payload.hypotheses
    methodology = b2_result.payload.methodology

    # ------------------------------------------------------------------ B3
    # data_exploration
    # ------------------------------------------------------------------ B3
    b3_input = DataExplorationInput(
        dataset=dataset,
        hypotheses=hypotheses,
    )
    b3_validated_input = validate_input("data_exploration", b3_input.model_dump(mode="json"))
    assert isinstance(b3_validated_input, DataExplorationInput)

    b3_stage = EchoDataExplorationStage()
    b3_result = await b3_stage.execute(b3_validated_input, ctx)
    assert isinstance(b3_result, StageOutput)

    b3_repro_dict: dict[str, JSONValue] | None = (
        b3_result.reproducibility.model_dump(mode="json")
        if b3_result.reproducibility is not None
        else None
    )
    validate_output(
        "data_exploration",
        b3_result.payload.model_dump(mode="json"),
        b3_repro_dict,
    )

    # Carry-forward from B3
    characterization = b3_result.payload.characterization

    # ------------------------------------------------------------------ B4
    # data_preparation
    # ------------------------------------------------------------------ B4
    b4_input = DataPreparationInput(
        dataset=dataset,
        characterization=characterization,
        plan_excerpt=methodology,
    )
    b4_validated_input = validate_input("data_preparation", b4_input.model_dump(mode="json"))
    assert isinstance(b4_validated_input, DataPreparationInput)

    b4_stage = EchoDataPreparationStage()
    b4_result = await b4_stage.execute(b4_validated_input, ctx)
    assert isinstance(b4_result, StageOutput)

    b4_repro_dict: dict[str, JSONValue] | None = (
        b4_result.reproducibility.model_dump(mode="json")
        if b4_result.reproducibility is not None
        else None
    )
    validate_output(
        "data_preparation",
        b4_result.payload.model_dump(mode="json"),
        b4_repro_dict,
    )

    # Carry-forward from B4
    splits = b4_result.payload.splits
    prep_script = b4_result.payload.prep_script

    # ------------------------------------------------------------------ B5
    # experimentation  (the only stage with ReproducibilityContract)
    # ------------------------------------------------------------------ B5
    b5_input = ExperimentationInput(
        hypotheses=hypotheses,
        splits=splits,
        prep_script=prep_script,
    )
    b5_validated_input = validate_input("experimentation", b5_input.model_dump(mode="json"))
    assert isinstance(b5_validated_input, ExperimentationInput)

    b5_stage = EchoExperimentationStage()
    b5_result = await b5_stage.execute(b5_validated_input, ctx)
    assert isinstance(b5_result, StageOutput)
    assert isinstance(b5_result.reproducibility, ReproducibilityContract), (
        "experimentation stage must return a ReproducibilityContract"
    )

    b5_repro_dict: dict[str, JSONValue] = b5_result.reproducibility.model_dump(mode="json")
    validate_output(
        "experimentation",
        b5_result.payload.model_dump(mode="json"),
        b5_repro_dict,
    )

    # Carry-forward from B5
    metrics = b5_result.payload.metrics
    artifacts = b5_result.payload.artifacts

    # ------------------------------------------------------------------ B6
    # interpretation
    # ------------------------------------------------------------------ B6
    b6_input = InterpretationInput(
        metrics=metrics,
        artifacts=artifacts,
        hypotheses=hypotheses,
    )
    b6_validated_input = validate_input("interpretation", b6_input.model_dump(mode="json"))
    assert isinstance(b6_validated_input, InterpretationInput)

    b6_stage = EchoInterpretationStage()
    b6_result = await b6_stage.execute(b6_validated_input, ctx)
    assert isinstance(b6_result, StageOutput)

    b6_repro_dict: dict[str, JSONValue] | None = (
        b6_result.reproducibility.model_dump(mode="json")
        if b6_result.reproducibility is not None
        else None
    )
    validate_output(
        "interpretation",
        b6_result.payload.model_dump(mode="json"),
        b6_repro_dict,
    )

    # Carry-forward from B6
    findings = b6_result.payload.findings

    # ------------------------------------------------------------------ B7
    # report_writing
    # ------------------------------------------------------------------ B7
    b7_input = ReportWritingInput(
        findings=findings,
        citations=citations,
        metrics=metrics,
        methodology=methodology,
    )
    b7_validated_input = validate_input("report_writing", b7_input.model_dump(mode="json"))
    assert isinstance(b7_validated_input, ReportWritingInput)

    b7_stage = EchoReportWritingStage()
    b7_result = await b7_stage.execute(b7_validated_input, ctx)
    assert isinstance(b7_result, StageOutput)

    b7_repro_dict: dict[str, JSONValue] | None = (
        b7_result.reproducibility.model_dump(mode="json")
        if b7_result.reproducibility is not None
        else None
    )
    validate_output(
        "report_writing",
        b7_result.payload.model_dump(mode="json"),
        b7_repro_dict,
    )

    # Carry-forward from B7
    report_markdown = b7_result.payload.report_markdown

    # ------------------------------------------------------------------ B8
    # peer_review
    # ------------------------------------------------------------------ B8
    b8_input = PeerReviewInput(
        report_markdown=report_markdown,
        findings=findings,
        metrics=metrics,
        methodology=methodology,
    )
    b8_validated_input = validate_input("peer_review", b8_input.model_dump(mode="json"))
    assert isinstance(b8_validated_input, PeerReviewInput)

    b8_stage = EchoPeerReviewStage()
    b8_result = await b8_stage.execute(b8_validated_input, ctx)
    assert isinstance(b8_result, StageOutput)

    b8_repro_dict: dict[str, JSONValue] | None = (
        b8_result.reproducibility.model_dump(mode="json")
        if b8_result.reproducibility is not None
        else None
    )
    validate_output(
        "peer_review",
        b8_result.payload.model_dump(mode="json"),
        b8_repro_dict,
    )

    # ------------------------------------------------------------------ Final assertions
    # ReproducibilityContract present ONLY on experimentation (B5)
    # Track by checking each result individually (avoids mypy generic-union issues).
    stages_with_repro: list[str] = []
    if b1_result.reproducibility is not None:
        stages_with_repro.append("literature_review")
    if b2_result.reproducibility is not None:
        stages_with_repro.append("plan_formulation")
    if b3_result.reproducibility is not None:
        stages_with_repro.append("data_exploration")
    if b4_result.reproducibility is not None:
        stages_with_repro.append("data_preparation")
    if b5_result.reproducibility is not None:
        stages_with_repro.append("experimentation")
    if b6_result.reproducibility is not None:
        stages_with_repro.append("interpretation")
    if b7_result.reproducibility is not None:
        stages_with_repro.append("report_writing")
    if b8_result.reproducibility is not None:
        stages_with_repro.append("peer_review")
    assert stages_with_repro == ["experimentation"], (
        f"ReproducibilityContract must be present only on 'experimentation'; "
        f"got it on: {stages_with_repro}"
    )

    # Final PeerReviewOutput: echo stub never triggers backtrack
    assert b8_result.payload.recommended_backtrack is None, (
        "EchoPeerReviewStage must return recommended_backtrack=None"
    )

    # Exactly 8 stage.echo.completed events emitted (one per stage)
    echo_events = [kind for kind, _ in recorder.events if kind == "stage.echo.completed"]
    assert len(echo_events) == 8, (
        f"Expected exactly 8 stage.echo.completed events, got {len(echo_events)}: {recorder.events}"
    )
