"""Tests for agentlabx.stages.validator — StageIOValidator (A4 Task 6).

Covers all three pure functions:
- validate_input  (tests 8-10)
- validate_output (tests 1-7)
- validate_backtrack (tests 11-16)
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from agentlabx.stages.contracts.literature_review import LiteratureReviewOutput
from agentlabx.stages.protocol import (
    BacktrackSignal,
    BacktrackTargetError,
    JSONValue,
    StageOutput,
    StageValidationError,
)
from agentlabx.stages.reproducibility import ReproducibilityContract
from agentlabx.stages.validator import validate_backtrack, validate_input, validate_output

# ---------------------------------------------------------------------------
# Minimal valid payload dicts (avoid using the model constructors so that
# we test the dict→model path the validator actually exercises)
# ---------------------------------------------------------------------------

_VALID_LITERATURE_REVIEW_OUTPUT: dict[str, JSONValue] = {
    "citations": [
        {
            "paper_id": "2304.12345v1",
            "title": "Some Title",
            "authors": ["Alice Bob"],
            "year": 2023,
            "source": "arxiv",
            "url": "https://arxiv.org/abs/2304.12345v1",
        }
    ],
    "summaries": [
        {
            "citation_id": "2304.12345v1",
            "paragraph": "Key paper on augmentation.",
            "chunk_refs": [
                {
                    "chunk_id": "c-1",
                    "paper_id": "2304.12345v1",
                    "span_start": 0,
                    "span_end": 200,
                    "score": 0.9,
                }
            ],
        }
    ],
    "corpus_id": "corp-42",
}

_VALID_EXPERIMENTATION_OUTPUT: dict[str, JSONValue] = {
    "metrics": [{"name": "dice", "value": 0.87, "unit": None}],
    "artifacts": [
        {
            "artifact_id": "a-model.pt",
            "kind": "model",
            "path": "/workspace/runs/run-1/model.pt",
            "content_hash": "sha256:deadbeef" * 4,
        }
    ],
    "exec_logs": [{"stdout": "loss: 0.42\n", "stderr": "", "exit_code": 0}],
    "memory_entries_created": ["mem-uuid-1"],
}

_VALID_REPRODUCIBILITY: dict[str, JSONValue] = {
    "seed": 42,
    "env_hash": "abc123",
    "deps_snapshot": {"torch": "2.1.0"},
    "run_command": "python train.py",
    "container_image": None,
    "git_ref": "abc1234",
}

_VALID_LITERATURE_REVIEW_INPUT: dict[str, JSONValue] = {
    "question": {
        "text": "Does augmentation help CT segmentation?",
        "project_id": "proj-1",
    },
    "prior_corpus_ids": [],
    "target_count_min": 10,
}

# ---------------------------------------------------------------------------
# validate_output tests (1-7)
# ---------------------------------------------------------------------------


class TestValidateOutput:
    def test_01_happy_path_literature_review(self) -> None:
        """validate_output returns StageOutput with LiteratureReviewOutput payload."""
        result = validate_output("literature_review", _VALID_LITERATURE_REVIEW_OUTPUT, None)

        assert isinstance(result, StageOutput)
        assert isinstance(result.payload, BaseModel)
        assert isinstance(result.payload, LiteratureReviewOutput)
        assert result.reproducibility is None

    def test_02_schema_violation_raises_stage_validation_error(self) -> None:
        """citations must be a list; passing a string raises StageValidationError."""
        bad_payload: dict[str, JSONValue] = {
            "citations": "not a list",
            "summaries": [],
            "corpus_id": "corp-1",
        }
        with pytest.raises(StageValidationError):
            validate_output("literature_review", bad_payload, None)

    def test_03_missing_reproducibility_on_experimentation_raises(self) -> None:
        """experimentation requires reproducibility; passing None raises StageValidationError."""
        with pytest.raises(StageValidationError, match="ReproducibilityContract"):
            validate_output("experimentation", _VALID_EXPERIMENTATION_OUTPUT, None)

    def test_04_valid_reproducibility_on_experimentation_succeeds(self) -> None:
        """experimentation with a complete repro dict returns populated reproducibility."""
        result = validate_output(
            "experimentation", _VALID_EXPERIMENTATION_OUTPUT, _VALID_REPRODUCIBILITY
        )

        assert isinstance(result, StageOutput)
        assert isinstance(result.reproducibility, ReproducibilityContract)
        assert result.reproducibility.seed == 42

    def test_05_incomplete_reproducibility_on_experimentation_raises(self) -> None:
        """Incomplete repro dict (missing required fields) raises StageValidationError."""
        incomplete_repro: dict[str, JSONValue] = {"seed": 42}
        with pytest.raises(StageValidationError):
            validate_output("experimentation", _VALID_EXPERIMENTATION_OUTPUT, incomplete_repro)

    def test_06_reproducibility_on_non_experimentation_stage_is_silently_allowed(self) -> None:
        """Providing repro for literature_review is silently accepted per spec."""
        result = validate_output(
            "literature_review", _VALID_LITERATURE_REVIEW_OUTPUT, _VALID_REPRODUCIBILITY
        )

        assert isinstance(result, StageOutput)
        assert isinstance(result.reproducibility, ReproducibilityContract)

    def test_07_unknown_stage_raises_stage_validation_error(self) -> None:
        """Unknown stage name raises StageValidationError."""
        with pytest.raises(StageValidationError):
            validate_output("bogus", {}, None)


# ---------------------------------------------------------------------------
# validate_input tests (8-10)
# ---------------------------------------------------------------------------


class TestValidateInput:
    def test_08_happy_path(self) -> None:
        """validate_input returns a valid BaseModel instance for a good payload."""
        result = validate_input("literature_review", _VALID_LITERATURE_REVIEW_INPUT)

        assert isinstance(result, BaseModel)

    def test_09_schema_violation_raises_stage_validation_error(self) -> None:
        """An invalid field type raises StageValidationError (wraps ValidationError)."""
        bad_payload: dict[str, JSONValue] = {
            "question": "not a dict",
            "prior_corpus_ids": [],
            "target_count_min": 10,
        }
        with pytest.raises(StageValidationError):
            validate_input("literature_review", bad_payload)

    def test_10_unknown_stage_raises_stage_validation_error(self) -> None:
        """Unknown stage name raises StageValidationError."""
        with pytest.raises(StageValidationError):
            validate_input("bogus_stage", {})


# ---------------------------------------------------------------------------
# validate_backtrack tests (11-16)
# ---------------------------------------------------------------------------


class TestValidateBacktrack:
    def test_11_peer_review_may_target_any_earlier_stage(self) -> None:
        """peer_review may target any earlier canonical stage; test two targets."""
        signal_lr = BacktrackSignal(
            target_stage="literature_review",
            reason="Insufficient literature coverage.",
        )
        signal_exp = BacktrackSignal(
            target_stage="experimentation",
            reason="Experiment design flawed.",
        )
        # Both should succeed without raising
        validate_backtrack("peer_review", signal_lr)
        validate_backtrack("peer_review", signal_exp)

    def test_12_literature_review_has_no_targets(self) -> None:
        """literature_review cannot target any stage; any target raises BacktrackTargetError."""
        signal = BacktrackSignal(
            target_stage="plan_formulation",
            reason="Want to redo plan.",
        )
        with pytest.raises(BacktrackTargetError):
            validate_backtrack("literature_review", signal)

    def test_13_data_preparation_cannot_target_literature_review(self) -> None:
        """data_preparation → literature_review is outside canonical targets; must raise."""
        signal = BacktrackSignal(
            target_stage="literature_review",
            reason="Need more papers.",
        )
        with pytest.raises(BacktrackTargetError):
            validate_backtrack("data_preparation", signal)

    def test_14_data_preparation_can_target_data_exploration(self) -> None:
        """data_preparation → data_exploration is canonical; must succeed."""
        signal = BacktrackSignal(
            target_stage="data_exploration",
            reason="Need to rerun exploration.",
        )
        # Should not raise
        validate_backtrack("data_preparation", signal)

    def test_15_b2_preserve_tag_enforcement(self) -> None:
        """B-2: valid tag accepted, typo tag rejected, empty preserve accepted."""
        # Valid: accepted_citation_ids is in CANONICAL_PRESERVE_TAGS["plan_formulation"]
        signal_valid = BacktrackSignal(
            target_stage="literature_review",
            reason="x",
            preserve=frozenset({"accepted_citation_ids"}),
        )
        validate_backtrack("plan_formulation", signal_valid)  # must not raise

        # Invalid: accepted_citations (missing _ids suffix) is a typo — not in canonical
        signal_typo = BacktrackSignal(
            target_stage="literature_review",
            reason="x",
            preserve=frozenset({"accepted_citations"}),
        )
        with pytest.raises(BacktrackTargetError, match="accepted_citations"):
            validate_backtrack("plan_formulation", signal_typo)

        # Empty preserve set is always valid
        signal_empty = BacktrackSignal(
            target_stage="literature_review",
            reason="x",
            preserve=frozenset(),
        )
        validate_backtrack("plan_formulation", signal_empty)  # must not raise

    def test_16_unknown_origin_stage_raises_backtrack_target_error(self) -> None:
        """Unknown origin stage raises BacktrackTargetError."""
        signal = BacktrackSignal(
            target_stage="literature_review",
            reason="Going back.",
        )
        with pytest.raises(BacktrackTargetError):
            validate_backtrack("not_a_real_stage", signal)
