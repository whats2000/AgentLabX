"""Snapshot store for Phase 1 → Phase 2 state handoff.

The spine captures a JSON snapshot of PipelineState at each station boundary.
Fork tests load the snapshot for the station where they want to deviate, rehydrate
it into a fresh PipelineExecutor, then drive the alternate branch.

State is plain JSON — any non-JSON fields (asyncio events, task handles) must be
filtered out before save and re-wired during load by the caller.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class SnapshotStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, label: str) -> Path:
        return self.root / f"{label}.json"

    def save(self, label: str, state: dict[str, Any]) -> None:
        payload = _jsonable(state)
        self._path(label).write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    def load(self, label: str) -> dict[str, Any]:
        p = self._path(label)
        if not p.exists():
            msg = f"Snapshot '{label}' not found at {p}. Run Phase 1 spine first."
            raise FileNotFoundError(msg)
        return json.loads(p.read_text(encoding="utf-8"))

    def list(self) -> list[str]:
        return sorted(p.stem for p in self.root.glob("*.json"))


def _jsonable(state: dict[str, Any]) -> dict[str, Any]:
    """Drop non-JSON-serializable fields (paused_event, asyncio tasks, etc.)."""
    out: dict[str, Any] = {}
    for k, v in state.items():
        try:
            json.dumps(v)
            out[k] = v
        except (TypeError, ValueError):
            continue
    return out
