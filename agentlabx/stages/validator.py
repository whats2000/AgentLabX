"""Contract-driven stage I/O and backtrack validation (A4 Task 6).

Contract-driven validation: this module reads canonical constants in
``registry.py`` and never queries the registered Stage subclass.

Pure functions only — no classes, no module-level state.  All enforcement
is derived exclusively from the canonical constants:

* :data:`~agentlabx.stages.registry.CANONICAL_CONTRACTS`
* :data:`~agentlabx.stages.registry.STAGE_REPRODUCIBILITY_REQUIRED`
* :data:`~agentlabx.stages.registry.CANONICAL_BACKTRACK_TARGETS`
* :data:`~agentlabx.stages.registry.CANONICAL_PRESERVE_TAGS`
* :data:`~agentlabx.stages.registry.STAGE_NAMES`
"""

from __future__ import annotations

from pydantic import BaseModel, ValidationError

from agentlabx.stages.protocol import (
    BacktrackSignal,
    BacktrackTargetError,
    JSONValue,
    StageOutput,
    StageValidationError,
)
from agentlabx.stages.registry import (
    CANONICAL_BACKTRACK_TARGETS,
    CANONICAL_CONTRACTS,
    CANONICAL_PRESERVE_TAGS,
    STAGE_NAMES,
    STAGE_REPRODUCIBILITY_REQUIRED,
)
from agentlabx.stages.reproducibility import ReproducibilityContract


def validate_input(stage_name: str, payload: dict[str, JSONValue]) -> BaseModel:
    """Validate *payload* against the canonical input model for *stage_name*.

    Reads :data:`~agentlabx.stages.registry.CANONICAL_CONTRACTS` to obtain the
    input model; never queries the registered :class:`Stage` subclass.

    Args:
        stage_name: Canonical stage name (must appear in
            :data:`~agentlabx.stages.registry.STAGE_NAMES`).
        payload: Raw dictionary to validate.

    Returns:
        A validated instance of the stage's canonical input model.

    Raises:
        StageValidationError: If *stage_name* is unknown, or if *payload*
            fails Pydantic validation.  When wrapping a
            :class:`~pydantic.ValidationError`, the original is preserved as
            ``__cause__`` via ``raise X from e``.
    """
    if stage_name not in STAGE_NAMES:
        raise StageValidationError(
            stage_name,
            "input",
            f"unknown stage {stage_name!r}; valid stages are {list(STAGE_NAMES)}",
        )

    input_model, _ = CANONICAL_CONTRACTS[stage_name]
    try:
        return input_model.model_validate(payload)
    except ValidationError as e:
        raise StageValidationError(
            stage_name,
            "input",
            str(e),
        ) from e


def validate_output(
    stage_name: str,
    output: dict[str, JSONValue],
    reproducibility: dict[str, JSONValue] | None,
) -> StageOutput[BaseModel]:
    """Validate *output* (and optional *reproducibility*) for *stage_name*.

    Reads :data:`~agentlabx.stages.registry.CANONICAL_CONTRACTS` for the output
    model and :data:`~agentlabx.stages.registry.STAGE_REPRODUCIBILITY_REQUIRED`
    to determine whether a :class:`~agentlabx.stages.reproducibility.ReproducibilityContract`
    is required.  Never queries the registered :class:`Stage` subclass.

    Reproducibility policy:

    * Stages in :data:`~agentlabx.stages.registry.STAGE_REPRODUCIBILITY_REQUIRED`
      **must** supply a complete ``reproducibility`` dict.  Supplying ``None`` or
      an incomplete dict raises :class:`~agentlabx.stages.protocol.StageValidationError`.
    * Stages **not** in ``STAGE_REPRODUCIBILITY_REQUIRED`` may supply
      ``reproducibility`` or omit it; both are silently accepted.

    .. note::
        The return type is ``StageOutput[BaseModel]`` because Pydantic v2 generic
        erasure prevents recovering the concrete ``OutputT`` at the validator
        boundary.  Callers that need the concrete type for static checking should
        ``assert isinstance(result.payload, LiteratureReviewOutput)`` (or the
        relevant model) — the runtime instance IS the concrete type, only the
        static binding is erased.

    Args:
        stage_name: Canonical stage name (must appear in
            :data:`~agentlabx.stages.registry.STAGE_NAMES`).
        output: Raw dictionary to validate against the output model.
        reproducibility: Optional reproducibility dict; required when
            *stage_name* is in
            :data:`~agentlabx.stages.registry.STAGE_REPRODUCIBILITY_REQUIRED`.

    Returns:
        A :class:`~agentlabx.stages.protocol.StageOutput` whose ``payload`` is
        an instance of the stage's canonical output model and whose
        ``reproducibility`` is either a
        :class:`~agentlabx.stages.reproducibility.ReproducibilityContract`
        instance or ``None``.

    Raises:
        StageValidationError: If *stage_name* is unknown, if *output* fails
            Pydantic validation, if a required ``ReproducibilityContract`` is
            absent, or if the provided ``reproducibility`` dict is incomplete.
    """
    if stage_name not in STAGE_NAMES:
        raise StageValidationError(
            stage_name,
            "output",
            f"unknown stage {stage_name!r}; valid stages are {list(STAGE_NAMES)}",
        )

    _, output_model = CANONICAL_CONTRACTS[stage_name]

    # Validate output payload
    try:
        payload_model = output_model.model_validate(output)
    except ValidationError as e:
        raise StageValidationError(
            stage_name,
            "output",
            str(e),
        ) from e

    # Validate reproducibility contract
    repro_obj: ReproducibilityContract | None = None
    if stage_name in STAGE_REPRODUCIBILITY_REQUIRED:
        if reproducibility is None:
            raise StageValidationError(
                stage_name,
                "output",
                f"stage {stage_name!r} requires a ReproducibilityContract but none was provided",
            )
        try:
            repro_obj = ReproducibilityContract.model_validate(reproducibility)
        except ValidationError as e:
            raise StageValidationError(
                stage_name,
                "output",
                str(e),
            ) from e
    elif reproducibility is not None:
        # Silently accept reproducibility for stages that do not require it
        try:
            repro_obj = ReproducibilityContract.model_validate(reproducibility)
        except ValidationError as e:
            raise StageValidationError(
                stage_name,
                "output",
                str(e),
            ) from e

    return StageOutput[BaseModel](payload=payload_model, reproducibility=repro_obj)


def validate_backtrack(origin_stage_name: str, signal: BacktrackSignal) -> None:
    """Validate *signal* against the canonical backtrack constraints for *origin_stage_name*.

    Enforces three canonical constraints, all read from registry constants
    (never from the registered Stage subclass):

    1. *origin_stage_name* must be a known canonical stage.
    2. ``signal.target_stage`` must be in
       :data:`~agentlabx.stages.registry.CANONICAL_BACKTRACK_TARGETS`
       for *origin_stage_name*.
    3. ``signal.preserve`` must be a subset of
       :data:`~agentlabx.stages.registry.CANONICAL_PRESERVE_TAGS`
       for *origin_stage_name* (B-2 fix: rejects typo tags that would otherwise
       silently mean "preserve nothing").

    Args:
        origin_stage_name: The stage emitting the backtrack signal (must be
            canonical).
        signal: The :class:`~agentlabx.stages.protocol.BacktrackSignal` to
            validate.

    Raises:
        BacktrackTargetError: If any of the three constraints is violated.
    """
    if origin_stage_name not in STAGE_NAMES:
        raise BacktrackTargetError(
            origin_stage_name,
            signal.target_stage,
            f"unknown origin stage: {origin_stage_name!r}",
        )

    allowed_targets = CANONICAL_BACKTRACK_TARGETS[origin_stage_name]
    if signal.target_stage not in allowed_targets:
        raise BacktrackTargetError(
            origin_stage_name,
            signal.target_stage,
            (
                f"{origin_stage_name} cannot target {signal.target_stage}: "
                f"allowed = {allowed_targets}"
            ),
        )

    allowed_tags = CANONICAL_PRESERVE_TAGS[origin_stage_name]
    unknown_tags = signal.preserve - allowed_tags
    if unknown_tags:
        raise BacktrackTargetError(
            origin_stage_name,
            signal.target_stage,
            (
                f"{origin_stage_name} declared unknown preserve tags: "
                f"{signal.preserve - allowed_tags}"
            ),
        )


__all__ = [
    "validate_backtrack",
    "validate_input",
    "validate_output",
]
