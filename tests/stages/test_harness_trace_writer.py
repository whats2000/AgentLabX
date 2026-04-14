from __future__ import annotations

import json
from pathlib import Path

from tests.harness.contracts.base import ContractResult, HarnessTrace, Severity
from tests.harness.harness.trace import write_trace_artifact


def test_writer_emits_json_with_all_sections(tmp_path: Path):
    trace = HarnessTrace(test_id="spine.literature_review")
    trace.record_event({"type": "stage_started", "stage": "literature_review"})
    trace.record_prompt(
        node="work",
        stage="literature_review",
        agent="phd_student",
        messages=[{"role": "user", "content": "..."}],
    )
    trace.record_http(method="GET", path="/graph", status=200, body={"nodes": []})
    trace.snapshot("after_literature_review", {"current_stage": "plan_formulation"})
    trace.results.append(ContractResult.ok("enter_emits_event"))
    trace.results.append(
        ContractResult.fail("work_sees_items", severity=Severity.P1, actual=0, expected=">=1")
    )

    path = write_trace_artifact(trace, root=tmp_path)
    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["test_id"] == "spine.literature_review"
    assert len(data["events"]) == 1
    assert len(data["prompts"]) == 1
    assert len(data["http"]) == 1
    assert "after_literature_review" in data["state_snapshots"]
    assert data["summary"]["total"] == 2
    assert data["summary"]["passed"] == 1
    assert data["summary"]["failed"] == 1
    assert data["summary"]["by_severity"] == {"P1": 1}
