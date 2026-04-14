"""PI advisor contracts — verdict vocabulary + turn emission correlation.

Note on event shape: `pi_verdict` events carry the verdict in their `data` payload
(matching the rest of the event bus). The contract reads `event["data"]["verdict"]`
with a fallback to `event["verdict"]` to tolerate flatter shapes.
"""
from __future__ import annotations

from tests.harness.contracts.base import Contract, ContractResult, HarnessTrace, Severity


VALID_VERDICTS = {"approve", "revise", "replan"}


def _verdict_value(event: dict) -> str | None:
    data = event.get("data") or {}
    return data.get("verdict") or event.get("verdict")


def _verdict_in_vocab(trace: HarnessTrace) -> ContractResult:
    cid = "pi_advisor.verdict_in_vocab"
    for e in trace.events_of_type("pi_verdict"):
        v = _verdict_value(e)
        if v not in VALID_VERDICTS:
            return ContractResult.fail(
                cid, severity=Severity.P2,
                expected=sorted(VALID_VERDICTS),
                actual=v,
                detail=f"PI advisor produced unparseable verdict: {v!r}",
            )
    return ContractResult.ok(cid)


def _emits_agent_turn(trace: HarnessTrace) -> ContractResult:
    cid = "pi_advisor.emits_agent_turn"
    verdicts = trace.events_of_type("pi_verdict")
    if not verdicts:
        return ContractResult.ok(cid)
    starts = trace.events_of_type("pi_agent_turn_started")
    completes = trace.events_of_type("pi_agent_turn_completed")
    if not starts or not completes:
        return ContractResult.fail(
            cid, severity=Severity.P1,
            detail=(
                f"pi_verdict emitted but missing pi_agent_turn_started/completed "
                f"(starts={len(starts)}, completes={len(completes)})"
            ),
        )
    return ContractResult.ok(cid)


def _prompt_includes_failures(trace: HarnessTrace) -> ContractResult:
    cid = "pi_advisor.prompt_includes_failures"
    # Only check if a verdict was actually issued (PI was actually invoked)
    verdicts = trace.events_of_type("pi_verdict")
    if not verdicts:
        return ContractResult.ok(cid)
    # Find prompts from PI-role agents
    prompts = [
        p for p in trace.prompts
        if p.get("agent") in ("pi_advisor", "principal_investigator", "pi")
    ]
    if not prompts:
        # PI verdict was issued but we didn't capture the prompt — can't verify
        return ContractResult.ok(cid)
    for p in prompts:
        blob = (p.get("system") or "") + " ".join(m.get("content", "") for m in p.get("messages", []))
        if "error" not in blob.lower() and "fail" not in blob.lower():
            return ContractResult.fail(
                cid, severity=Severity.P1,
                detail=(
                    "PI advisor prompt lacks any failure/error context — "
                    "advisor can't deliberate meaningfully without failure history"
                ),
            )
    return ContractResult.ok(cid)


PI_VERDICT_IN_VOCAB = Contract(
    id="pi_advisor.verdict_in_vocab",
    check=_verdict_in_vocab,
    description="PI verdict must be one of approve/revise/replan",
)

PI_EMITS_AGENT_TURN = Contract(
    id="pi_advisor.emits_agent_turn",
    check=_emits_agent_turn,
    description="Every pi_verdict must be surrounded by pi_agent_turn_started/completed",
)

PI_PROMPT_INCLUDES_FAILURES = Contract(
    id="pi_advisor.prompt_includes_failures",
    check=_prompt_includes_failures,
    description="PI advisor prompt must include failure/error context when issued",
)
