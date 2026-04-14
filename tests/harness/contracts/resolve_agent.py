"""resolve_agent input contract — verify the agent that just ran used the
configured provider+model, not a hardcoded fallback."""
from __future__ import annotations

from tests.harness.contracts.base import Contract, ContractResult, HarnessTrace, Severity


def _model_matches_expected(trace: HarnessTrace, *, expected_prefix: str) -> ContractResult:
    cid = "resolve_agent.model_plumbed"
    for event in trace.events_of_type("agent_llm_request"):
        # Real event carries `data.model` (see Plan 8 T4 findings)
        data = event.get("data") or {}
        model = data.get("model", "")
        if not model:
            return ContractResult.fail(
                cid,
                severity=Severity.P1,
                detail=f"agent_llm_request event missing data.model: {event}",
            )
        if not model.startswith(expected_prefix):
            return ContractResult.fail(
                cid,
                severity=Severity.P1,
                expected=f"{expected_prefix}*",
                actual=model,
                detail=f"agent used wrong model — likely hardcoded fallback (B2 regression)",
            )
    return ContractResult.ok(cid)


def model_plumbed_contract(*, expected_prefix: str) -> Contract:
    return Contract(
        id="resolve_agent.model_plumbed",
        check=lambda trace: _model_matches_expected(trace, expected_prefix=expected_prefix),
        description=f"Every agent_llm_request must use a model starting with '{expected_prefix}'",
    )
