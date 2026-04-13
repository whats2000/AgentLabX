"""Priority-based transition handler for pipeline stage routing."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from agentlabx.core.session import SessionPreferences
from agentlabx.core.state import PipelineState
from agentlabx.core.zones import cross_zone


class TransitionDecision(BaseModel):
    """Result of TransitionHandler.decide()."""

    next_stage: str | None
    action: Literal[
        "advance",
        "backtrack",
        "forced_advance",
        "complete",
        "human_override",
        "backtrack_limit_exceeded",
    ]
    reason: str
    needs_approval: bool = False


class TransitionHandler:
    """Determines the next stage using a priority-ordered decision chain.

    Priority:
    1. human_override (explicit user routing instruction)
    2. total_iterations >= max_total_iterations → complete
    3. backtrack requested + (per-edge attempts OR cost fraction exceeded)
       → backtrack_limit_exceeded (handler owns fallback, returns concrete next_stage)
    4. stage iteration limit reached + next_stage hint → forced_advance
    5. next_stage hint within stage limit → follow hint (backtrack or advance)
    6. no hint → advance to next stage in default_sequence
    7. end of sequence → complete
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

        # ── Priority 3: backtrack retry/cost gate ────────────────────────────
        # Self-loops (next_hint == current_stage) are not backtracks by
        # _is_backtrack's definition and bypass this gate — they're gated
        # only by stage iteration limits (Priority 4).
        if next_hint is not None and self._is_backtrack(
            next_hint, current_stage, default_sequence
        ):
            edge_key = f"{current_stage}->{next_hint}"
            attempts = state.get("backtrack_attempts", {}).get(edge_key, 0)
            per_edge_limit = self.preferences.max_backtrack_attempts_per_edge

            escalate_reason: str | None = None
            if attempts >= per_edge_limit:
                escalate_reason = (
                    f"Per-edge backtrack limit reached for "
                    f"'{edge_key}' ({attempts}/{per_edge_limit})"
                )

            cost_tracker = state.get("cost_tracker")
            total_cost = float(cost_tracker.total_cost) if cost_tracker else 0.0
            cost_spent = float(state.get("backtrack_cost_spent", 0.0))
            if total_cost > 0.0:
                fraction = cost_spent / total_cost
                if (
                    fraction >= self.preferences.max_backtrack_cost_fraction
                    and escalate_reason is None
                ):
                    escalate_reason = (
                        f"Cumulative backtrack cost fraction "
                        f"{fraction:.2f} >= limit "
                        f"{self.preferences.max_backtrack_cost_fraction:.2f}"
                    )

            if escalate_reason is not None:
                # Handler owns the fallback — compute next_in_sequence here
                # so transition_node just applies the decision.
                fallback = self._next_in_sequence(
                    current_stage, default_sequence, completed_stages
                )
                return TransitionDecision(
                    next_stage=fallback,
                    action="backtrack_limit_exceeded",
                    reason=escalate_reason,
                    needs_approval=True,
                )

        # ── Priority 4 & 5: next_stage hint exists ────────────────────────────
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

        # ── Priority 6: no hint — advance to next stage in sequence ─────────
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

        # ── Priority 7: reached end of sequence ──────────────────────────────
        return TransitionDecision(
            next_stage=None,
            action="complete",
            reason="Reached end of default_sequence",
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
        completed: list[str],  # kept for signature stability (still used by callers) but unused here
    ) -> str | None:
        """Return the stage immediately after `current` in the sequence, or None if at end.

        Does NOT filter by completed_stages. Re-running a stage is expected after
        a backtrack (or after a human override routes back into an earlier stage)
        — the stage itself decides whether it actually needs to redo work (via
        its bypass/plan logic in Plan 7B). completed_stages remains a history
        ledger for observability, not a routing filter.
        """
        try:
            start = sequence.index(current) + 1
        except ValueError:
            return None
        if start >= len(sequence):
            return None
        return sequence[start]

    def _check_approval(self, *, action: str, stage: str, target: str) -> bool:
        """Zone-aware HITL approval (spec §3.3.3).

        Per-stage control overrides (highest priority):
          "approve"/"edit" → always approve
          "auto"           → never approve
        Zone-aware defaults:
          advance          → no approval (notify only, even cross-zone)
          backtrack        → approve iff cross-zone OR backtrack_control=approve

        A stage with zone=None (e.g. lab_meeting) is treated as cross-zone
        on either side, so backtracks involving it always trigger approval.
        """
        sc = self.preferences.stage_controls.get(stage)
        if sc in ("approve", "edit"):
            return True
        if sc == "auto":
            return False

        if action == "backtrack":
            if self.preferences.backtrack_control == "approve":
                return True
            return cross_zone(stage, target)

        # advance / forced_advance / human_override default: no approval
        return False
