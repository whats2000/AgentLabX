from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.harness.harness.snapshots import SnapshotStore


def test_snapshot_round_trip(tmp_path: Path):
    store = SnapshotStore(root=tmp_path)
    state = {
        "research_topic": "x",
        "current_stage": "literature_review",
        "stage_plans": {"literature_review": {"items": [{"id": "a"}]}},
        "cost_tracker": {"usd": 0.01},
    }
    store.save("after_literature_review", state)

    loaded = store.load("after_literature_review")
    assert loaded["research_topic"] == "x"
    assert loaded["stage_plans"]["literature_review"]["items"][0]["id"] == "a"


def test_snapshot_missing_raises(tmp_path: Path):
    store = SnapshotStore(root=tmp_path)
    with pytest.raises(FileNotFoundError):
        store.load("nope")


def test_snapshot_list_sorted(tmp_path: Path):
    store = SnapshotStore(root=tmp_path)
    store.save("after_data_exploration", {"a": 1})
    store.save("after_literature_review", {"a": 1})
    assert store.list() == ["after_data_exploration", "after_literature_review"]


def test_snapshot_roundtrip_preserves_nested_lists_and_numbers(tmp_path: Path):
    """Fork tests rely on exact state reconstruction — verify no coercion."""
    store = SnapshotStore(root=tmp_path)
    state = {
        "transition_log": [
            {"from_stage": "literature_review", "to_stage": "plan_formulation", "turn": 0}
        ],
        "errors": [],
        "iteration_count": 3,
    }
    store.save("s", state)
    loaded = store.load("s")
    assert loaded == state
