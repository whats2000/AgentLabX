"""Steering helpers — how fork tests push the model toward a specific branch.

Two channels:
- HitlDirective: wraps the production POST /checkpoint/approve payload. Used at
  decide/transition checkpoints where the production UI would submit an approval.
- ContextShape: mutations to PipelineState applied *before* a stage runs, to bias
  the model (remove prior artifacts to force gate=run, cap iterations to force
  evaluate=done, etc.).

These are the only two legitimate steering mechanisms. Mocking the model is not
allowed — if a branch is unreachable via these channels, that itself is a finding.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any


@dataclass
class HitlDirective:
    action: str  # "approve" | "reject" | "redirect" | "edit"
    target_stage: str | None = None
    reason: str | None = None
    edit: dict[str, Any] | None = None

    @classmethod
    def approve(cls) -> "HitlDirective":
        return cls(action="approve")

    @classmethod
    def reject(cls, reason: str) -> "HitlDirective":
        return cls(action="reject", reason=reason)

    @classmethod
    def redirect(cls, *, target_stage: str, reason: str) -> "HitlDirective":
        return cls(action="redirect", target_stage=target_stage, reason=reason)

    @classmethod
    def edit(cls, *, edit: dict[str, Any]) -> "HitlDirective":
        return cls(action="edit", edit=edit)

    def payload(self) -> dict[str, Any]:
        out: dict[str, Any] = {"action": self.action}
        if self.target_stage is not None:
            out["target_stage"] = self.target_stage
        if self.reason is not None:
            out["reason"] = self.reason
        if self.edit is not None and not callable(self.edit):
            out["edit"] = self.edit
        return out


@dataclass
class ContextShape:
    """Deterministic mutations applied to PipelineState before running a station.

    All fields default to no-op. Only set the ones needed to steer the target branch.
    """
    max_stage_iterations: int | None = None
    clear_artifacts: list[str] = field(default_factory=list)
    set_artifacts: dict[str, Any] = field(default_factory=dict)
    backtrack_budget: int | None = None
    extra_state: dict[str, Any] = field(default_factory=dict)


def apply_context_shape(state: dict[str, Any], shape: ContextShape) -> dict[str, Any]:
    """Return a deep-copied state with the shape applied. Input is never mutated."""
    out = copy.deepcopy(state)
    if shape.max_stage_iterations is not None:
        out["max_stage_iterations"] = shape.max_stage_iterations
    if shape.backtrack_budget is not None:
        out["backtrack_budget"] = shape.backtrack_budget
    artifacts = out.setdefault("artifacts", {})
    for name in shape.clear_artifacts:
        artifacts.pop(name, None)
    for name, value in shape.set_artifacts.items():
        artifacts[name] = value
    for k, v in shape.extra_state.items():
        out[k] = v
    return out
