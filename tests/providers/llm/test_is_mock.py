"""Test is_mock class attribute on LLM providers."""


def test_base_llm_provider_default_is_mock_false():
    from agentlabx.providers.llm.base import BaseLLMProvider

    assert BaseLLMProvider.is_mock is False


def test_mock_llm_provider_is_mock_true():
    from agentlabx.providers.llm.mock_provider import MockLLMProvider

    p = MockLLMProvider(responses=[])
    assert p.is_mock is True
