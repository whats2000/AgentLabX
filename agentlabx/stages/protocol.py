"""Stage protocol primitives (SRS § stage-contracts, A4 Task 2).

Defines the core abstractions every stage implementation must satisfy:

* :class:`StageContext` — immutable execution context injected by the runner.
* :class:`BacktrackSignal` — a stage returns this to request re-routing.
* :class:`StageOutput` — wraps a stage's successful payload + optional metadata.
* ``StageResult`` — union alias returned by :meth:`Stage.execute`.
* :class:`Stage` — the abstract base class every concrete stage must extend.

Cross-constant validation (``requires_reproducibility`` vs
``STAGE_REPRODUCIBILITY_REQUIRED``, ``backtrack_targets`` subset checks,
capability-tag whitelist) lives in ``Task 5``'s ``StageRegistry.register()``
and is intentionally absent here.
"""

from __future__ import annotations

import abc
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field

from agentlabx.stages.contracts._shared import NoteRef
from agentlabx.stages.reproducibility import ReproducibilityContract

# ---------------------------------------------------------------------------
# JSON value type (recursive, PEP 695)
# ---------------------------------------------------------------------------

type JSONValue = str | int | float | bool | None | list[JSONValue] | dict[str, JSONValue]
"""Strict JSON value type alias used wherever ``dict[str, Any]`` would appear.

Using a recursive PEP 695 ``type`` statement avoids ``Any`` while remaining
mypy-clean under ``--strict``.
"""

# ---------------------------------------------------------------------------
# Execution context
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class StageContext:
    """Immutable execution context injected by the stage runner.

    Carries identifiers, the run mode, and two injectable callables so that
    stages remain side-effect-free with respect to external state.  No service
    handles (LLM, MCP, RAG) are present here — those arrive in A6.

    Attributes:
        run_id: UUID of the top-level experiment run.
        project_id: UUID of the owning project.
        stage_run_id: UUID of this specific stage invocation.
        identity_id: UUID of the user initiating the run (VARCHAR(36) in A1).
        run_mode: ``"auto"`` for fully-automated runs; ``"hitl"`` for
            human-in-the-loop runs where confirmation gates may fire.
        emit_event: Async callable ``(event_kind, payload) → None``; the
            runner wires this to the event bus.  Payload values must be
            JSON-serialisable (enforced by the :data:`JSONValue` type).
        now: Callable that returns the current UTC datetime; injectable for
            deterministic testing.
    """

    run_id: str
    project_id: str
    stage_run_id: str
    identity_id: str
    run_mode: Literal["auto", "hitl"]
    emit_event: Callable[[str, dict[str, JSONValue]], Awaitable[None]]
    now: Callable[[], datetime]


# ---------------------------------------------------------------------------
# Backtrack signal
# ---------------------------------------------------------------------------


class BacktrackSignal(BaseModel):  # type: ignore[explicit-any]
    """Returned by a stage that needs the runner to re-route to an earlier stage.

    A stage should return this instead of raising when the re-route is a
    normal operational decision (e.g. the hypothesis is invalid, restart from
    planning).  Exceptional conditions (bugs, contract violations) must raise.

    Attributes:
        target_stage: ``stage_name`` of the stage to jump back to.
        reason: Human-readable explanation; must be non-empty.
        preserve: Keys from the current run's scratchpad to carry forward.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    target_stage: str
    reason: str = Field(min_length=1)
    preserve: frozenset[str] = frozenset()


# ---------------------------------------------------------------------------
# Stage output
# ---------------------------------------------------------------------------


class StageOutput[OutputT: BaseModel](BaseModel):  # type: ignore[explicit-any]
    """Successful result envelope returned by a stage.

    Attributes:
        payload: The concrete output value; its type is bound at subclass time.
        reproducibility: Optional reproducibility contract; required by stages
            that set ``requires_reproducibility = True`` (enforced at
            registration in Task 5, not here).
        notes: Ordered list of note references produced during this stage run.
            The A7 annotation system populates these; stages may leave the
            list empty.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    payload: OutputT
    reproducibility: ReproducibilityContract | None = None
    notes: list[NoteRef] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# StageResult — PEP 695 type alias
# ---------------------------------------------------------------------------

type StageResult[OutputT: BaseModel] = StageOutput[OutputT] | BacktrackSignal
"""Union of the two possible return values from :meth:`Stage.execute`.

A stage either:
* Returns a :class:`StageOutput` carrying the successful payload, or
* Returns a :class:`BacktrackSignal` requesting re-routing to an earlier stage.
"""

# ---------------------------------------------------------------------------
# Stage ABC
# ---------------------------------------------------------------------------


class Stage[InputT: BaseModel, OutputT: BaseModel](abc.ABC):
    """Abstract base class every concrete stage must extend.

    Structural ClassVar requirements (checked at class-definition time by
    :meth:`__init_subclass__`):

    * ``stage_name`` — non-empty :class:`str` identifier, unique within a
      registry.
    * ``input_model`` — the :class:`~pydantic.BaseModel` subclass that
      validates incoming payloads.
    * ``output_model`` — the :class:`~pydantic.BaseModel` subclass the stage
      promises to return.
    * ``backtrack_targets`` — :class:`frozenset` of ``stage_name`` strings
      this stage may backtrack to (may be empty; cross-registry subset check
      lives in Task 5).

    Optional ClassVars (have sensible defaults):

    * ``required_capabilities`` — per-stage union of capability tags this
      stage needs granted.  A8 narrows per-(agent, stage) at LLM-call time.
    * ``requires_reproducibility`` — if ``True``, the runner's Task 5
      ``register()`` cross-checks against ``STAGE_REPRODUCIBILITY_REQUIRED``.
      The field is declarative only; no validator reads it here.
    """

    stage_name: ClassVar[str]
    input_model: ClassVar[type[BaseModel]]
    output_model: ClassVar[type[BaseModel]]
    backtrack_targets: ClassVar[frozenset[str]]

    required_capabilities: ClassVar[frozenset[str]] = frozenset()
    """Per-stage union of capability tags.

    A8 narrows per-(agent, stage) at LLM-call time.
    """

    requires_reproducibility: ClassVar[bool] = False
    """Declarative flag; Task 5's ``StageRegistry.register()`` cross-checks
    this against ``STAGE_REPRODUCIBILITY_REQUIRED``.  No validator reads it
    here.
    """

    def __init_subclass__(cls, **kwargs: object) -> None:
        """Validate structural ClassVar presence and types at class creation.

        Raises:
            StageContractMismatchError: If any of the four required ClassVars
                is missing or has the wrong type.  Cross-constant validation
                lives in Task 5.
        """
        super().__init_subclass__(**kwargs)
        _validate_stage_classvars(cls)

    @abc.abstractmethod
    async def execute(
        self,
        payload: InputT,
        ctx: StageContext,
    ) -> StageResult[OutputT]:
        """Execute this stage and return either a payload or a backtrack signal.

        Args:
            payload: Validated input; its runtime type is ``input_model``.
            ctx: Immutable execution context supplied by the runner.

        Returns:
            :class:`StageOutput` on success or :class:`BacktrackSignal` on
            re-route request.
        """


def _validate_stage_classvars(cls: type) -> None:
    """Perform structural-only ClassVar validation for a :class:`Stage` subclass.

    Checks the four *required* ClassVars:

    1. ``stage_name`` is a non-empty :class:`str`.
    2. ``input_model`` is a :class:`~pydantic.BaseModel` subclass.
    3. ``output_model`` is a :class:`~pydantic.BaseModel` subclass.
    4. ``backtrack_targets`` is a :class:`frozenset`.

    Cross-constant checks are intentionally absent and live in Task 5.

    Raises:
        StageContractMismatchError: On any structural violation.
    """
    # stage_name
    stage_name = cls.__dict__.get("stage_name", _MISSING)
    if stage_name is _MISSING:
        # Also check via class attribute (inherited) — but we want concrete
        # classes to define their own, so check __dict__ first.
        stage_name = getattr(cls, "stage_name", _MISSING)
    if stage_name is _MISSING:
        raise StageContractMismatchError(
            cls.__name__,
            "stage_name",
            "missing; every concrete Stage subclass must define stage_name: ClassVar[str]",
        )
    if not isinstance(stage_name, str) or not stage_name:
        raise StageContractMismatchError(
            cls.__name__,
            "stage_name",
            f"must be a non-empty str, got {stage_name!r}",
        )

    # input_model
    input_model = getattr(cls, "input_model", _MISSING)
    if input_model is _MISSING:
        raise StageContractMismatchError(
            cls.__name__,
            "input_model",
            "missing; every concrete Stage subclass must define"
            " input_model: ClassVar[type[BaseModel]]",
        )
    if not (isinstance(input_model, type) and issubclass(input_model, BaseModel)):
        raise StageContractMismatchError(
            cls.__name__,
            "input_model",
            f"must be a BaseModel subclass (type), got {input_model!r}",
        )

    # output_model
    output_model = getattr(cls, "output_model", _MISSING)
    if output_model is _MISSING:
        raise StageContractMismatchError(
            cls.__name__,
            "output_model",
            "missing; every concrete Stage subclass must define"
            " output_model: ClassVar[type[BaseModel]]",
        )
    if not (isinstance(output_model, type) and issubclass(output_model, BaseModel)):
        raise StageContractMismatchError(
            cls.__name__,
            "output_model",
            f"must be a BaseModel subclass (type), got {output_model!r}",
        )

    # backtrack_targets
    backtrack_targets = getattr(cls, "backtrack_targets", _MISSING)
    if backtrack_targets is _MISSING:
        raise StageContractMismatchError(
            cls.__name__,
            "backtrack_targets",
            "missing; every concrete Stage subclass must define"
            " backtrack_targets: ClassVar[frozenset[str]]",
        )
    if not isinstance(backtrack_targets, frozenset):
        raise StageContractMismatchError(
            cls.__name__,
            "backtrack_targets",
            f"must be a frozenset, got {type(backtrack_targets).__name__!r}",
        )


# Sentinel for missing ClassVar (avoids shadowing builtins).
_MISSING: object = object()


# ---------------------------------------------------------------------------
# Exception hierarchy
# ---------------------------------------------------------------------------


class StageError(Exception):
    """Base class for all stage-protocol errors."""


class StageContractMismatchError(StageError):
    """Raised when a :class:`Stage` subclass violates a structural contract rule.

    Emitted by :meth:`Stage.__init_subclass__` when a required ClassVar is
    missing or has an incorrect type.  Cross-constant violations are reported
    by ``StageRegistry.register()`` in Task 5.

    Args:
        stage_cls_name: The ``__name__`` of the offending class.
        rule_violated: The name of the ClassVar or rule that was broken.
        detail: Human-readable explanation of the violation.
    """

    def __init__(self, stage_cls_name: str, rule_violated: str, detail: str) -> None:
        super().__init__(
            f"Stage contract violation in {stage_cls_name!r}: {rule_violated} — {detail}"
        )
        self.stage_cls_name = stage_cls_name
        self.rule_violated = rule_violated
        self.detail = detail


class StageValidationError(StageError):
    """Raised when a stage's input or output payload fails Pydantic validation.

    Wraps the underlying :class:`~pydantic.ValidationError` with stage-level
    context so callers can distinguish payload problems from contract problems.

    Args:
        stage_name: The ``stage_name`` ClassVar of the offending stage.
        direction: ``"input"`` or ``"output"``.
        detail: Human-readable description of the validation failure.
    """

    def __init__(self, stage_name: str, direction: str, detail: str) -> None:
        super().__init__(f"Stage {stage_name!r} {direction} validation failed: {detail}")
        self.stage_name = stage_name
        self.direction = direction
        self.detail = detail


class BacktrackTargetError(StageError):
    """Raised when a :class:`BacktrackSignal` names an invalid target stage.

    The runner emits this when ``BacktrackSignal.target_stage`` is not
    registered or not listed in the returning stage's ``backtrack_targets``.
    Structural *subset* validation happens in Task 5; this exception is used
    at runtime by the runner.

    Args:
        source_stage: The stage that emitted the signal.
        target_stage: The requested target stage name.
        detail: Human-readable explanation.
    """

    def __init__(self, source_stage: str, target_stage: str, detail: str) -> None:
        super().__init__(f"Invalid backtrack from {source_stage!r} to {target_stage!r}: {detail}")
        self.source_stage = source_stage
        self.target_stage = target_stage
        self.detail = detail


__all__ = [
    "BacktrackSignal",
    "BacktrackTargetError",
    "JSONValue",
    "NoteRef",
    "Stage",
    "StageContractMismatchError",
    "StageContext",
    "StageError",
    "StageOutput",
    "StageResult",
    "StageValidationError",
]
