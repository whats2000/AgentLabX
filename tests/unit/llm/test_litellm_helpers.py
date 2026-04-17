from __future__ import annotations

import os

from agentlabx.llm.litellm_provider import _build_messages, _scoped_env
from agentlabx.llm.protocol import LLMRequest, Message, MessageRole


def test_scoped_env_sets_and_restores() -> None:
    os.environ["TEST_SCOPED_KEY"] = "original"
    with _scoped_env("new-value", "TEST_SCOPED_KEY"):
        assert os.environ["TEST_SCOPED_KEY"] == "new-value"
    assert os.environ["TEST_SCOPED_KEY"] == "original"
    del os.environ["TEST_SCOPED_KEY"]


def test_scoped_env_pops_when_no_previous() -> None:
    os.environ.pop("TEST_SCOPED_NEW", None)
    with _scoped_env("temp-value", "TEST_SCOPED_NEW"):
        assert os.environ["TEST_SCOPED_NEW"] == "temp-value"
    assert "TEST_SCOPED_NEW" not in os.environ


def test_scoped_env_noop_when_none() -> None:
    with _scoped_env(None, "ANY_VAR"):
        pass
    with _scoped_env("key", None):
        pass
    with _scoped_env("key", ""):
        pass


def test_build_messages_with_system_prompt() -> None:
    req = LLMRequest(
        model="m",
        messages=[{"role": MessageRole.USER, "content": "hi"}],
        system_prompt="Be helpful.",
    )
    msgs = _build_messages(req)
    assert msgs[0] == {"role": "system", "content": "Be helpful."}
    assert msgs[1] == {"role": "user", "content": "hi"}


def test_build_messages_with_message_dataclass() -> None:
    req = LLMRequest(
        model="m",
        messages=[Message(role=MessageRole.USER, content="typed msg")],
    )
    msgs = _build_messages(req)
    assert msgs[0] == {"role": "user", "content": "typed msg"}
