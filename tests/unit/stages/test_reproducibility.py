"""Tests for agentlabx.stages.reproducibility.ReproducibilityContract."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from agentlabx.stages.reproducibility import ReproducibilityContract

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_KWARGS: dict[str, object] = {
    "seed": 42,
    "env_hash": "sha256:abc123",
    "deps_snapshot": {"numpy": "1.26.0", "torch": "2.3.0"},
    "run_command": "python train.py --cfg config.yaml",
    "container_image": "ghcr.io/org/image:latest",
    "git_ref": "refs/heads/main@abcdef0",
}


def make_contract(**overrides: object) -> ReproducibilityContract:
    kwargs = {**VALID_KWARGS, **overrides}
    return ReproducibilityContract(**kwargs)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Round-trip
# ---------------------------------------------------------------------------


def test_round_trip_json_mode() -> None:
    """model_dump(mode='json') -> model_validate produces an equal contract."""
    original = make_contract()
    dumped = original.model_dump(mode="json")
    restored = ReproducibilityContract.model_validate(dumped)

    assert restored.seed == original.seed
    assert restored.env_hash == original.env_hash
    assert restored.deps_snapshot == original.deps_snapshot
    assert restored.run_command == original.run_command
    assert restored.container_image == original.container_image
    assert restored.git_ref == original.git_ref


def test_round_trip_equality() -> None:
    """Frozen Pydantic models compare equal after a JSON round-trip."""
    original = make_contract()
    dumped = original.model_dump(mode="json")
    restored = ReproducibilityContract.model_validate(dumped)
    assert restored == original


def test_created_at_round_trip() -> None:
    """created_at survives a JSON round-trip as a datetime instance."""
    original = make_contract()
    dumped = original.model_dump(mode="json")
    restored = ReproducibilityContract.model_validate(dumped)
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


def test_missing_git_ref_raises() -> None:
    """Omitting git_ref (required, no default) must raise ValidationError."""
    data = {k: v for k, v in VALID_KWARGS.items() if k != "git_ref"}
    with pytest.raises(ValidationError):
        ReproducibilityContract(**data)  # type: ignore[arg-type]


def test_missing_container_image_raises() -> None:
    data = {k: v for k, v in VALID_KWARGS.items() if k != "container_image"}
    with pytest.raises(ValidationError):
        ReproducibilityContract(**data)  # type: ignore[arg-type]


def test_missing_seed_raises() -> None:
    data = {k: v for k, v in VALID_KWARGS.items() if k != "seed"}
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
    with pytest.raises((ValidationError, TypeError)):
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
