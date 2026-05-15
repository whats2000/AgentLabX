"""Reproducibility contract model for experiment artifacts (SRS FR-7).

Every experiment artifact must carry a fully-specified reproducibility contract;
partial submission is rejected by the model's extra="forbid" + required fields.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field


class ReproducibilityContract(BaseModel):  # type: ignore[explicit-any]
    """Immutable reproducibility contract attached to every experiment artifact.

    All fields are required at construction time — ``extra="forbid"`` ensures
    no partial or mis-spelled fields can slip through.  ``container_image`` and
    ``git_ref`` accept ``None`` (not containerised / no VCS ref) but the fields
    themselves must be explicitly provided.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    seed: int
    env_hash: str = Field(min_length=1)
    deps_snapshot: dict[str, str]
    run_command: str = Field(min_length=1)
    container_image: str | None
    git_ref: str | None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
