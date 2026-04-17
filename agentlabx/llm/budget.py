from __future__ import annotations

import asyncio

from agentlabx.llm.protocol import BudgetExceededError


class BudgetTracker:
    """Per-project LLM cost tracker with optional cap enforcement.

    Thread-safe under asyncio: record_async() and check_async() acquire an
    internal lock so concurrent calls cannot interleave spend updates.
    """

    def __init__(self, *, cap_usd: float | None) -> None:
        self._cap_usd = cap_usd
        self._spent_usd: float = 0.0
        self._call_count: int = 0
        self._lock: asyncio.Lock = asyncio.Lock()

    @property
    def spent_usd(self) -> float:
        return self._spent_usd

    @property
    def remaining_usd(self) -> float | None:
        if self._cap_usd is None:
            return None
        return self._cap_usd - self._spent_usd

    @property
    def call_count(self) -> int:
        return self._call_count

    def record(self, *, cost_usd: float) -> None:
        """Record the cost of an LLM call (sync — use record_async for lock)."""
        self._spent_usd += cost_usd
        self._call_count += 1

    async def record_async(self, *, cost_usd: float) -> None:
        """Record cost under the internal lock (concurrency-safe)."""
        async with self._lock:
            self._spent_usd += cost_usd
            self._call_count += 1

    def check(self) -> None:
        """Raise BudgetExceededError if spending has strictly exceeded the cap."""
        if self._cap_usd is not None and self._spent_usd > self._cap_usd:
            raise BudgetExceededError(spent=self._spent_usd, cap=self._cap_usd)

    async def check_async(self) -> None:
        """Check budget under the internal lock (concurrency-safe)."""
        async with self._lock:
            self.check()

    def summary(self) -> dict[str, float | int | None]:
        """Return a summary dict suitable for event payloads."""
        return {
            "spent_usd": self._spent_usd,
            "cap_usd": self._cap_usd,
            "remaining_usd": self.remaining_usd,
            "call_count": self._call_count,
        }
