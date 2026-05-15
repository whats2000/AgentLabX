"""Tests for echo stage stubs (A4 Tasks 7+8).

Coverage:
1. Each EchoStage produces a valid output per validate_output.
2. Each EchoStage registers cleanly via StageRegistry.
3. Determinism — two calls with the same input produce equal outputs.
4. Event emission — stage.echo.completed emitted exactly once with the right payload.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

import pytest
from pydantic import BaseModel

from agentlabx.stages.contracts._shared import (
    ArtifactRef,
    Citation,
    DatasetRef,
    ExecLog,
    Finding,
    Hypothesis,
    Metric,
    ResearchQuestion,
)
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
from agentlabx.stages.registry import STAGE_NAMES, StageRegistry
from agentlabx.stages.reproducibility import ReproducibilityContract
from agentlabx.stages.validator import validate_output

# ---------------------------------------------------------------------------
# Fake event recorder and StageContext factory
# ---------------------------------------------------------------------------


@dataclass
class _EventRecorder:
    """Records (kind, payload) pairs from emit_event calls."""

    events: list[tuple[str, dict[str, JSONValue]]] = field(default_factory=list)

    async def emit_event(self, kind: str, payload: dict[str, JSONValue]) -> None:
        self.events.append((kind, payload))


def _make_ctx() -> StageContext:
    """Build a silent (discarding) StageContext."""

    async def _noop(kind: str, payload: dict[str, JSONValue]) -> None:  # noqa: ARG001
        pass

    return StageContext(
        run_id="run-echo-1",
        project_id="proj-echo-1",
        stage_run_id="stage-run-echo-1",
        identity_id="user-echo-1",
        run_mode="auto",
        emit_event=_noop,
        now=lambda: datetime.now(UTC),
    )


def _make_recording_ctx() -> tuple[StageContext, _EventRecorder]:
    """Build a StageContext backed by an EventRecorder."""
    recorder = _EventRecorder()
    ctx = StageContext(
        run_id="run-echo-1",
        project_id="proj-echo-1",
        stage_run_id="stage-run-echo-1",
        identity_id="user-echo-1",
        run_mode="auto",
        emit_event=recorder.emit_event,
        now=lambda: datetime.now(UTC),
    )
    return ctx, recorder


# ---------------------------------------------------------------------------
# Minimal input constructors (one per stage)
# ---------------------------------------------------------------------------


def _make_question() -> ResearchQuestion:
    return ResearchQuestion(text="Does X improve Y?", project_id="proj-1")


def _make_hypothesis() -> Hypothesis:
    return Hypothesis(
        id="h-1",
        statement="X improves Y.",
        baselines=["baseline-A"],
        ablations=["ablation-A"],
    )


def _make_citation() -> Citation:
    return Citation(
        paper_id="echo-cite-1",
        title="Echo Citation",
        authors=["Author One"],
        year=2025,
        source="other",
        url=None,
    )


def _make_dataset_ref() -> DatasetRef:
    return DatasetRef(dataset_id="ds-echo", name="EchoDataset", split_hint=None)


def _make_artifact_ref(
    kind: Literal["dataset", "split", "script", "model", "report", "plot", "table", "other"],
    artifact_id: str = "a-1",
) -> ArtifactRef:
    return ArtifactRef(
        artifact_id=artifact_id,
        kind=kind,
        path=f"/tmp/echo/{artifact_id}",
        content_hash="0" * 64,
    )


def _make_exec_log() -> ExecLog:
    return ExecLog(stdout="ok", stderr="", exit_code=0)


def _make_metric() -> Metric:
    return Metric(name="accuracy", value=0.9, unit=None)


def _make_finding() -> Finding:
    return Finding(
        id="f-1",
        statement="Finding one.",
        cited_metric_names=["accuracy"],
        cited_artifact_ids=["a-1"],
        verbatim_values={"accuracy": 0.9},
        cited_chunk_ids=[],
    )


def _make_literature_review_input() -> LiteratureReviewInput:
    return LiteratureReviewInput(
        question=_make_question(),
        prior_corpus_ids=[],
        target_count_min=3,
    )


def _make_plan_formulation_input() -> PlanFormulationInput:
    return PlanFormulationInput(
        citations=[_make_citation()],
        corpus_id="corp-echo-1",
        question=_make_question(),
    )


def _make_data_exploration_input() -> DataExplorationInput:
    return DataExplorationInput(
        dataset=_make_dataset_ref(),
        hypotheses=[_make_hypothesis()],
    )


def _make_data_preparation_input() -> DataPreparationInput:
    return DataPreparationInput(
        dataset=_make_dataset_ref(),
        characterization="Roughly uniform.",
        plan_excerpt="Normalise and split.",
    )


def _make_experimentation_input() -> ExperimentationInput:
    return ExperimentationInput(
        hypotheses=[_make_hypothesis()],
        splits={
            "train": _make_artifact_ref(kind="split", artifact_id="split-train"),
            "val": _make_artifact_ref(kind="split", artifact_id="split-val"),
        },
        prep_script=_make_artifact_ref(kind="script", artifact_id="prep-script"),
    )


def _make_interpretation_input() -> InterpretationInput:
    return InterpretationInput(
        metrics=[_make_metric()],
        artifacts=[_make_artifact_ref(kind="model")],
        hypotheses=[_make_hypothesis()],
    )


def _make_report_writing_input() -> ReportWritingInput:
    return ReportWritingInput(
        findings=[_make_finding()],
        citations=[_make_citation()],
        metrics=[_make_metric()],
        methodology="Train baseline.",
    )


def _make_peer_review_input() -> PeerReviewInput:
    return PeerReviewInput(
        report_markdown=_make_artifact_ref(kind="report", artifact_id="report-md"),
        findings=[_make_finding()],
        metrics=[_make_metric()],
        methodology="Train baseline.",
    )


# ---------------------------------------------------------------------------
# Parametrize helpers
#
# Mypy invariance note: Stage[ConcreteIn, ConcreteOut] is NOT a subtype of
# Stage[BaseModel, BaseModel] due to invariance, so we store the concrete
# Input types separately and access the class via a typed tuple.  The
# parametrized test functions receive `BaseModel` for the input arg since
# pytest injects by position, not by type, and the runtime types are correct.
# ---------------------------------------------------------------------------

_STAGE_PARAMS: list[tuple[str, BaseModel]] = [
    ("literature_review", _make_literature_review_input()),
    ("plan_formulation", _make_plan_formulation_input()),
    ("data_exploration", _make_data_exploration_input()),
    ("data_preparation", _make_data_preparation_input()),
    ("experimentation", _make_experimentation_input()),
    ("interpretation", _make_interpretation_input()),
    ("report_writing", _make_report_writing_input()),
    ("peer_review", _make_peer_review_input()),
]

_STAGE_IDS: list[str] = [name for name, _ in _STAGE_PARAMS]

# Ordered list of concrete echo classes (matches _STAGE_PARAMS order exactly)
_ECHO_CLASSES: list[
    type[EchoLiteratureReviewStage]
    | type[EchoPlanFormulationStage]
    | type[EchoDataExplorationStage]
    | type[EchoDataPreparationStage]
    | type[EchoExperimentationStage]
    | type[EchoInterpretationStage]
    | type[EchoReportWritingStage]
    | type[EchoPeerReviewStage]
] = [
    EchoLiteratureReviewStage,
    EchoPlanFormulationStage,
    EchoDataExplorationStage,
    EchoDataPreparationStage,
    EchoExperimentationStage,
    EchoInterpretationStage,
    EchoReportWritingStage,
    EchoPeerReviewStage,
]

# Combine for parametrize — each item is (echo_cls, stage_name, stage_input)
_STAGE_FIXTURES: list[
    tuple[
        type[EchoLiteratureReviewStage]
        | type[EchoPlanFormulationStage]
        | type[EchoDataExplorationStage]
        | type[EchoDataPreparationStage]
        | type[EchoExperimentationStage]
        | type[EchoInterpretationStage]
        | type[EchoReportWritingStage]
        | type[EchoPeerReviewStage],
        str,
        BaseModel,
    ]
] = [(cls, name, inp) for cls, (name, inp) in zip(_ECHO_CLASSES, _STAGE_PARAMS, strict=True)]


# ---------------------------------------------------------------------------
# Section 1: validate_output round-trip (all 8 stages)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("stage_cls", "stage_name", "stage_input"),
    _STAGE_FIXTURES,
    ids=_STAGE_IDS,
)
@pytest.mark.asyncio
async def test_echo_stage_produces_valid_output(
    stage_cls: type[EchoLiteratureReviewStage]
    | type[EchoPlanFormulationStage]
    | type[EchoDataExplorationStage]
    | type[EchoDataPreparationStage]
    | type[EchoExperimentationStage]
    | type[EchoInterpretationStage]
    | type[EchoReportWritingStage]
    | type[EchoPeerReviewStage],
    stage_name: str,
    stage_input: BaseModel,
) -> None:
    """Each EchoStage produces a valid output that passes validate_output."""
    ctx = _make_ctx()
    instance = stage_cls()
    result = await instance.execute(stage_input, ctx)  # type: ignore[arg-type]

    assert isinstance(result, StageOutput), f"{stage_cls.__name__} must return StageOutput"

    repro_dict: dict[str, JSONValue] | None = None
    if result.reproducibility is not None:
        repro_dict = result.reproducibility.model_dump(mode="json")

    validated = validate_output(
        stage_name,
        result.payload.model_dump(mode="json"),
        repro_dict,
    )
    assert isinstance(validated, StageOutput)

    # Reproducibility only on stages that declare requires_reproducibility = True
    if stage_cls.requires_reproducibility:
        assert result.reproducibility is not None, f"{stage_cls.__name__} must have reproducibility"
        assert isinstance(result.reproducibility, ReproducibilityContract)
    else:
        assert result.reproducibility is None, (
            f"{stage_cls.__name__} must not return reproducibility"
        )


# ---------------------------------------------------------------------------
# Section 2: StageRegistry.register succeeds for every echo stub
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("stage_cls", "stage_name", "stage_input"),
    _STAGE_FIXTURES,
    ids=_STAGE_IDS,
)
def test_echo_stage_registers_cleanly(
    stage_cls: type[EchoLiteratureReviewStage]
    | type[EchoPlanFormulationStage]
    | type[EchoDataExplorationStage]
    | type[EchoDataPreparationStage]
    | type[EchoExperimentationStage]
    | type[EchoInterpretationStage]
    | type[EchoReportWritingStage]
    | type[EchoPeerReviewStage],
    stage_name: str,
    stage_input: BaseModel,
) -> None:
    """Each EchoStage registers in a fresh StageRegistry without raising."""
    registry = StageRegistry()
    registry.register(stage_cls)  # type: ignore[misc]  # mypy cannot unify the union of concrete Echo* class types to type[Stage[BaseModel, BaseModel]]
    impls = registry.implementations_for(stage_cls.stage_name)
    assert stage_cls in impls


# ---------------------------------------------------------------------------
# Section 3: Determinism
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("stage_cls", "stage_name", "stage_input"),
    _STAGE_FIXTURES,
    ids=_STAGE_IDS,
)
@pytest.mark.asyncio
async def test_echo_stage_is_deterministic(
    stage_cls: type[EchoLiteratureReviewStage]
    | type[EchoPlanFormulationStage]
    | type[EchoDataExplorationStage]
    | type[EchoDataPreparationStage]
    | type[EchoExperimentationStage]
    | type[EchoInterpretationStage]
    | type[EchoReportWritingStage]
    | type[EchoPeerReviewStage],
    stage_name: str,
    stage_input: BaseModel,
) -> None:
    """Calling execute twice with the same input produces equal payloads."""
    ctx1 = _make_ctx()
    ctx2 = _make_ctx()
    instance = stage_cls()

    result1 = await instance.execute(stage_input, ctx1)  # type: ignore[arg-type]
    result2 = await instance.execute(stage_input, ctx2)  # type: ignore[arg-type]

    assert isinstance(result1, StageOutput)
    assert isinstance(result2, StageOutput)
    assert result1.payload.model_dump(mode="json") == result2.payload.model_dump(mode="json"), (
        f"{stage_cls.__name__} must be deterministic"
    )


# ---------------------------------------------------------------------------
# Section 4: Event emission
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("stage_cls", "stage_name", "stage_input"),
    _STAGE_FIXTURES,
    ids=_STAGE_IDS,
)
@pytest.mark.asyncio
async def test_echo_stage_emits_one_event(
    stage_cls: type[EchoLiteratureReviewStage]
    | type[EchoPlanFormulationStage]
    | type[EchoDataExplorationStage]
    | type[EchoDataPreparationStage]
    | type[EchoExperimentationStage]
    | type[EchoInterpretationStage]
    | type[EchoReportWritingStage]
    | type[EchoPeerReviewStage],
    stage_name: str,
    stage_input: BaseModel,
) -> None:
    """Each execute emits exactly one stage.echo.completed event with the right stage_name."""
    ctx, recorder = _make_recording_ctx()
    instance = stage_cls()

    result = await instance.execute(stage_input, ctx)  # type: ignore[arg-type]

    assert isinstance(result, StageOutput)
    assert len(recorder.events) == 1, (
        f"{stage_cls.__name__} must emit exactly 1 event, got {len(recorder.events)}"
    )
    kind, payload = recorder.events[0]
    assert kind == "stage.echo.completed", (
        f"Expected event kind 'stage.echo.completed', got {kind!r}"
    )
    assert payload == {"stage_name": stage_name}, (
        f"Expected {{'stage_name': {stage_name!r}}}, got {payload!r}"
    )


# ---------------------------------------------------------------------------
# Section 5: ClassVar integrity checks (direct class access — no loop ambiguity)
# ---------------------------------------------------------------------------


class TestEchoStageClassVars:
    """Structural checks on ClassVar values for all 8 echo stubs."""

    def test_requires_reproducibility_only_on_experimentation(self) -> None:
        """Only EchoExperimentationStage has requires_reproducibility=True."""
        assert EchoLiteratureReviewStage.requires_reproducibility is False
        assert EchoPlanFormulationStage.requires_reproducibility is False
        assert EchoDataExplorationStage.requires_reproducibility is False
        assert EchoDataPreparationStage.requires_reproducibility is False
        assert EchoExperimentationStage.requires_reproducibility is True
        assert EchoInterpretationStage.requires_reproducibility is False
        assert EchoReportWritingStage.requires_reproducibility is False
        assert EchoPeerReviewStage.requires_reproducibility is False

    def test_backtrack_targets_are_frozensets(self) -> None:
        for cls in _ECHO_CLASSES:
            assert isinstance(cls.backtrack_targets, frozenset), (
                f"{cls.__name__}.backtrack_targets must be frozenset"
            )

    def test_required_capabilities_are_frozensets(self) -> None:
        for cls in _ECHO_CLASSES:
            assert isinstance(cls.required_capabilities, frozenset), (
                f"{cls.__name__}.required_capabilities must be frozenset"
            )

    def test_literature_review_backtrack_targets_empty(self) -> None:
        assert EchoLiteratureReviewStage.backtrack_targets == frozenset()

    def test_experimentation_backtrack_targets(self) -> None:
        assert EchoExperimentationStage.backtrack_targets == frozenset(
            {"plan_formulation", "data_preparation", "data_exploration"}
        )

    def test_peer_review_backtrack_targets_all_prior(self) -> None:
        expected = frozenset(set(STAGE_NAMES) - {"peer_review"})
        assert EchoPeerReviewStage.backtrack_targets == expected

    def test_all_stage_names_canonical(self) -> None:
        for cls in _ECHO_CLASSES:
            assert cls.stage_name in STAGE_NAMES, (
                f"{cls.__name__}.stage_name {cls.stage_name!r} not in STAGE_NAMES"
            )
