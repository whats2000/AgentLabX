"""StageRegistry — contract-driven enforcement and entry-point discovery (A4 Task 5).

Canonical constants and the :class:`StageRegistry` class live here.  The
constants are the *single source of truth* for pipeline order, I/O contracts,
reproducibility requirements, backtrack upper-bounds, and preserve-tag
upper-bounds.

No implementation details live here — this module is intentionally thin and
import-only.
"""

from __future__ import annotations

import warnings
from importlib.metadata import entry_points
from typing import TypeVar

from pydantic import BaseModel

from agentlabx.mcp.capabilities import SEED_CAPABILITIES
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
from agentlabx.stages.protocol import Stage, StageContractMismatchError

# ---------------------------------------------------------------------------
# Canonical pipeline order
# ---------------------------------------------------------------------------

STAGE_NAMES: tuple[str, ...] = (
    "literature_review",
    "plan_formulation",
    "data_exploration",
    "data_preparation",
    "experimentation",
    "interpretation",
    "report_writing",
    "peer_review",
)
"""The 8 canonical stage names in pipeline order.

This is the single source of truth — registry validation, the runner, and
UI labels all derive from this constant.
"""

# ---------------------------------------------------------------------------
# Canonical I/O contracts
# ---------------------------------------------------------------------------

CANONICAL_CONTRACTS: dict[str, tuple[type[BaseModel], type[BaseModel]]] = {
    "literature_review": (LiteratureReviewInput, LiteratureReviewOutput),
    "plan_formulation": (PlanFormulationInput, PlanFormulationOutput),
    "data_exploration": (DataExplorationInput, DataExplorationOutput),
    "data_preparation": (DataPreparationInput, DataPreparationOutput),
    "experimentation": (ExperimentationInput, ExperimentationOutput),
    "interpretation": (InterpretationInput, InterpretationOutput),
    "report_writing": (ReportWritingInput, ReportWritingOutput),
    "peer_review": (PeerReviewInput, PeerReviewOutput),
}
"""Canonical (input_model, output_model) pair per stage name.

``StageRegistry.register()`` enforces that every impl's declared models
match these exactly — no subclassing, no aliasing.
"""

# ---------------------------------------------------------------------------
# Reproducibility requirements
# ---------------------------------------------------------------------------

STAGE_REPRODUCIBILITY_REQUIRED: frozenset[str] = frozenset({"experimentation"})
"""Stages whose impls must declare ``requires_reproducibility = True``.

Single source of truth referenced by :meth:`StageRegistry.register` (rule 3).
"""

# ---------------------------------------------------------------------------
# Backtrack upper-bounds (SRS Layer-B table)
# ---------------------------------------------------------------------------

CANONICAL_BACKTRACK_TARGETS: dict[str, frozenset[str]] = {
    "literature_review": frozenset(),
    "plan_formulation": frozenset({"literature_review"}),
    "data_exploration": frozenset({"plan_formulation"}),
    "data_preparation": frozenset({"data_exploration"}),
    "experimentation": frozenset({"plan_formulation", "data_preparation", "data_exploration"}),
    "interpretation": frozenset({"experimentation"}),
    "report_writing": frozenset({"interpretation"}),
    "peer_review": frozenset(set(STAGE_NAMES) - {"peer_review"}),
}
"""Upper-bound backtrack targets per stage (SRS Layer-B table).

An impl may declare a *subset* of these (narrowing is allowed).  Declaring
targets **outside** this set causes :meth:`StageRegistry.register` to raise
:class:`~agentlabx.stages.protocol.StageContractMismatchError`.
"""

# ---------------------------------------------------------------------------
# Preserve-tag upper-bounds (B-2 fix; tags = field names on OWN output)
# ---------------------------------------------------------------------------

CANONICAL_PRESERVE_TAGS: dict[str, frozenset[str]] = {
    "literature_review": frozenset(),
    "plan_formulation": frozenset({"accepted_citation_ids"}),
    "data_exploration": frozenset({"summary_stats", "plots", "characterization"}),
    "data_preparation": frozenset({"prep_script", "splits", "transforms"}),
    "experimentation": frozenset({"metrics", "artifacts", "memory_entries_created"}),
    "interpretation": frozenset({"findings"}),
    "report_writing": frozenset(
        {"report_markdown", "report_latex", "report_pdf", "cited_chunk_ids"}
    ),
    "peer_review": frozenset({"action_items"}),
}
"""Upper-bound preserve-tag names per stage.

Tags are field names on the stage's OWN output model (audited against Task 4
contracts).  ``literature_review`` has an empty set for symmetry; it has no
backtrack targets, so preserve semantics are vacuous.
"""

# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_SEED_CAPABILITIES_SET: frozenset[str] = frozenset(SEED_CAPABILITIES)

# TypeVars on register() prevent mypy invariance errors when callers pass concrete Stage
# subclasses; the internal storage holds type[Stage[BaseModel, BaseModel]] which would
# normally not unify with the concrete generic instantiation at the call site.
_InputT = TypeVar("_InputT", bound=BaseModel)
_OutputT = TypeVar("_OutputT", bound=BaseModel)


class StageRegistry:
    """Contract-driven registry mapping stage names to concrete :class:`Stage` impls.

    All five validation rules are enforced at :meth:`register` time.  Rules 1-4
    raise :class:`~agentlabx.stages.protocol.StageContractMismatchError`; rule
    5 (unknown capability tags) emits :class:`UserWarning` but still registers
    the impl.

    Usage::

        registry = StageRegistry()
        registry.register(MyLiteratureReviewImpl)
        impl_class = registry.default_for("literature_review")
    """

    def __init__(self) -> None:
        self._impls: dict[str, list[type[Stage[BaseModel, BaseModel]]]] = {}

    def register(self, impl: type[Stage[_InputT, _OutputT]]) -> None:
        """Validate *impl* against all five contract rules and add it to the registry.

        Rules (all keyed on :data:`STAGE_NAMES` / :data:`CANONICAL_CONTRACTS`
        etc.):

        1. ``impl.stage_name`` must be in :data:`STAGE_NAMES`.
        2. ``(impl.input_model, impl.output_model)`` must equal
           :data:`CANONICAL_CONTRACTS[impl.stage_name]`.
        3. ``impl.requires_reproducibility`` must match whether the stage is in
           :data:`STAGE_REPRODUCIBILITY_REQUIRED`.
        4. ``impl.backtrack_targets`` must be a subset of
           :data:`CANONICAL_BACKTRACK_TARGETS[impl.stage_name]`.
        5. Every tag in ``impl.required_capabilities`` must appear in
           :data:`~agentlabx.mcp.capabilities.SEED_CAPABILITIES`; unknown tags
           emit :class:`UserWarning` (registration still succeeds).

        Args:
            impl: A :class:`~agentlabx.stages.protocol.Stage` subclass
                (the class itself, not an instance).

        Raises:
            StageContractMismatchError: If rules 1-4 are violated.
        """
        name = impl.stage_name

        # Rule 1 — stage_name must be canonical
        if name not in STAGE_NAMES:
            raise StageContractMismatchError(
                impl.__name__,
                "stage_name",
                f"{name!r} is not a canonical stage name; expected one of {STAGE_NAMES}",
            )

        # Rule 2 — I/O contract must match exactly
        expected_input, expected_output = CANONICAL_CONTRACTS[name]
        if impl.input_model is not expected_input or impl.output_model is not expected_output:
            raise StageContractMismatchError(
                impl.__name__,
                "input_model/output_model",
                (
                    f"contract mismatch for {name!r}: "
                    f"expected ({expected_input.__name__}, {expected_output.__name__}), "
                    f"got ({impl.input_model.__name__}, {impl.output_model.__name__})"
                ),
            )

        # Rule 3 — reproducibility flag must match STAGE_REPRODUCIBILITY_REQUIRED
        expected_repro = name in STAGE_REPRODUCIBILITY_REQUIRED
        if impl.requires_reproducibility != expected_repro:
            raise StageContractMismatchError(
                impl.__name__,
                "requires_reproducibility",
                (
                    f"stage {name!r} requires_reproducibility must be {expected_repro}, "
                    f"got {impl.requires_reproducibility}"
                ),
            )

        # Rule 4 — backtrack_targets must be a subset of the canonical upper-bound
        canonical_targets = CANONICAL_BACKTRACK_TARGETS[name]
        if not impl.backtrack_targets <= canonical_targets:
            extra = impl.backtrack_targets - canonical_targets
            raise StageContractMismatchError(
                impl.__name__,
                "backtrack_targets",
                (
                    f"stage {name!r} declared targets outside canonical upper-bound; "
                    f"disallowed: {sorted(extra)}"
                ),
            )

        # Rule 5 — capability tags: warn on unknown, never raise
        unknown_tags = impl.required_capabilities - _SEED_CAPABILITIES_SET
        if unknown_tags:
            warnings.warn(
                (
                    f"Stage {impl.__name__!r} declares unknown capability tags "
                    f"{sorted(unknown_tags)!r}; these are not in SEED_CAPABILITIES"
                ),
                UserWarning,
                stacklevel=2,
            )

        # TypeVar-bound generics (_InputT/_OutputT) vs concrete BaseModel storage:
        # mypy's invariance on type[Stage[...]] makes the generic-to-concrete
        # assignment unprovable at the append site, but the value is structurally correct.
        self._impls.setdefault(name, []).append(impl)  # type: ignore[arg-type]

    def implementations_for(self, stage_name: str) -> list[type[Stage[BaseModel, BaseModel]]]:
        """Return all registered impls for *stage_name* (empty list if none).

        Args:
            stage_name: Canonical stage name.

        Returns:
            A list of :class:`~agentlabx.stages.protocol.Stage` subclasses
            registered for this stage (may be empty).
        """
        return list(self._impls.get(stage_name, []))

    def default_for(self, stage_name: str) -> type[Stage[BaseModel, BaseModel]]:
        """Return the sole registered impl or raise if ambiguous/absent.

        Args:
            stage_name: Canonical stage name.

        Returns:
            The sole registered impl for *stage_name*.

        Raises:
            LookupError: If no impl is registered for *stage_name*.
            NotImplementedError: If more than one impl is registered
                (multi-impl selection is deferred to A6).
        """
        impls = self._impls.get(stage_name, [])
        n = len(impls)
        if n == 0:
            raise LookupError(f"no impl registered for {stage_name!r}")
        if n > 1:
            raise NotImplementedError(
                f"multiple impls registered for {stage_name!r} "
                "— A6 will read selected_impl from settings"
            )
        return impls[0]


# ---------------------------------------------------------------------------
# Entry-point discovery
# ---------------------------------------------------------------------------


def discover_stages(registry: StageRegistry) -> None:
    """Load stage impls from the ``agentlabx.stages`` entry-point group.

    Mirrors :func:`agentlabx.plugins.registry.discover_entry_points`.  Each
    entry point's target must be a :class:`~agentlabx.stages.protocol.Stage`
    subclass; it is passed directly to :meth:`StageRegistry.register`.

    Args:
        registry: The :class:`StageRegistry` to populate.
    """
    for ep in entry_points(group="agentlabx.stages"):
        impl = ep.load()
        registry.register(impl)


__all__ = [
    "CANONICAL_BACKTRACK_TARGETS",
    "CANONICAL_CONTRACTS",
    "CANONICAL_PRESERVE_TAGS",
    "STAGE_NAMES",
    "STAGE_REPRODUCIBILITY_REQUIRED",
    "StageRegistry",
    "discover_stages",
]
