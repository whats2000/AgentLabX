from __future__ import annotations

from agentlabx.server.rate_limit import LoginRateLimiter


def test_under_threshold_not_locked() -> None:
    lim = LoginRateLimiter(max_failures=3, window_seconds=60, lockout_seconds=120)
    assert lim.record_failure("a@x.com") is None
    assert lim.record_failure("a@x.com") is None
    assert lim.check("a@x.com") is None


def test_threshold_triggers_lock() -> None:
    lim = LoginRateLimiter(max_failures=3, window_seconds=60, lockout_seconds=120)
    assert lim.record_failure("a@x.com") is None
    assert lim.record_failure("a@x.com") is None
    locked = lim.record_failure("a@x.com")
    assert locked is not None
    assert 0 < locked <= 120
    remaining = lim.check("a@x.com")
    assert remaining is not None


def test_success_resets_counter() -> None:
    lim = LoginRateLimiter(max_failures=3, window_seconds=60, lockout_seconds=120)
    lim.record_failure("a@x.com")
    lim.record_failure("a@x.com")
    lim.record_success("a@x.com")
    assert lim.record_failure("a@x.com") is None  # counter reset, no lock


def test_email_is_normalized() -> None:
    lim = LoginRateLimiter(max_failures=2, window_seconds=60, lockout_seconds=60)
    lim.record_failure("A@X.com")
    locked = lim.record_failure("  a@x.COM ")
    assert locked is not None  # same key after normalization
