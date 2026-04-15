"""Input + output contracts for each internal subgraph node: enter, stage_plan,
gate, work, evaluate, decide.

Input contracts verify the model saw the correct context at this node (prompt
includes required fields). Output contracts verify the node emitted the right
events and wrote the right state.

Note: the agent_llm_request event does NOT carry a `node` field (TurnContext only
tracks stage, per Plan 8 T9b). Input contracts distinguish stage-level nodes by
inspecting the `agent` field (different nodes call different agents: stage_plan
uses a planner, work uses a worker, evaluate uses an evaluator).
"""
from __future__ import annotations

from tests.harness.contracts.base import Contract, ContractResult, HarnessTrace, Severity


# -------- ENTER ----------

def _enter_emits_event_for_stage(trace: HarnessTrace, *, stage_name: str) -> ContractResult:
    cid = f"stage_nodes.enter.emits_event[{stage_name}]"
    events = [
        e for e in trace.events_of_type("stage_internal_node_changed")
        if e.get("data", {}).get("internal_node") == "enter"
        and e.get("data", {}).get("stage") == stage_name
    ]
    if not events:
        return ContractResult.fail(
            cid, severity=Severity.P1,
            detail=f"no stage_internal_node_changed(enter,{stage_name}) event",
        )
    # B4 regression — ensure no event has empty stage
    for e in events:
        if not e.get("data", {}).get("stage"):
            return ContractResult.fail(
                cid, severity=Severity.P1,
                detail="enter event has empty 'stage' field (B4 regression)",
            )
    return ContractResult.ok(cid)


def enter_emits_event(*, stage_name: str) -> Contract:
    return Contract(
        id=f"stage_nodes.enter.emits_event[{stage_name}]",
        check=lambda t: _enter_emits_event_for_stage(t, stage_name=stage_name),
    )


# -------- STAGE_PLAN ----------

def _stage_plan_persists_plan(trace: HarnessTrace, *, stage_name: str) -> ContractResult:
    cid = f"stage_nodes.stage_plan.persisted[{stage_name}]"
    events = [
        e for e in trace.events_of_type("stage_plan_persisted")
        if e.get("data", {}).get("stage") == stage_name
        or e.get("stage") == stage_name  # tolerate both shapes
    ]
    if not events:
        return ContractResult.fail(
            cid, severity=Severity.P1,
            detail=f"no stage_plan_persisted event for {stage_name}",
        )
    return ContractResult.ok(cid)


def stage_plan_persisted(*, stage_name: str) -> Contract:
    return Contract(
        id=f"stage_nodes.stage_plan.persisted[{stage_name}]",
        check=lambda t: _stage_plan_persists_plan(t, stage_name=stage_name),
    )


# -------- WORK ----------

def _work_emits_agent_turn(trace: HarnessTrace, *, stage_name: str) -> ContractResult:
    cid = f"stage_nodes.work.emits_agent_turn[{stage_name}]"
    starts = [
        e for e in trace.events_of_type("agent_turn_started")
        if (e.get("data", {}).get("stage") == stage_name
            or e.get("stage") == stage_name)
    ]
    if not starts:
        return ContractResult.fail(
            cid, severity=Severity.P1,
            detail=f"no agent_turn_started during {stage_name}.work",
        )
    return ContractResult.ok(cid)


def work_emits_agent_turn(*, stage_name: str) -> Contract:
    return Contract(
        id=f"stage_nodes.work.emits_agent_turn[{stage_name}]",
        check=lambda t: _work_emits_agent_turn(t, stage_name=stage_name),
    )


def _work_prompt_mentions_plan_items(trace: HarnessTrace, *, stage_name: str) -> ContractResult:
    """Input contract: the LLM prompt for this stage must reference plan item ids
    that were persisted. Uses stage filter (node unavailable per T9b)."""
    cid = f"stage_nodes.work.prompt_includes_plan_items[{stage_name}]"
    # Find plan items from a snapshot taken before this stage ran
    before_key = f"before_{stage_name}"
    snap = trace.state_snapshots.get(before_key, {})
    plan = (snap.get("stage_plans") or {}).get(stage_name) or {}
    items = plan.get("items") or []
    if not items:
        return ContractResult.ok(cid)  # no plan items = nothing to check

    prompts = [p for p in trace.prompts if p.get("stage") == stage_name]
    if not prompts:
        return ContractResult.fail(
            cid, severity=Severity.P1,
            detail=f"no captured prompts for stage {stage_name}",
        )
    blob = " ".join(
        (p.get("system") or "") + " ".join(m.get("content", "") for m in p.get("messages", []))
        for p in prompts
    )
    missing = [item.get("id") for item in items if item.get("id") and str(item.get("id")) not in blob]
    if missing:
        return ContractResult.fail(
            cid, severity=Severity.P1,
            detail=f"stage prompts missing plan item ids: {missing}",
        )
    return ContractResult.ok(cid)


def work_prompt_includes_plan_items(*, stage_name: str) -> Contract:
    return Contract(
        id=f"stage_nodes.work.prompt_includes_plan_items[{stage_name}]",
        check=lambda t: _work_prompt_mentions_plan_items(t, stage_name=stage_name),
    )


# -------- EVALUATE ----------

def _evaluate_respects_iteration_bound(trace: HarnessTrace, *, stage_name: str) -> ContractResult:
    cid = f"stage_nodes.evaluate.respects_iteration_bound[{stage_name}]"
    after = trace.state_snapshots.get(f"after_{stage_name}", {})
    # max_stage_iterations is a per-stage dict in PipelineState, not a flat int
    raw = after.get("max_stage_iterations", {})
    if isinstance(raw, dict):
        max_iter = raw.get(stage_name, 10)
    else:
        max_iter = raw if isinstance(raw, int) else 10
    iters = [
        e for e in trace.events_of_type("stage_internal_node_changed")
        if e.get("data", {}).get("internal_node") == "evaluate"
        and e.get("data", {}).get("stage") == stage_name
    ]
    if len(iters) > max_iter:
        return ContractResult.fail(
            cid, severity=Severity.P0,
            detail=f"evaluate ran {len(iters)} times; max_stage_iterations={max_iter} (unbounded)",
        )
    return ContractResult.ok(cid)


def evaluate_respects_iteration_bound(*, stage_name: str) -> Contract:
    return Contract(
        id=f"stage_nodes.evaluate.respects_iteration_bound[{stage_name}]",
        check=lambda t: _evaluate_respects_iteration_bound(t, stage_name=stage_name),
    )


# -------- DECIDE ----------

def _decide_pause_contract(trace: HarnessTrace, *, stage_name: str) -> ContractResult:
    cid = f"stage_nodes.decide.pause_contract[{stage_name}]"
    after = trace.state_snapshots.get(f"after_{stage_name}", {})
    needs_approval = after.get("needs_approval", False)
    checkpoints = [
        e for e in trace.events_of_type("checkpoint_reached")
        if (e.get("data", {}).get("stage") == stage_name or e.get("stage") == stage_name)
    ]
    if not needs_approval:
        return ContractResult.ok(cid)
    if not checkpoints:
        return ContractResult.fail(
            cid, severity=Severity.P1,
            detail="decide said needs_approval=True but no checkpoint_reached emitted",
        )
    for e in checkpoints:
        data = e.get("data") or {}
        if "control_mode" not in data:
            return ContractResult.fail(
                cid, severity=Severity.P2,
                detail="checkpoint_reached missing control_mode field (Plan 7E C1 regression)",
            )
    return ContractResult.ok(cid)


def decide_pause_contract(*, stage_name: str) -> Contract:
    return Contract(
        id=f"stage_nodes.decide.pause_contract[{stage_name}]",
        check=lambda t: _decide_pause_contract(t, stage_name=stage_name),
    )


# -------- TOOL USAGE ----------

def _stage_emits_tool_call(trace: HarnessTrace, *, stage_name: str) -> ContractResult:
    """Verify the stage actually called a tool. For literature_review, experimentation,
    etc. that require external data fetches, missing tool_call events mean the agent
    either hallucinated output or the stage skipped the fetch."""
    cid = f"stage_nodes.tool_usage.at_least_one_tool_call[{stage_name}]"
    # Look for agent_tool_call events associated with this stage (via data.stage)
    tool_calls = [
        e for e in trace.events_of_type("agent_tool_call")
        if e.get("data", {}).get("stage") == stage_name
    ]
    if not tool_calls:
        return ContractResult.fail(
            cid, severity=Severity.P1,
            detail=f"no agent_tool_call events during {stage_name} — tool-using stage didn't call any tool",
        )
    return ContractResult.ok(cid)


def stage_emits_tool_call(*, stage_name: str) -> Contract:
    return Contract(
        id=f"stage_nodes.tool_usage.at_least_one_tool_call[{stage_name}]",
        check=lambda t: _stage_emits_tool_call(t, stage_name=stage_name),
    )
