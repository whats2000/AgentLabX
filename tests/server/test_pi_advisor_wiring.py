"""Verify PIAgent is constructed and wired into the pipeline when LLM is not mock."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from agentlabx.agents.pi_agent import PIAgent
from agentlabx.core.pipeline import PipelineBuilder


@pytest.mark.asyncio
async def test_executor_constructs_pi_advisor_for_real_llm(tmp_path, monkeypatch):
    """When session uses a real (non-mock) LLM provider, executor constructs a PIAgent."""
    from agentlabx.server.executor import PipelineExecutor
    from agentlabx.core.registry import PluginRegistry
    from agentlabx.core.session import SessionManager
    from agentlabx.plugins._builtin import register_builtin_plugins
    from agentlabx.providers.llm.base import BaseLLMProvider, LLMResponse

    registry = PluginRegistry()
    register_builtin_plugins(registry)

    class _StubProvider(BaseLLMProvider):
        name = "stub"
        is_mock = False

        async def query(self, *, model, prompt, **kwargs):
            return LLMResponse(
                content='{"next_stage":"literature_review","confidence":0.9,"reasoning":"ok"}',
                tokens_in=1,
                tokens_out=1,
                cost_usd=0.0,
                model=model,
            )

    provider = _StubProvider()
    session_manager = SessionManager()

    # Monkey-patch PipelineBuilder to capture the pi_advisor it received.
    captured = {}
    original_init = PipelineBuilder.__init__

    def spying_init(self, registry, preferences=None, pi_advisor=None):
        captured["advisor"] = pi_advisor
        original_init(self, registry, preferences=preferences, pi_advisor=pi_advisor)

    monkeypatch.setattr(PipelineBuilder, "__init__", spying_init)

    executor = PipelineExecutor(
        registry=registry,
        session_manager=session_manager,
        llm_provider=provider,
        storage=None,
        checkpoint_db_path=str(tmp_path / "ckpt.db"),
        event_forwarder=None,
    )
    await executor.initialize()

    session = session_manager.create_session(user_id="u1", research_topic="t")

    # Invoke start_session — this builds the graph (and therefore
    # invokes the spying PipelineBuilder.__init__).
    import asyncio
    try:
        running = await executor.start_session(session)
        # Cancel immediately so we don't wait for the full pipeline run
        await executor.cancel_session(session.session_id)
    except asyncio.CancelledError:
        pass  # expected — we only needed the build step

    assert "advisor" in captured, "PipelineBuilder was never constructed"
    assert isinstance(captured["advisor"], PIAgent), (
        f"Expected PIAgent advisor for non-mock LLM, got {type(captured['advisor'])!r}"
    )


@pytest.mark.asyncio
async def test_executor_does_not_construct_advisor_for_mock_llm(tmp_path, monkeypatch):
    """Under mock LLM (is_mock=True), pi_advisor remains None."""
    from agentlabx.server.executor import PipelineExecutor
    from agentlabx.core.registry import PluginRegistry
    from agentlabx.core.session import SessionManager
    from agentlabx.plugins._builtin import register_builtin_plugins
    from agentlabx.providers.llm.mock_provider import MockLLMProvider

    registry = PluginRegistry()
    register_builtin_plugins(registry)

    provider = MockLLMProvider()
    session_manager = SessionManager()

    captured = {}
    original_init = PipelineBuilder.__init__

    def spying_init(self, registry, preferences=None, pi_advisor=None):
        captured["advisor"] = pi_advisor
        original_init(self, registry, preferences=preferences, pi_advisor=pi_advisor)

    monkeypatch.setattr(PipelineBuilder, "__init__", spying_init)

    executor = PipelineExecutor(
        registry=registry,
        session_manager=session_manager,
        llm_provider=provider,
        storage=None,
        checkpoint_db_path=str(tmp_path / "ckpt.db"),
        event_forwarder=None,
    )
    await executor.initialize()

    session = session_manager.create_session(user_id="u1", research_topic="t")

    import asyncio
    try:
        running = await executor.start_session(session)
        await executor.cancel_session(session.session_id)
    except asyncio.CancelledError:
        pass  # expected — we only needed the build step

    assert captured.get("advisor") is None, (
        f"Expected no advisor for mock LLM, got {captured.get('advisor')!r}"
    )
