from __future__ import annotations

import asyncio

import pytest

from agentlabx.llm.budget import BudgetTracker
from agentlabx.llm.protocol import BudgetExceededError


def test_initial_spend_is_zero() -> None:
    tracker = BudgetTracker(cap_usd=10.0)
    assert tracker.spent_usd == 0.0
    assert tracker.remaining_usd == 10.0


def test_record_increments_spend() -> None:
    tracker = BudgetTracker(cap_usd=10.0)
    tracker.record(cost_usd=2.5)
    assert tracker.spent_usd == 2.5
    assert tracker.remaining_usd == 7.5


def test_record_multiple_increments() -> None:
    tracker = BudgetTracker(cap_usd=10.0)
    tracker.record(cost_usd=1.0)
    tracker.record(cost_usd=2.0)
    tracker.record(cost_usd=3.0)
    assert tracker.spent_usd == 6.0
    assert tracker.remaining_usd == 4.0


def test_check_raises_when_cap_exceeded() -> None:
    tracker = BudgetTracker(cap_usd=5.0)
    tracker.record(cost_usd=4.0)
    tracker.check()  # should not raise — still under cap
    tracker.record(cost_usd=2.0)  # now at 6.0 > 5.0
    with pytest.raises(BudgetExceededError) as exc_info:
        tracker.check()
    assert exc_info.value.spent == 6.0
    assert exc_info.value.cap == 5.0


def test_check_raises_at_exact_cap() -> None:
    tracker = BudgetTracker(cap_usd=5.0)
    tracker.record(cost_usd=5.0)
    # At exact cap — should NOT raise (only raises when strictly exceeded)
    tracker.check()


def test_no_cap_never_raises() -> None:
    tracker = BudgetTracker(cap_usd=None)
    tracker.record(cost_usd=99999.0)
    tracker.check()  # no cap → never raises
    assert tracker.spent_usd == 99999.0
    assert tracker.remaining_usd is None


def test_zero_cost_record() -> None:
    tracker = BudgetTracker(cap_usd=10.0)
    tracker.record(cost_usd=0.0)
    assert tracker.spent_usd == 0.0


def test_call_count() -> None:
    tracker = BudgetTracker(cap_usd=10.0)
    assert tracker.call_count == 0
    tracker.record(cost_usd=1.0)
    tracker.record(cost_usd=0.0)
    assert tracker.call_count == 2


def test_summary() -> None:
    tracker = BudgetTracker(cap_usd=10.0)
    tracker.record(cost_usd=3.5)
    tracker.record(cost_usd=1.5)
    summary = tracker.summary()
    assert summary["spent_usd"] == 5.0
    assert summary["cap_usd"] == 10.0
    assert summary["remaining_usd"] == 5.0
    assert summary["call_count"] == 2


@pytest.mark.asyncio
async def test_record_async_is_concurrency_safe() -> None:
    """Multiple concurrent record_async calls produce correct totals."""
    tracker = BudgetTracker(cap_usd=None)

    async def record_many(n: int, cost: float) -> None:
        for _ in range(n):
            await tracker.record_async(cost_usd=cost)

    await asyncio.gather(
        record_many(100, 0.01),
        record_many(100, 0.01),
    )
    assert tracker.call_count == 200
    assert abs(tracker.spent_usd - 2.0) < 1e-9


@pytest.mark.asyncio
async def test_check_async_raises_when_exceeded() -> None:
    tracker = BudgetTracker(cap_usd=1.0)
    await tracker.record_async(cost_usd=2.0)
    with pytest.raises(BudgetExceededError):
        await tracker.check_async()
