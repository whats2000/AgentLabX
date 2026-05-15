"""Tests for agentlabx.stages.reproducibility.ReproducibilityContract."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TypedDict

import pytest
from pydantic import ValidationError

from agentlabx.stages.reproducibility import ReproducibilityContract

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _RepoKwargs(TypedDict):
    seed: int
    env_hash: str
    deps_snapshot: dict[str, str]
    run_command: str
    container_image: str | None
    git_ref: str | None


VALID_KWARGS: _RepoKwargs = {
    "seed": 42,
    "env_hash": "sha256:abc123",
    "deps_snapshot": {"numpy": "1.26.0", "torch": "2.3.0"},
    "run_command": "python train.py --cfg config.yaml",
    "container_image": "ghcr.io/org/image:latest",
    "git_ref": "refs/heads/main@abcdef0",
}


def make_contract(**overrides: object) -> ReproducibilityContract:
    merged: dict[str, object] = {**VALID_KWARGS, **overrides}
    return ReproducibilityContract(**merged)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Round-trip (single consolidated test)
# ---------------------------------------------------------------------------


def test_round_trip() -> None:
    """JSON round-trip produces an equal contract; created_at stays a datetime."""
    original = make_contract()
    dumped = original.model_dump(mode="json")
    restored = ReproducibilityContract.model_validate(dumped)
    assert restored == original
    assert isinstance(restored.created_at, datetime)


# ---------------------------------------------------------------------------
# created_at default
# ---------------------------------------------------------------------------


def test_created_at_defaults_to_now_utc() -> None:
    before = datetime.now(UTC)
    contract = make_contract()
    after = datetime.now(UTC)
    assert before <= contract.created_at <= after


# ---------------------------------------------------------------------------
# None-valued optional fields (must be explicitly present)
# ---------------------------------------------------------------------------


def test_none_container_image_accepted() -> None:
    contract = make_contract(container_image=None)
    assert contract.container_image is None


def test_none_git_ref_accepted() -> None:
    contract = make_contract(git_ref=None)
    assert contract.git_ref is None


# ---------------------------------------------------------------------------
# Partial-dict rejection (required fields without defaults)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "missing_field",
    ["seed", "env_hash", "container_image", "git_ref", "run_command", "deps_snapshot"],
)
def test_required_field_missing_raises(missing_field: str) -> None:
    """Omitting any required field must raise ValidationError."""
    data = {k: v for k, v in VALID_KWARGS.items() if k != missing_field}
    with pytest.raises(ValidationError):
        ReproducibilityContract(**data)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Field-level constraint: env_hash must be non-empty
# ---------------------------------------------------------------------------


def test_empty_env_hash_raises() -> None:
    with pytest.raises(ValidationError):
        make_contract(env_hash="")


# ---------------------------------------------------------------------------
# Field-level constraint: run_command must be non-empty
# ---------------------------------------------------------------------------


def test_empty_run_command_raises() -> None:
    with pytest.raises(ValidationError):
        make_contract(run_command="")


# ---------------------------------------------------------------------------
# Frozen model — mutation is rejected
# ---------------------------------------------------------------------------


def test_frozen_model_rejects_mutation() -> None:
    contract = make_contract()
    with pytest.raises(ValidationError):
        contract.seed = 99  # noqa: B010


# ---------------------------------------------------------------------------
# extra="forbid" — extra fields are rejected
# ---------------------------------------------------------------------------


def test_extra_field_raises() -> None:
    data = {**VALID_KWARGS, "unexpected_field": "oops"}
    with pytest.raises(ValidationError):
        ReproducibilityContract.model_validate(data)


# ---------------------------------------------------------------------------
# Negative seed is valid (some RNGs accept negative seeds)
# ---------------------------------------------------------------------------


def test_negative_seed_accepted() -> None:
    contract = make_contract(seed=-1)
    assert contract.seed == -1


# ---------------------------------------------------------------------------
# Empty deps_snapshot is allowed (degenerate but legal)
# ---------------------------------------------------------------------------


def test_empty_deps_snapshot_accepted() -> None:
    contract = make_contract(deps_snapshot={})
    assert contract.deps_snapshot == {}
