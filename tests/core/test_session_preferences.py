from agentlabx.core.session import SessionPreferences


def test_retry_governance_defaults():
    p = SessionPreferences()
    assert p.max_backtrack_attempts_per_edge == 2
    assert p.max_backtrack_cost_fraction == 0.4


def test_retry_governance_overrides():
    p = SessionPreferences(
        max_backtrack_attempts_per_edge=5,
        max_backtrack_cost_fraction=0.6,
    )
    assert p.max_backtrack_attempts_per_edge == 5
    assert p.max_backtrack_cost_fraction == 0.6
