"""Tests for agentlabx.stages.protocol — Stage protocol primitives (A4 Task 2)."""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime
from typing import ClassVar

import pytest
from pydantic import BaseModel, ValidationError

from agentlabx.stages.protocol import (
    BacktrackSignal,
    BacktrackTargetError,
    JSONValue,
    Stage,
    StageContext,
    StageContractMismatchError,
    StageOutput,
    StageValidationError,
)

# ---------------------------------------------------------------------------
# Helpers — minimal BaseModel stubs for tests
# ---------------------------------------------------------------------------


class _InputModel(BaseModel):  # type: ignore[explicit-any]
    x: int


class _OutputModel(BaseModel):  # type: ignore[explicit-any]
    y: str


class _X(BaseModel):  # type: ignore[explicit-any]
    """Minimal model used in StageOutput round-trip test."""

    a: int


# ---------------------------------------------------------------------------
# Helpers — valid Stage subclass and context factory
# ---------------------------------------------------------------------------


def _make_ctx() -> StageContext:
    """Return a minimal valid StageContext."""

    async def _noop_emit(kind: str, payload: dict[str, JSONValue]) -> None:  # noqa: ARG001
        return

    return StageContext(
        run_id="run-1",
        project_id="proj-1",
        stage_run_id="srun-1",
        identity_id="id-1",
        run_mode="auto",
        emit_event=_noop_emit,
        now=lambda: datetime.now(UTC),
    )


class _ValidStage(Stage[_InputModel, _OutputModel]):
    """A well-formed Stage subclass for use in tests that need a live instance."""

    stage_name: ClassVar[str] = "valid_stage"
    input_model: ClassVar[type[BaseModel]] = _InputModel
    output_model: ClassVar[type[BaseModel]] = _OutputModel
    backtrack_targets: ClassVar[frozenset[str]] = frozenset()

    async def execute(
        self,
        payload: _InputModel,
        ctx: StageContext,
    ) -> StageOutput[_OutputModel]:
        return StageOutput(payload=_OutputModel(y=str(payload.x)))


# ---------------------------------------------------------------------------
# __init_subclass__ structural validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "missing_classvar",
    ["stage_name", "input_model", "output_model", "backtrack_targets"],
)
def test_missing_classvar_raises_contract_error(missing_classvar: str) -> None:
    """Omitting any required ClassVar must raise StageContractMismatchError at class creation."""
    classvars: dict[str, object] = {
        "stage_name": "test_stage",
        "input_model": _InputModel,
        "output_model": _OutputModel,
        "backtrack_targets": frozenset[str](),
    }
    # Remove the ClassVar under test.
    del classvars[missing_classvar]

    # Dynamically add the execute abstract method so it's a concrete class.
    async def execute(
        self: object,
        payload: object,
        ctx: StageContext,
    ) -> StageOutput[_OutputModel]:
        return StageOutput(payload=_OutputModel(y=""))

    classvars["execute"] = execute

    with pytest.raises(StageContractMismatchError) as exc_info:
        type(
            f"_Bad_{missing_classvar}",
            (Stage,),
            classvars,
        )

    # The error message must name the violated rule.
    assert missing_classvar in str(exc_info.value)


def test_stage_name_empty_string_raises() -> None:
    """stage_name must be non-empty."""
    with pytest.raises(StageContractMismatchError) as exc_info:

        class _EmptyName(Stage[_InputModel, _OutputModel]):
            stage_name: ClassVar[str] = ""
            input_model: ClassVar[type[BaseModel]] = _InputModel
            output_model: ClassVar[type[BaseModel]] = _OutputModel
            backtrack_targets: ClassVar[frozenset[str]] = frozenset()

            async def execute(
                self,
                payload: _InputModel,
                ctx: StageContext,
            ) -> StageOutput[_OutputModel]:
                return StageOutput(payload=_OutputModel(y=""))

    assert "stage_name" in str(exc_info.value)


def test_input_model_non_basemodel_raises() -> None:
    """input_model must be a BaseModel subclass."""
    with pytest.raises(StageContractMismatchError) as exc_info:

        class _BadInput(Stage[_InputModel, _OutputModel]):
            stage_name: ClassVar[str] = "bad_input"
            input_model: ClassVar[type[BaseModel]] = str  # type: ignore[assignment]
            output_model: ClassVar[type[BaseModel]] = _OutputModel
            backtrack_targets: ClassVar[frozenset[str]] = frozenset()

            async def execute(
                self,
                payload: _InputModel,
                ctx: StageContext,
            ) -> StageOutput[_OutputModel]:
                return StageOutput(payload=_OutputModel(y=""))

    assert "input_model" in str(exc_info.value)


def test_backtrack_targets_non_frozenset_raises() -> None:
    """backtrack_targets must be a frozenset."""
    with pytest.raises(StageContractMismatchError) as exc_info:

        class _BadTargets(Stage[_InputModel, _OutputModel]):
            stage_name: ClassVar[str] = "bad_targets"
            input_model: ClassVar[type[BaseModel]] = _InputModel
            output_model: ClassVar[type[BaseModel]] = _OutputModel
            backtrack_targets: ClassVar[frozenset[str]] = set()  # type: ignore[assignment]

            async def execute(
                self,
                payload: _InputModel,
                ctx: StageContext,
            ) -> StageOutput[_OutputModel]:
                return StageOutput(payload=_OutputModel(y=""))

    assert "backtrack_targets" in str(exc_info.value)


# ---------------------------------------------------------------------------
# StageContext — frozen + hashable
# ---------------------------------------------------------------------------


def test_stage_context_is_frozen() -> None:
    """Mutating a StageContext field must raise FrozenInstanceError."""
    ctx = _make_ctx()
    with pytest.raises(dataclasses.FrozenInstanceError):
        ctx.run_id = "mutated"  # type: ignore[misc]


def test_stage_context_is_hashable() -> None:
    """StageContext must be usable as a dict key / set member (slots=True dataclass)."""
    ctx = _make_ctx()
    # Dataclasses with frozen=True and slots=True are hashable by default.
    d: dict[StageContext, str] = {ctx: "value"}
    assert d[ctx] == "value"


# ---------------------------------------------------------------------------
# BacktrackSignal — validation
# ---------------------------------------------------------------------------


def test_backtrack_signal_empty_reason_raises() -> None:
    """reason="" must raise ValidationError (Field min_length=1)."""
    with pytest.raises(ValidationError):
        BacktrackSignal(target_stage="x", reason="")


def test_backtrack_signal_round_trip() -> None:
    """BacktrackSignal round-trips through model_dump(mode='json') → model_validate."""
    signal = BacktrackSignal(
        target_stage="x",
        reason="rebuild",
        preserve=frozenset({"key_a", "key_b"}),
    )
    dumped = signal.model_dump(mode="json")
    restored = BacktrackSignal.model_validate(dumped)
    assert restored == signal
    assert isinstance(restored.preserve, frozenset)


def test_backtrack_signal_extra_field_raises() -> None:
    """extra='forbid' must reject unrecognised fields."""
    with pytest.raises(ValidationError):
        BacktrackSignal.model_validate({"target_stage": "x", "reason": "ok", "unexpected": "boom"})


def test_backtrack_signal_frozen_rejects_mutation() -> None:
    """BacktrackSignal is frozen; mutation must raise ValidationError."""
    signal = BacktrackSignal(target_stage="x", reason="ok")
    with pytest.raises(ValidationError):
        signal.reason = "changed"  # noqa: B010


# ---------------------------------------------------------------------------
# StageOutput — generic round-trip
# ---------------------------------------------------------------------------


def test_stage_output_round_trip() -> None:
    """StageOutput[_X] round-trips through model_dump(mode='json') → model_validate."""
    output: StageOutput[_X] = StageOutput(payload=_X(a=42))
    dumped = output.model_dump(mode="json")
    restored: StageOutput[_X] = StageOutput[_X].model_validate(dumped)
    assert restored.payload.a == 42
    assert restored.reproducibility is None
    assert restored.notes == []


def test_stage_output_with_notes_round_trip() -> None:
    """StageOutput with NoteRef entries round-trips correctly."""
    from agentlabx.stages.contracts._shared import NoteRef

    note = NoteRef(id="n1", category="finding")
    output: StageOutput[_X] = StageOutput(payload=_X(a=7), notes=[note])
    dumped = output.model_dump(mode="json")
    restored: StageOutput[_X] = StageOutput[_X].model_validate(dumped)
    assert len(restored.notes) == 1
    assert restored.notes[0].id == "n1"
    assert restored.notes[0].category == "finding"


# ---------------------------------------------------------------------------
# Exception hierarchy
# ---------------------------------------------------------------------------


def test_exception_hierarchy() -> None:
    """All three concrete exceptions are subclasses of StageError."""
    from agentlabx.stages.protocol import StageError

    assert issubclass(StageContractMismatchError, StageError)
    assert issubclass(StageValidationError, StageError)
    assert issubclass(BacktrackTargetError, StageError)


def test_stage_contract_mismatch_error_message() -> None:
    """StageContractMismatchError includes class name, rule, and detail."""
    err = StageContractMismatchError("MyStage", "stage_name", "missing")
    assert "MyStage" in str(err)
    assert "stage_name" in str(err)
    assert "missing" in str(err)


def test_stage_validation_error_message() -> None:
    """StageValidationError includes stage name, direction, and detail."""
    err = StageValidationError("my_stage", "input", "field x required")
    assert "my_stage" in str(err)
    assert "input" in str(err)
    assert "field x required" in str(err)


def test_backtrack_target_error_message() -> None:
    """BacktrackTargetError includes source, target, and detail."""
    err = BacktrackTargetError("source_stage", "target_stage", "not registered")
    assert "source_stage" in str(err)
    assert "target_stage" in str(err)
    assert "not registered" in str(err)
