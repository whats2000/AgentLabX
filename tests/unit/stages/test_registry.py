"""Tests for agentlabx.stages.registry — StageRegistry + entry-point discovery (A4 Task 5)."""

from __future__ import annotations

import warnings
from typing import ClassVar

import pytest
from pydantic import BaseModel

from agentlabx.stages.contracts.data_exploration import (
    DataExplorationInput,
    DataExplorationOutput,
)
from agentlabx.stages.contracts.experimentation import (
    ExperimentationInput,
    ExperimentationOutput,
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
from agentlabx.stages.protocol import (
    Stage,
    StageContext,
    StageContractMismatchError,
    StageResult,
)
from agentlabx.stages.registry import (
    CANONICAL_BACKTRACK_TARGETS,
    CANONICAL_CONTRACTS,
    CANONICAL_PRESERVE_TAGS,
    STAGE_NAMES,
    STAGE_REPRODUCIBILITY_REQUIRED,
    StageRegistry,
    discover_stages,
)

# ---------------------------------------------------------------------------
# Fixtures — minimal Stage subclasses for tests
# ---------------------------------------------------------------------------


class _LitReviewImpl(Stage[LiteratureReviewInput, LiteratureReviewOutput]):
    """Minimal literature_review impl used for happy-path tests."""

    stage_name: ClassVar[str] = "literature_review"
    input_model: ClassVar[type[BaseModel]] = LiteratureReviewInput
    output_model: ClassVar[type[BaseModel]] = LiteratureReviewOutput
    backtrack_targets: ClassVar[frozenset[str]] = frozenset()
    required_capabilities: ClassVar[frozenset[str]] = frozenset({"paper_search"})
    requires_reproducibility: ClassVar[bool] = False

    async def execute(
        self,
        payload: LiteratureReviewInput,
        ctx: StageContext,
    ) -> StageResult[LiteratureReviewOutput]:  # pragma: no cover
        raise NotImplementedError


class _LitReviewImpl2(Stage[LiteratureReviewInput, LiteratureReviewOutput]):
    """Second literature_review impl for N>1 default_for test."""

    stage_name: ClassVar[str] = "literature_review"
    input_model: ClassVar[type[BaseModel]] = LiteratureReviewInput
    output_model: ClassVar[type[BaseModel]] = LiteratureReviewOutput
    backtrack_targets: ClassVar[frozenset[str]] = frozenset()
    required_capabilities: ClassVar[frozenset[str]] = frozenset()
    requires_reproducibility: ClassVar[bool] = False

    async def execute(
        self,
        payload: LiteratureReviewInput,
        ctx: StageContext,
    ) -> StageResult[LiteratureReviewOutput]:  # pragma: no cover
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Section 1: Constants shape
# ---------------------------------------------------------------------------


class TestConstants:
    def test_stage_names_is_tuple(self) -> None:
        assert isinstance(STAGE_NAMES, tuple)

    def test_stage_names_has_eight_entries(self) -> None:
        assert len(STAGE_NAMES) == 8

    def test_stage_names_pipeline_order(self) -> None:
        assert STAGE_NAMES == (
            "literature_review",
            "plan_formulation",
            "data_exploration",
            "data_preparation",
            "experimentation",
            "interpretation",
            "report_writing",
            "peer_review",
        )

    def test_canonical_contracts_has_all_stages(self) -> None:
        assert set(CANONICAL_CONTRACTS.keys()) == set(STAGE_NAMES)

    def test_canonical_contracts_values_are_basemodel_pairs(self) -> None:
        for name, (inp, out) in CANONICAL_CONTRACTS.items():
            assert issubclass(inp, BaseModel), f"{name}: input not a BaseModel subclass"
            assert issubclass(out, BaseModel), f"{name}: output not a BaseModel subclass"

    def test_stage_reproducibility_required_is_frozenset(self) -> None:
        assert isinstance(STAGE_REPRODUCIBILITY_REQUIRED, frozenset)
        assert frozenset({"experimentation"}) == STAGE_REPRODUCIBILITY_REQUIRED

    def test_canonical_backtrack_targets_has_all_stages(self) -> None:
        assert set(CANONICAL_BACKTRACK_TARGETS.keys()) == set(STAGE_NAMES)

    def test_canonical_backtrack_targets_values_are_frozensets(self) -> None:
        for name, targets in CANONICAL_BACKTRACK_TARGETS.items():
            assert isinstance(targets, frozenset), f"{name}: targets not frozenset"

    def test_peer_review_backtrack_targets_is_all_prior_stages(self) -> None:
        expected = frozenset(set(STAGE_NAMES) - {"peer_review"})
        assert CANONICAL_BACKTRACK_TARGETS["peer_review"] == expected

    def test_literature_review_backtrack_targets_empty(self) -> None:
        assert CANONICAL_BACKTRACK_TARGETS["literature_review"] == frozenset()

    def test_canonical_preserve_tags_has_all_stages(self) -> None:
        assert set(CANONICAL_PRESERVE_TAGS.keys()) == set(STAGE_NAMES)

    def test_canonical_preserve_tags_values_are_frozensets(self) -> None:
        for name, tags in CANONICAL_PRESERVE_TAGS.items():
            assert isinstance(tags, frozenset), f"{name}: tags not frozenset"

    def test_plan_formulation_preserve_tags(self) -> None:
        assert CANONICAL_PRESERVE_TAGS["plan_formulation"] == frozenset({"accepted_citation_ids"})


# ---------------------------------------------------------------------------
# Section 2: Happy path
# ---------------------------------------------------------------------------


class TestHappyPath:
    def test_register_and_implementations_for(self) -> None:
        registry = StageRegistry()
        registry.register(_LitReviewImpl)
        assert registry.implementations_for("literature_review") == [_LitReviewImpl]

    def test_default_for_single_impl(self) -> None:
        registry = StageRegistry()
        registry.register(_LitReviewImpl)
        assert registry.default_for("literature_review") is _LitReviewImpl

    def test_implementations_for_returns_empty_list_for_unknown(self) -> None:
        registry = StageRegistry()
        result = registry.implementations_for("literature_review")
        assert result == []

    def test_implementations_for_not_named_list(self) -> None:
        # Verify the method is named correctly (not shadowing builtin 'list')
        registry = StageRegistry()
        assert hasattr(registry, "implementations_for")
        assert not hasattr(registry, "list")


# ---------------------------------------------------------------------------
# Section 3: Mismatch failure modes
# ---------------------------------------------------------------------------


class TestMismatchFailures:
    def test_unknown_stage_name_raises(self) -> None:
        class _BogusImpl(Stage[LiteratureReviewInput, LiteratureReviewOutput]):
            stage_name: ClassVar[str] = "bogus"
            input_model: ClassVar[type[BaseModel]] = LiteratureReviewInput
            output_model: ClassVar[type[BaseModel]] = LiteratureReviewOutput
            backtrack_targets: ClassVar[frozenset[str]] = frozenset()
            requires_reproducibility: ClassVar[bool] = False

            async def execute(
                self,
                payload: LiteratureReviewInput,
                ctx: StageContext,
            ) -> StageResult[LiteratureReviewOutput]:  # pragma: no cover
                raise NotImplementedError

        registry = StageRegistry()
        with pytest.raises(StageContractMismatchError):
            registry.register(_BogusImpl)

    def test_wrong_output_model_raises(self) -> None:
        class _WrongOutputImpl(Stage[LiteratureReviewInput, PlanFormulationOutput]):
            stage_name: ClassVar[str] = "literature_review"
            input_model: ClassVar[type[BaseModel]] = LiteratureReviewInput
            output_model: ClassVar[type[BaseModel]] = PlanFormulationOutput
            backtrack_targets: ClassVar[frozenset[str]] = frozenset()
            requires_reproducibility: ClassVar[bool] = False

            async def execute(
                self,
                payload: LiteratureReviewInput,
                ctx: StageContext,
            ) -> StageResult[PlanFormulationOutput]:  # pragma: no cover
                raise NotImplementedError

        registry = StageRegistry()
        with pytest.raises(StageContractMismatchError):
            registry.register(_WrongOutputImpl)

    def test_wrong_reproducibility_true_for_non_required_raises(self) -> None:
        class _WrongReproImpl(Stage[LiteratureReviewInput, LiteratureReviewOutput]):
            stage_name: ClassVar[str] = "literature_review"
            input_model: ClassVar[type[BaseModel]] = LiteratureReviewInput
            output_model: ClassVar[type[BaseModel]] = LiteratureReviewOutput
            backtrack_targets: ClassVar[frozenset[str]] = frozenset()
            requires_reproducibility: ClassVar[bool] = True  # wrong: LR doesn't need it

            async def execute(
                self,
                payload: LiteratureReviewInput,
                ctx: StageContext,
            ) -> StageResult[LiteratureReviewOutput]:  # pragma: no cover
                raise NotImplementedError

        registry = StageRegistry()
        with pytest.raises(StageContractMismatchError):
            registry.register(_WrongReproImpl)

    def test_wrong_reproducibility_false_for_required_raises(self) -> None:
        class _WrongReproImpl2(Stage[ExperimentationInput, ExperimentationOutput]):
            stage_name: ClassVar[str] = "experimentation"
            input_model: ClassVar[type[BaseModel]] = ExperimentationInput
            output_model: ClassVar[type[BaseModel]] = ExperimentationOutput
            backtrack_targets: ClassVar[frozenset[str]] = frozenset()
            requires_reproducibility: ClassVar[bool] = False  # wrong: experimentation requires it

            async def execute(
                self,
                payload: ExperimentationInput,
                ctx: StageContext,
            ) -> StageResult[ExperimentationOutput]:  # pragma: no cover
                raise NotImplementedError

        registry = StageRegistry()
        with pytest.raises(StageContractMismatchError):
            registry.register(_WrongReproImpl2)

    def test_broadened_backtrack_targets_raises(self) -> None:
        class _BroadenedImpl(Stage[PlanFormulationInput, PlanFormulationOutput]):
            stage_name: ClassVar[str] = "plan_formulation"
            input_model: ClassVar[type[BaseModel]] = PlanFormulationInput
            output_model: ClassVar[type[BaseModel]] = PlanFormulationOutput
            # peer_review is NOT in CANONICAL_BACKTRACK_TARGETS["plan_formulation"]
            backtrack_targets: ClassVar[frozenset[str]] = frozenset(
                {"literature_review", "peer_review"}
            )
            requires_reproducibility: ClassVar[bool] = False

            async def execute(
                self,
                payload: PlanFormulationInput,
                ctx: StageContext,
            ) -> StageResult[PlanFormulationOutput]:  # pragma: no cover
                raise NotImplementedError

        registry = StageRegistry()
        with pytest.raises(StageContractMismatchError):
            registry.register(_BroadenedImpl)

    def test_narrowed_backtrack_targets_succeeds(self) -> None:
        """Subset of canonical targets is allowed (narrowing = OK)."""

        class _NarrowedPeerReviewImpl(Stage[PeerReviewInput, PeerReviewOutput]):
            stage_name: ClassVar[str] = "peer_review"
            input_model: ClassVar[type[BaseModel]] = PeerReviewInput
            output_model: ClassVar[type[BaseModel]] = PeerReviewOutput
            # Only one of the 7 allowed targets — valid subset
            backtrack_targets: ClassVar[frozenset[str]] = frozenset({"experimentation"})
            requires_reproducibility: ClassVar[bool] = False

            async def execute(
                self,
                payload: PeerReviewInput,
                ctx: StageContext,
            ) -> StageResult[PeerReviewOutput]:  # pragma: no cover
                raise NotImplementedError

        registry = StageRegistry()
        registry.register(_NarrowedPeerReviewImpl)  # must not raise
        assert registry.implementations_for("peer_review") == [_NarrowedPeerReviewImpl]


# ---------------------------------------------------------------------------
# Section 4: Capability tag warnings
# ---------------------------------------------------------------------------


class TestCapabilityTagWarnings:
    def test_unknown_capability_emits_user_warning(self) -> None:
        class _UnknownCapImpl(Stage[DataExplorationInput, DataExplorationOutput]):
            stage_name: ClassVar[str] = "data_exploration"
            input_model: ClassVar[type[BaseModel]] = DataExplorationInput
            output_model: ClassVar[type[BaseModel]] = DataExplorationOutput
            backtrack_targets: ClassVar[frozenset[str]] = frozenset()
            required_capabilities: ClassVar[frozenset[str]] = frozenset({"fs_read", "made_up_cap"})
            requires_reproducibility: ClassVar[bool] = False

            async def execute(
                self,
                payload: DataExplorationInput,
                ctx: StageContext,
            ) -> StageResult[DataExplorationOutput]:  # pragma: no cover
                raise NotImplementedError

        registry = StageRegistry()
        with pytest.warns(UserWarning):
            registry.register(_UnknownCapImpl)
        # Registration succeeded
        assert registry.implementations_for("data_exploration") == [_UnknownCapImpl]

    def test_known_capability_emits_no_warning(self) -> None:
        class _KnownCapImpl(Stage[DataExplorationInput, DataExplorationOutput]):
            stage_name: ClassVar[str] = "data_exploration"
            input_model: ClassVar[type[BaseModel]] = DataExplorationInput
            output_model: ClassVar[type[BaseModel]] = DataExplorationOutput
            backtrack_targets: ClassVar[frozenset[str]] = frozenset()
            required_capabilities: ClassVar[frozenset[str]] = frozenset({"web_browse"})
            requires_reproducibility: ClassVar[bool] = False

            async def execute(
                self,
                payload: DataExplorationInput,
                ctx: StageContext,
            ) -> StageResult[DataExplorationOutput]:  # pragma: no cover
                raise NotImplementedError

        registry = StageRegistry()
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            registry.register(_KnownCapImpl)
        assert len(w) == 0


# ---------------------------------------------------------------------------
# Section 5: default_for behaviour
# ---------------------------------------------------------------------------


class TestDefaultFor:
    def test_default_for_no_impl_raises_lookup_error(self) -> None:
        registry = StageRegistry()
        with pytest.raises(LookupError) as exc_info:
            registry.default_for("literature_review")
        assert "literature_review" in str(exc_info.value)

    def test_default_for_single_impl_returns_it(self) -> None:
        registry = StageRegistry()
        registry.register(_LitReviewImpl)
        assert registry.default_for("literature_review") is _LitReviewImpl

    def test_default_for_two_impls_raises_not_implemented(self) -> None:
        registry = StageRegistry()
        registry.register(_LitReviewImpl)
        registry.register(_LitReviewImpl2)
        with pytest.raises(NotImplementedError) as exc_info:
            registry.default_for("literature_review")
        assert "A6 will read selected_impl from settings" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Section 6: discover_stages (entry-point integration)
# ---------------------------------------------------------------------------


@pytest.mark.skip(reason="entry points not yet registered — see Task 8")
def test_discover_stages_loads_entry_points() -> None:
    """Full entry-point discovery — skipped until Task 8 ships echo stubs."""
    registry = StageRegistry()
    discover_stages(registry)
    # After Task 8, assert that known stub stages appear in the registry.


def test_discover_stages_no_entry_points_registered() -> None:
    """In a clean test environment, no entry points exist — registry stays empty."""
    registry = StageRegistry()
    # In a fresh install without registered entry points this should be a no-op.
    discover_stages(registry)
    for name in STAGE_NAMES:
        assert registry.implementations_for(name) == [], (
            f"expected no impls for {name!r} before any entry points are registered"
        )
