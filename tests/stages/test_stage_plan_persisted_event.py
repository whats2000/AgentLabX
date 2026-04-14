"""ARCH-1 (Plan 8): plan_node must emit stage_plan_persisted event after writing plan to state."""
from __future__ import annotations

import pytest

from agentlabx.stages.literature_review import LiteratureReviewStage
from agentlabx.stages.subgraph import StageSubgraphBuilder
from agentlabx.stages.base import StageContext


@pytest.mark.asyncio
async def test_plan_node_emits_stage_plan_persisted():
    stage = LiteratureReviewStage()
    compiled = StageSubgraphBuilder().compile(stage)

    events_seen: list[dict] = []

    class StubBus:
        async def emit(self, event):
            events_seen.append({
                "type": getattr(event, "type", ""),
                "data": getattr(event, "data", {}),
                "source": getattr(event, "source", ""),
            })

    ctx = StageContext(event_bus=StubBus())
    state = {
        "research_topic": "x",
        "current_stage": "",
        "goals": [],
        "artifacts": {},
        "stage_plans": {},
        "session_id": "test-session",
    }

    try:
        await compiled.ainvoke({"state": state, "context": ctx})
    except Exception:
        pass  # downstream nodes may fail without real LLM; we only need plan_node to have emitted

    persisted = [e for e in events_seen if e.get("type") == "stage_plan_persisted"]
    assert persisted, f"expected stage_plan_persisted event, saw: {[e.get('type') for e in events_seen]}"

    # Check the event carries the stage name
    for e in persisted:
        assert e["data"].get("stage") == "literature_review", (
            f"stage_plan_persisted event missing/wrong stage: {e}"
        )
        # items_count field is expected
        assert "items_count" in e["data"], f"missing items_count: {e}"
