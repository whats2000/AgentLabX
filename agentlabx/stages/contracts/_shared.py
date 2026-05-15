"""Shared sub-models for stage contracts. Task 3 extends this file."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class NoteRef(BaseModel):  # type: ignore[explicit-any]
    """A7 hook placeholder. Task 3 may extend with body / created_at."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    category: str


__all__ = ["NoteRef"]
