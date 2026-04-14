"""B2 regression for PIAgent — model is plumbed from StageContext.model /
settings, not hardcoded. Complements Plan 8 T9 which covered resolve_agent."""
from __future__ import annotations

from agentlabx.agents.pi_agent import PIAgent


def test_pi_agent_accepts_none_model():
    """PIAgent should accept model=None (receives it from executor when settings absent)."""
    agent = PIAgent(llm_provider=None, model=None)
    assert agent.model is None


def test_pi_agent_uses_passed_model():
    """PIAgent should store and use the passed model value."""
    agent = PIAgent(llm_provider=None, model="gemini/gemini-2.5-flash")
    assert agent.model == "gemini/gemini-2.5-flash"
