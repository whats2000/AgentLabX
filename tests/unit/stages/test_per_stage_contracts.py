"""Round-trip and required-field tests for all 8 per-stage I/O contracts (A4 Task 4).

16 models total: Input + Output for each of the 8 pipeline stages.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TypedDict

import pytest
from pydantic import BaseModel, ValidationError

from agentlabx.stages.contracts import (
    ActionItem,
    ArtifactRef,
    ChunkRef,
    Citation,
    CitationSummary,
    DatasetRef,
    ExecLog,
    Finding,
    Hypothesis,
    Metric,
    ResearchQuestion,
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
from agentlabx.stages.protocol import BacktrackSignal

# ---------------------------------------------------------------------------
# Shared fixture builders (narrow typed — no dict[str, object])
# ---------------------------------------------------------------------------


def _make_question() -> ResearchQuestion:
    return ResearchQuestion(text="Does augmentation help CT segmentation?", project_id="proj-1")


def _make_hypothesis() -> Hypothesis:
    return Hypothesis(
        id="h-1",
        statement="Augmentation improves Dice by 5%.",
        baselines=["no_aug"],
        ablations=["flip_only", "crop_only"],
    )


def _make_citation() -> Citation:
    return Citation(
        paper_id="2304.12345v1",
        title="Some Title",
        authors=["Alice Bob"],
        year=2023,
        source="arxiv",
        url="https://arxiv.org/abs/2304.12345v1",
    )


def _make_chunk_ref() -> ChunkRef:
    return ChunkRef(
        chunk_id="c-1",
        paper_id="2304.12345v1",
        span_start=0,
        span_end=200,
        score=0.9,
    )


def _make_citation_summary() -> CitationSummary:
    return CitationSummary(
        citation_id="2304.12345v1",
        paragraph="Key paper on augmentation.",
        chunk_refs=[_make_chunk_ref()],
    )


def _make_dataset_ref() -> DatasetRef:
    return DatasetRef(dataset_id="ds-1", name="MedSeg", split_hint="train")


def _make_artifact_ref(kind: str = "model", name: str = "model.pt") -> ArtifactRef:
    return ArtifactRef(
        artifact_id=f"a-{name}",
        kind=kind,  # type: ignore[arg-type]
        path=f"/workspace/runs/run-1/{name}",
        content_hash="sha256:deadbeef" * 4,
    )


def _make_exec_log(exit_code: int = 0) -> ExecLog:
    return ExecLog(stdout="loss: 0.42\n", stderr="", exit_code=exit_code)


def _make_metric() -> Metric:
    return Metric(name="dice", value=0.87, unit=None)


def _make_finding() -> Finding:
    return Finding(
        id="f-1",
        statement="Augmentation improves Dice by 5.2%.",
        cited_metric_names=["dice"],
        cited_artifact_ids=["a-model.pt"],
        cited_chunk_ids=["c-1"],
        verbatim_values={"dice": 0.87},
    )


def _make_action_item() -> ActionItem:
    return ActionItem(
        id="ai-1",
        severity="major",
        description="Missing ablation study.",
        target_section="§4 Experiments",
    )


def _make_backtrack_signal() -> BacktrackSignal:
    return BacktrackSignal(
        target_stage="plan_formulation",
        reason="Hypotheses were not falsifiable.",
        preserve=frozenset(["corpus_id"]),
    )


# ---------------------------------------------------------------------------
# Round-trip helpers — one per model
# ---------------------------------------------------------------------------


def _round_trip_literature_review_input() -> None:
    original = LiteratureReviewInput(
        question=_make_question(),
        prior_corpus_ids=["corp-1"],
        target_count_min=15,
    )
    restored = LiteratureReviewInput.model_validate(original.model_dump(mode="json"))
    assert restored == original


def _round_trip_literature_review_output() -> None:
    original = LiteratureReviewOutput(
        citations=[_make_citation()],
        summaries=[_make_citation_summary()],
        corpus_id="corp-42",
    )
    restored = LiteratureReviewOutput.model_validate(original.model_dump(mode="json"))
    assert restored == original


def _round_trip_plan_formulation_input() -> None:
    original = PlanFormulationInput(
        citations=[_make_citation()],
        corpus_id="corp-42",
        question=_make_question(),
    )
    restored = PlanFormulationInput.model_validate(original.model_dump(mode="json"))
    assert restored == original


def _round_trip_plan_formulation_output() -> None:
    original = PlanFormulationOutput(
        hypotheses=[_make_hypothesis()],
        methodology="Train ResUNet with 5-fold CV.",
        success_criteria=["Dice ≥ 0.85 on test set"],
        accepted_citation_ids=["2304.12345v1"],
    )
    restored = PlanFormulationOutput.model_validate(original.model_dump(mode="json"))
    assert restored == original


def _round_trip_data_exploration_input() -> None:
    original = DataExplorationInput(
        dataset=_make_dataset_ref(),
        hypotheses=[_make_hypothesis()],
    )
    restored = DataExplorationInput.model_validate(original.model_dump(mode="json"))
    assert restored == original


def _round_trip_data_exploration_output() -> None:
    original = DataExplorationOutput(
        summary_stats={"mean": 128.5, "std": 42.3},
        plots=[_make_artifact_ref(kind="plot", name="hist.png")],
        characterization="Data is roughly gaussian.",
        exec_log=_make_exec_log(),
    )
    restored = DataExplorationOutput.model_validate(original.model_dump(mode="json"))
    assert restored == original


def _round_trip_data_preparation_input() -> None:
    original = DataPreparationInput(
        dataset=_make_dataset_ref(),
        characterization="Roughly gaussian.",
        plan_excerpt="Normalise and augment with random flips.",
    )
    restored = DataPreparationInput.model_validate(original.model_dump(mode="json"))
    assert restored == original


def _round_trip_data_preparation_output() -> None:
    original = DataPreparationOutput(
        prep_script=_make_artifact_ref(kind="script", name="prep.py"),
        splits={
            "train": _make_artifact_ref(kind="split", name="train.npz"),
            "val": _make_artifact_ref(kind="split", name="val.npz"),
            "test": _make_artifact_ref(kind="split", name="test.npz"),
        },
        transforms=["normalise", "random_flip"],
        exec_log=_make_exec_log(),
    )
    restored = DataPreparationOutput.model_validate(original.model_dump(mode="json"))
    assert restored == original


def _round_trip_experimentation_input() -> None:
    original = ExperimentationInput(
        hypotheses=[_make_hypothesis()],
        splits={
            "train": _make_artifact_ref(kind="split", name="train.npz"),
            "val": _make_artifact_ref(kind="split", name="val.npz"),
            "test": _make_artifact_ref(kind="split", name="test.npz"),
        },
        prep_script=_make_artifact_ref(kind="script", name="prep.py"),
    )
    restored = ExperimentationInput.model_validate(original.model_dump(mode="json"))
    assert restored == original


def _round_trip_experimentation_output() -> None:
    original = ExperimentationOutput(
        metrics=[_make_metric()],
        artifacts=[_make_artifact_ref(kind="model", name="model.pt")],
        exec_logs=[_make_exec_log()],
        memory_entries_created=["mem-uuid-1"],
    )
    restored = ExperimentationOutput.model_validate(original.model_dump(mode="json"))
    assert restored == original


def _round_trip_interpretation_input() -> None:
    original = InterpretationInput(
        metrics=[_make_metric()],
        artifacts=[_make_artifact_ref()],
        hypotheses=[_make_hypothesis()],
    )
    restored = InterpretationInput.model_validate(original.model_dump(mode="json"))
    assert restored == original


def _round_trip_interpretation_output() -> None:
    original = InterpretationOutput(
        findings=[_make_finding()],
        confidence_notes=["Results may not generalise to 3D volumes."],
    )
    restored = InterpretationOutput.model_validate(original.model_dump(mode="json"))
    assert restored == original


def _round_trip_report_writing_input() -> None:
    original = ReportWritingInput(
        findings=[_make_finding()],
        citations=[_make_citation()],
        metrics=[_make_metric()],
        methodology="Train ResUNet with 5-fold CV.",
    )
    restored = ReportWritingInput.model_validate(original.model_dump(mode="json"))
    assert restored == original


def _round_trip_report_writing_output_full() -> None:
    """ReportWritingOutput with all optional fields populated."""
    original = ReportWritingOutput(
        report_markdown=_make_artifact_ref(kind="report", name="report.md"),
        report_latex=_make_artifact_ref(kind="report", name="report.tex"),
        report_pdf=_make_artifact_ref(kind="report", name="report.pdf"),
        cited_chunk_ids=["c-1"],
        pandoc_log=_make_exec_log(),
    )
    restored = ReportWritingOutput.model_validate(original.model_dump(mode="json"))
    assert restored == original


def _round_trip_report_writing_output_none_fields() -> None:
    """ReportWritingOutput with report_latex/pdf/pandoc_log all None."""
    original = ReportWritingOutput(
        report_markdown=_make_artifact_ref(kind="report", name="report.md"),
        report_latex=None,
        report_pdf=None,
        cited_chunk_ids=[],
        pandoc_log=None,
    )
    restored = ReportWritingOutput.model_validate(original.model_dump(mode="json"))
    assert restored == original
    assert restored.report_latex is None
    assert restored.report_pdf is None
    assert restored.pandoc_log is None


def _round_trip_peer_review_input() -> None:
    original = PeerReviewInput(
        report_markdown=_make_artifact_ref(kind="report", name="report.md"),
        findings=[_make_finding()],
        metrics=[_make_metric()],
        methodology="Train ResUNet with 5-fold CV.",
    )
    restored = PeerReviewInput.model_validate(original.model_dump(mode="json"))
    assert restored == original


def _round_trip_peer_review_output_with_backtrack() -> None:
    """PeerReviewOutput with a concrete BacktrackSignal."""
    original = PeerReviewOutput(
        critique="The ablation study is missing.",
        action_items=[_make_action_item()],
        recommended_backtrack=_make_backtrack_signal(),
    )
    restored = PeerReviewOutput.model_validate(original.model_dump(mode="json"))
    assert restored == original
    assert restored.recommended_backtrack is not None
    assert restored.recommended_backtrack.target_stage == "plan_formulation"


def _round_trip_peer_review_output_no_backtrack() -> None:
    """PeerReviewOutput with recommended_backtrack=None."""
    original = PeerReviewOutput(
        critique="Report looks good.",
        action_items=[],
        recommended_backtrack=None,
    )
    restored = PeerReviewOutput.model_validate(original.model_dump(mode="json"))
    assert restored == original
    assert restored.recommended_backtrack is None


# ---------------------------------------------------------------------------
# Parametrized round-trip (16 models — two variants for some)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "fn",
    [
        _round_trip_literature_review_input,
        _round_trip_literature_review_output,
        _round_trip_plan_formulation_input,
        _round_trip_plan_formulation_output,
        _round_trip_data_exploration_input,
        _round_trip_data_exploration_output,
        _round_trip_data_preparation_input,
        _round_trip_data_preparation_output,
        _round_trip_experimentation_input,
        _round_trip_experimentation_output,
        _round_trip_interpretation_input,
        _round_trip_interpretation_output,
        _round_trip_report_writing_input,
        _round_trip_report_writing_output_full,
        _round_trip_report_writing_output_none_fields,
        _round_trip_peer_review_input,
        _round_trip_peer_review_output_with_backtrack,
        _round_trip_peer_review_output_no_backtrack,
    ],
    ids=[
        "LiteratureReviewInput",
        "LiteratureReviewOutput",
        "PlanFormulationInput",
        "PlanFormulationOutput",
        "DataExplorationInput",
        "DataExplorationOutput",
        "DataPreparationInput",
        "DataPreparationOutput",
        "ExperimentationInput",
        "ExperimentationOutput",
        "InterpretationInput",
        "InterpretationOutput",
        "ReportWritingInput",
        "ReportWritingOutput_full",
        "ReportWritingOutput_none_fields",
        "PeerReviewInput",
        "PeerReviewOutput_with_backtrack",
        "PeerReviewOutput_no_backtrack",
    ],
)
def test_round_trip(fn: Callable[[], None]) -> None:
    """Every stage I/O model round-trips through model_dump(mode='json') → model_validate."""
    fn()


# ---------------------------------------------------------------------------
# Required-field omission tests — distinct required field per stage
# ---------------------------------------------------------------------------


class _MissingCorpusIdPayload(TypedDict):
    citations: list[Citation]
    summaries: list[CitationSummary]
    # corpus_id intentionally omitted


class _MissingHypothesesPayload(TypedDict):
    methodology: str
    success_criteria: list[str]
    accepted_citation_ids: list[str]
    # hypotheses intentionally omitted


class _MissingSummaryStatsPayload(TypedDict):
    plots: list[ArtifactRef]
    characterization: str
    exec_log: dict[str, int | str]
    # summary_stats intentionally omitted


class _MissingPrepScriptPayload(TypedDict):
    splits: dict[str, ArtifactRef]
    transforms: list[str]
    exec_log: dict[str, int | str]
    # prep_script intentionally omitted


class _MissingMetricsPayload(TypedDict):
    artifacts: list[ArtifactRef]
    exec_logs: list[dict[str, int | str]]
    # metrics intentionally omitted


class _MissingFindingsPayload(TypedDict):
    confidence_notes: list[str]
    # findings intentionally omitted


class _MissingReportMarkdownPayload(TypedDict):
    report_latex: None
    report_pdf: None
    cited_chunk_ids: list[str]
    pandoc_log: None
    # report_markdown intentionally omitted


class _MissingCritiquePayload(TypedDict):
    action_items: list[ActionItem]
    recommended_backtrack: None
    # critique intentionally omitted


@pytest.mark.parametrize(
    ("model_cls", "payload"),
    [
        (
            LiteratureReviewOutput,
            _MissingCorpusIdPayload(
                citations=[],
                summaries=[],
            ),
        ),
        (
            PlanFormulationOutput,
            _MissingHypothesesPayload(
                methodology="some method",
                success_criteria=["criterion-1"],
                accepted_citation_ids=[],
            ),
        ),
        (
            DataExplorationOutput,
            _MissingSummaryStatsPayload(
                plots=[],
                characterization="desc",
                exec_log={"stdout": "", "stderr": "", "exit_code": 0},
            ),
        ),
        (
            DataPreparationOutput,
            _MissingPrepScriptPayload(
                splits={},
                transforms=[],
                exec_log={"stdout": "", "stderr": "", "exit_code": 0},
            ),
        ),
        (
            ExperimentationOutput,
            _MissingMetricsPayload(
                artifacts=[],
                exec_logs=[],
            ),
        ),
        (
            InterpretationOutput,
            _MissingFindingsPayload(
                confidence_notes=[],
            ),
        ),
        (
            ReportWritingOutput,
            _MissingReportMarkdownPayload(
                report_latex=None,
                report_pdf=None,
                cited_chunk_ids=[],
                pandoc_log=None,
            ),
        ),
        (
            PeerReviewOutput,
            _MissingCritiquePayload(
                action_items=[],
                recommended_backtrack=None,
            ),
        ),
    ],
    ids=[
        "LiteratureReviewOutput_missing_corpus_id",
        "PlanFormulationOutput_missing_hypotheses",
        "DataExplorationOutput_missing_summary_stats",
        "DataPreparationOutput_missing_prep_script",
        "ExperimentationOutput_missing_metrics",
        "InterpretationOutput_missing_findings",
        "ReportWritingOutput_missing_report_markdown",
        "PeerReviewOutput_missing_critique",
    ],
)
def test_missing_required_field_raises(model_cls: type[BaseModel], payload: object) -> None:
    """Omitting a required field raises ValidationError."""
    with pytest.raises(ValidationError):
        model_cls.model_validate(payload)


# ---------------------------------------------------------------------------
# ExperimentationOutput — default memory_entries_created + extra fields rejected
# ---------------------------------------------------------------------------


def test_experimentation_output_default_memory_entries() -> None:
    """ExperimentationOutput accepts memory_entries_created=[] by default."""
    out = ExperimentationOutput(
        metrics=[_make_metric()],
        artifacts=[_make_artifact_ref()],
        exec_logs=[_make_exec_log()],
    )
    assert out.memory_entries_created == []


def test_experimentation_output_rejects_extra_fields() -> None:
    """ExperimentationOutput rejects unknown extra fields."""
    with pytest.raises(ValidationError):
        ExperimentationOutput.model_validate(
            {
                "metrics": [{"name": "dice", "value": 0.87, "unit": None}],
                "artifacts": [
                    {
                        "artifact_id": "a-1",
                        "kind": "model",
                        "path": "/workspace/model.pt",
                        "content_hash": "sha256:deadbeef" * 4,
                    }
                ],
                "exec_logs": [{"stdout": "", "stderr": "", "exit_code": 0}],
                "unexpected_field": "boom",
            }
        )


# ---------------------------------------------------------------------------
# ReportWritingOutput — required-no-default fields must be PRESENT
# ---------------------------------------------------------------------------


class _ReportWritingMissingLatexPayload(TypedDict):
    report_markdown: dict[str, str]
    report_pdf: None
    cited_chunk_ids: list[str]
    pandoc_log: None
    # report_latex intentionally omitted


class _ReportWritingMissingPdfPayload(TypedDict):
    report_markdown: dict[str, str]
    report_latex: None
    cited_chunk_ids: list[str]
    pandoc_log: None
    # report_pdf intentionally omitted


class _ReportWritingMissingPandocLogPayload(TypedDict):
    report_markdown: dict[str, str]
    report_latex: None
    report_pdf: None
    cited_chunk_ids: list[str]
    # pandoc_log intentionally omitted


_REPORT_MARKDOWN_DICT: dict[str, str] = {
    "artifact_id": "a-md",
    "kind": "report",
    "path": "/workspace/report.md",
    "content_hash": "sha256:deadbeef" * 4,
}


@pytest.mark.parametrize(
    "payload",
    [
        _ReportWritingMissingLatexPayload(
            report_markdown=_REPORT_MARKDOWN_DICT,
            report_pdf=None,
            cited_chunk_ids=[],
            pandoc_log=None,
        ),
        _ReportWritingMissingPdfPayload(
            report_markdown=_REPORT_MARKDOWN_DICT,
            report_latex=None,
            cited_chunk_ids=[],
            pandoc_log=None,
        ),
        _ReportWritingMissingPandocLogPayload(
            report_markdown=_REPORT_MARKDOWN_DICT,
            report_latex=None,
            report_pdf=None,
            cited_chunk_ids=[],
        ),
    ],
    ids=[
        "missing_report_latex",
        "missing_report_pdf",
        "missing_pandoc_log",
    ],
)
def test_report_writing_output_required_no_default_fields(payload: object) -> None:
    """report_latex, report_pdf, and pandoc_log must be PRESENT (None OK, omission fails)."""
    with pytest.raises(ValidationError):
        ReportWritingOutput.model_validate(payload)


# ---------------------------------------------------------------------------
# PeerReviewOutput — recommended_backtrack must be PRESENT
# ---------------------------------------------------------------------------


class _PeerReviewMissingBacktrackPayload(TypedDict):
    critique: str
    action_items: list[ActionItem]
    # recommended_backtrack intentionally omitted


def test_peer_review_output_recommended_backtrack_required() -> None:
    """PeerReviewOutput rejects payloads that omit recommended_backtrack."""
    with pytest.raises(ValidationError):
        PeerReviewOutput.model_validate(
            _PeerReviewMissingBacktrackPayload(
                critique="Some critique.",
                action_items=[],
            )
        )


def test_peer_review_output_backtrack_signal_round_trips() -> None:
    """BacktrackSignal from agentlabx.stages.protocol round-trips through PeerReviewOutput."""
    signal = BacktrackSignal(
        target_stage="data_exploration",
        reason="Dataset characterization was incomplete.",
        preserve=frozenset(["corpus_id", "citations"]),
    )
    out = PeerReviewOutput(
        critique="The characterization step was skipped.",
        action_items=[],
        recommended_backtrack=signal,
    )
    restored = PeerReviewOutput.model_validate(out.model_dump(mode="json"))
    assert restored.recommended_backtrack is not None
    assert restored.recommended_backtrack.target_stage == "data_exploration"
    assert restored.recommended_backtrack.reason == "Dataset characterization was incomplete."
    assert "corpus_id" in restored.recommended_backtrack.preserve
