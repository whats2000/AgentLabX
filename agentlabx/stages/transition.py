"""Priority-based transition handler for pipeline stage routing."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from agentlabx.core.session import SessionPreferences
from agentlabx.core.state import PipelineState


class TransitionDecision(BaseModel):
    """Result of TransitionHandler.decide()."""

    next_stage: str | None
    action: str  # "advance", "backtrack", "forced_advance", "complete", "human_override"
    reason: str
    needs_approval: bool = False


class TransitionHandler:
    """Determines the next stage using a priority-ordered decision chain.

    Priority:
    1. human_override (explicit user routing instruction)
    2. total_iterations >= max_total_iterations → complete
    3. stage iteration limit reached + next_stage hint → forced_advance
    4. next_stage hint within stage limit → follow hint (backtrack or advance)
    5. no hint → advance to next uncompleted stage in default_sequence
    6. all stages complete → complete
    """

    def __init__(
        self,
        preferences: SessionPreferences | None = None,
    ) -> None:
        self.preferences = preferences or SessionPreferences()

    def decide(self, state: PipelineState) -> TransitionDecision:
        """Return a TransitionDecision based on current pipeline state."""
        current_stage: str = state.get("current_stage", "")
        next_hint: str | None = state.get("next_stage")
        human_override: str | None = state.get("human_override")
        total_iterations: int = state.get("total_iterations", 0)
        max_total: int = state.get("max_total_iterations", 50)
        stage_iterations: dict[str, int] = state.get("stage_iterations", {})
        max_stage_iters: dict[str, int] = state.get("max_stage_iterations", {})
        default_sequence: list[str] = state.get("default_sequence", [])
        completed_stages: list[str] = state.get("completed_stages", [])

        # ── Priority 1: human override ────────────────────────────────────────
        if human_override:
            return TransitionDecision(
                next_stage=human_override,
                action="human_override",
                reason=f"Human override: route to '{human_override}'",
                needs_approval=False,
            )

        # ── Priority 2: total iteration ceiling ───────────────────────────────
        if total_iterations >= max_total:
            return TransitionDecision(
                next_stage=None,
                action="complete",
                reason=f"Total iteration limit reached ({total_iterations}/{max_total})",
                needs_approval=False,
            )

        # ── Helper: is the current stage at its iteration limit? ──────────────
        stage_limit = max_stage_iters.get(current_stage, 0)
        current_iters = stage_iterations.get(current_stage, 0)
        at_stage_limit = stage_limit > 0 and current_iters >= stage_limit

        # ── Priority 3 & 4: next_stage hint exists ────────────────────────────
        if next_hint is not None:
            if at_stage_limit:
                # Stage is exhausted — skip the hint, advance in sequence instead
                forced_next = self._next_in_sequence(
                    current_stage, default_sequence, completed_stages
                )
                return TransitionDecision(
                    next_stage=forced_next,
                    action="forced_advance",
                    reason=(
                        f"Stage '{current_stage}' hit iteration limit "
                        f"({current_iters}/{stage_limit}); ignoring hint '{next_hint}'"
                    ),
                    needs_approval=False,
                )

            # Detect backtrack: hint points to an earlier position in sequence
            is_backtrack = self._is_backtrack(next_hint, current_stage, default_sequence)
            action = "backtrack" if is_backtrack else "advance"

            needs_approval = self._check_approval(
                action=action,
                stage=current_stage,
                target=next_hint,
            )
            return TransitionDecision(
                next_stage=next_hint,
                action=action,
                reason=f"Following stage hint: '{current_stage}' → '{next_hint}'",
                needs_approval=needs_approval,
            )

        # ── Priority 5: no hint — advance to next uncompleted stage ──────────
        next_in_seq = self._next_in_sequence(current_stage, default_sequence, completed_stages)
        if next_in_seq is not None:
            needs_approval = self._check_approval(
                action="advance",
                stage=current_stage,
                target=next_in_seq,
            )
            return TransitionDecision(
                next_stage=next_in_seq,
                action="advance",
                reason=f"Advancing to next stage in sequence: '{next_in_seq}'",
                needs_approval=needs_approval,
            )

        # ── Priority 6: all done ──────────────────────────────────────────────
        return TransitionDecision(
            next_stage=None,
            action="complete",
            reason="All stages in default_sequence are complete",
            needs_approval=False,
        )

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _is_backtrack(
        self,
        target: str,
        current: str,
        sequence: list[str],
    ) -> bool:
        """Return True if target is earlier in the sequence than current."""
        try:
            target_idx = sequence.index(target)
            current_idx = sequence.index(current)
            return target_idx < current_idx
        except ValueError:
            return False

    def _next_in_sequence(
        self,
        current: str,
        sequence: list[str],
        completed: list[str],
    ) -> str | None:
        """Return the first stage after current that isn't completed, or None."""
        try:
            start = sequence.index(current) + 1
        except ValueError:
            start = 0

        for stage in sequence[start:]:
            if stage not in completed:
                return stage
        return None

    def _check_approval(self, *, action: str, stage: str, target: str) -> bool:
        """Return True if this transition requires human approval (HITL)."""
        # Check per-stage control for the originating stage
        stage_control = self.preferences.get_stage_control(stage)
        if stage_control == "approve" or stage_control == "edit":
            return True

        # Check backtrack control preference
        if action == "backtrack" and self.preferences.backtrack_control == "approve":
            return True

        return False
