"""Priority-based transition handler for pipeline stage routing."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from agentlabx.agents.pi_agent import ConsultKind, PIAgent
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
        pi_advisor: PIAgent | None = None,
    ) -> None:
        self.preferences = preferences or SessionPreferences()
        self.pi_advisor = pi_advisor

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
                    current_stage, default_sequence
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
                    current_stage, default_sequence
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
        next_in_seq = self._next_in_sequence(current_stage, default_sequence)
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

    async def decide_async(self, state: PipelineState) -> TransitionDecision:
        """Async variant that consults the PI advisor on escalation paths.

        When pi_advisor is None (default), behaviour is identical to sync
        decide() — zero overhead, zero semantic change from Plan 7A.

        Consultation checkpoints (in evaluation order):

        1. ConsultKind.BACKTRACK_LIMIT — when rule_decision.action is
           "backtrack_limit_exceeded". Advisor suggests a concrete next stage
           overriding the default-sequence force-advance. Returns early if
           advisor overrides.

        2. ConsultKind.NEGATIVE_RESULT — when last_stage_status is
           "negative_result" AND rule_decision.action is "advance" OR
           "backtrack". The advisor makes the content-level judgment
           (publish / pivot / redirect) even when the stage pre-chose a
           backtrack target. The action is re-derived from the advisor's
           chosen target. Returns early if advisor overrides.

        Other action types (forced_advance, complete, human_override,
        backtrack_limit_exceeded) never consult the advisor — PI is an
        advisor, NOT a router (spec §3.3.5).
        """
        rule_decision = self.decide(state)

        if self.pi_advisor is None:
            return rule_decision

        # ── Checkpoint 1: backtrack_limit_exceeded ────────────────────────────
        if rule_decision.action == "backtrack_limit_exceeded":
            current = state.get("current_stage", "")
            target = state.get("next_stage")  # the backtrack target the stage requested
            edge_key = f"{current}->{target}"
            attempts = state.get("backtrack_attempts", {}).get(edge_key, 0)
            max_attempts = self.preferences.max_backtrack_attempts_per_edge

            advice = await self.pi_advisor.consult_escalation(
                ConsultKind.BACKTRACK_LIMIT,
                state,
                context={
                    "origin": current,
                    "target": target,
                    "attempts": attempts,
                    "max_attempts": max_attempts,
                    "rule_fallback": rule_decision.next_stage,
                },
            )

            if not advice.used_fallback and advice.next_stage is not None:
                return TransitionDecision(
                    next_stage=advice.next_stage,
                    action="backtrack_limit_exceeded",
                    reason=f"PI advisor: {advice.reasoning}",
                    needs_approval=True,
                )

            return rule_decision

        # ── Checkpoint 2: negative_result (Plan 7C follow-up) ─────────────────
        # NEGATIVE_RESULT is a content-level judgment (publish / pivot / redirect),
        # not a routing concern. Consult the advisor whenever a stage concluded
        # with a refuted hypothesis — even if the stage chose a backtrack target
        # unilaterally. The advisor's choice wins (with confidence gate);
        # the action is re-derived from whether the advisor's target sits earlier
        # in the default sequence (→ backtrack) or later (→ advance).
        if (
            self.pi_advisor is not None
            and state.get("last_stage_status") == "negative_result"
            and rule_decision.action in ("advance", "backtrack")
        ):
            origin = state.get("current_stage", "")
            experiment_results = state.get("experiment_results") or []
            # hypothesis_id is best-effort — pulled from the most recent
            # experiment result when available. Non-experimentation stages
            # emitting negative_result will surface "unknown" (acceptable;
            # the advisor's prompt documents that "unknown" is valid).
            hypothesis_id = "unknown"
            if experiment_results:
                last_exp = experiment_results[-1]
                hypothesis_id = (
                    getattr(last_exp, "hypothesis_id", None) or "unknown"
                )

            advice = await self.pi_advisor.consult_escalation(
                ConsultKind.NEGATIVE_RESULT,
                state,
                context={
                    "origin": origin,
                    "hypothesis_id": hypothesis_id,
                    "rule_fallback": rule_decision.next_stage,
                },
            )

            if not advice.used_fallback and advice.next_stage is not None:
                is_backtrack = self._is_backtrack(
                    advice.next_stage,
                    state.get("current_stage", ""),
                    state.get("default_sequence") or [],
                )
                return TransitionDecision(
                    next_stage=advice.next_stage,
                    action="backtrack" if is_backtrack else "advance",
                    reason=f"PI advisor (negative result): {advice.reasoning}",
                    needs_approval=True,
                )

        return rule_decision

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
        # Both "approve" and "edit" pause for HITL approval, but the frontend
        # must render different UX (yes/no dialog vs edit-output form). Plan 7D
        # will surface this distinction through the CheckpointModal; for now
        # needs_approval=True is a sufficient router signal.
        # TODO(7D): propagate the specific control mode (approve vs edit) so
        # the CheckpointModal can pick the right form.
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
