"""Contract base types — pure dataclasses, no live-model coupling."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


class Severity(str, Enum):
    P0 = "P0"  # blocker: deadlock, unbounded, non-terminating
    P1 = "P1"  # critical: wrong/missing context (system-side)
    P2 = "P2"  # second critical: model fails to follow directive
    P3 = "P3"  # observational: unexpected but defensible


@dataclass
class ContractResult:
    contract_id: str
    passed: bool
    severity: Severity | None = None
    actual: Any = None
    expected: Any = None
    detail: str = ""

    @classmethod
    def ok(cls, contract_id: str) -> "ContractResult":
        return cls(contract_id=contract_id, passed=True)

    @classmethod
    def fail(
        cls,
        contract_id: str,
        *,
        severity: Severity,
        actual: Any = None,
        expected: Any = None,
        detail: str = "",
    ) -> "ContractResult":
        parts = [detail] if detail else []
        if expected is not None or actual is not None:
            parts.append(f"expected={expected!r} actual={actual!r}")
        return cls(
            contract_id=contract_id,
            passed=False,
            severity=severity,
            actual=actual,
            expected=expected,
            detail=" | ".join(parts) or contract_id,
        )


@dataclass
class HarnessTrace:
    test_id: str
    events: list[dict[str, Any]] = field(default_factory=list)
    prompts: list[dict[str, Any]] = field(default_factory=list)
    http: list[dict[str, Any]] = field(default_factory=list)
    state_snapshots: dict[str, dict[str, Any]] = field(default_factory=dict)
    results: list[ContractResult] = field(default_factory=list)

    def record_event(self, event: dict[str, Any]) -> None:
        self.events.append(event)

    def record_prompt(
        self,
        *,
        node: str,
        stage: str,
        agent: str,
        messages: list[dict[str, Any]],
        system: str | None = None,
        tools: list[str] | None = None,
    ) -> None:
        self.prompts.append({
            "node": node,
            "stage": stage,
            "agent": agent,
            "messages": messages,
            "system": system,
            "tools": tools or [],
        })

    def record_http(self, *, method: str, path: str, status: int, body: Any) -> None:
        self.http.append({"method": method, "path": path, "status": status, "body": body})

    def snapshot(self, label: str, state: dict[str, Any]) -> None:
        self.state_snapshots[label] = dict(state)

    def events_of_type(self, event_type: str) -> list[dict[str, Any]]:
        return [e for e in self.events if e.get("type") == event_type]

    def prompts_for(self, *, node: str | None = None, stage: str | None = None) -> list[dict[str, Any]]:
        out = self.prompts
        if node:
            out = [p for p in out if p["node"] == node]
        if stage:
            out = [p for p in out if p["stage"] == stage]
        return out


@dataclass
class Contract:
    id: str
    check: Callable[[HarnessTrace], ContractResult]
    description: str = ""

    def run(self, trace: HarnessTrace) -> ContractResult:
        return self.check(trace)
