from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

_MAX_FAILURES = 5
_WINDOW_SECONDS = 5 * 60
_LOCKOUT_SECONDS = 15 * 60


@dataclass
class _EmailState:
    failures: list[float] = field(default_factory=list)
    locked_until: float = 0.0


class LoginRateLimiter:
    """Per-email sliding-window failure counter with lockout. In-memory, process-local."""

    def __init__(
        self,
        *,
        max_failures: int = _MAX_FAILURES,
        window_seconds: int = _WINDOW_SECONDS,
        lockout_seconds: int = _LOCKOUT_SECONDS,
    ) -> None:
        self._max_failures = max_failures
        self._window = window_seconds
        self._lockout = lockout_seconds
        self._state: dict[str, _EmailState] = {}
        self._lock = threading.Lock()

    def _now(self) -> float:
        return time.monotonic()

    def check(self, email: str) -> float | None:
        """Return the seconds-until-unlock if currently locked, else None."""
        key = email.strip().lower()
        with self._lock:
            st = self._state.get(key)
            if st is None:
                return None
            now = self._now()
            if st.locked_until > now:
                return st.locked_until - now
            return None

    def record_failure(self, email: str) -> float | None:
        """Record a failure. Return seconds-until-unlock if this triggered a lockout."""
        key = email.strip().lower()
        with self._lock:
            st = self._state.setdefault(key, _EmailState())
            now = self._now()
            # drop failures outside the window
            st.failures = [t for t in st.failures if now - t <= self._window]
            st.failures.append(now)
            if len(st.failures) >= self._max_failures:
                st.locked_until = now + self._lockout
                st.failures.clear()
                return float(self._lockout)
        return None

    def record_success(self, email: str) -> None:
        key = email.strip().lower()
        with self._lock:
            self._state.pop(key, None)
