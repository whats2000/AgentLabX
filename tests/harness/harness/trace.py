"""Trace artifact writer. Writes a stable JSON schema to tests/harness/runs/<ts>/<test_id>.json."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from tests.harness.contracts.base import HarnessTrace


def write_trace_artifact(trace: HarnessTrace, *, root: Path) -> Path:
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = root / ts
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{trace.test_id}.json"

    by_sev: dict[str, int] = {}
    passed = 0
    failed = 0
    for r in trace.results:
        if r.passed:
            passed += 1
        else:
            failed += 1
            if r.severity is not None:
                by_sev[r.severity.value] = by_sev.get(r.severity.value, 0) + 1

    payload = {
        "test_id": trace.test_id,
        "events": trace.events,
        "prompts": trace.prompts,
        "http": trace.http,
        "state_snapshots": trace.state_snapshots,
        "results": [
            {
                "contract_id": r.contract_id,
                "passed": r.passed,
                "severity": r.severity.value if r.severity else None,
                "detail": r.detail,
            }
            for r in trace.results
        ],
        "summary": {
            "total": len(trace.results),
            "passed": passed,
            "failed": failed,
            "by_severity": by_sev,
        },
    }
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return out_path
