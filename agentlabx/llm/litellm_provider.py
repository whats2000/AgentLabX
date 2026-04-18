from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager

import litellm

from agentlabx.llm.protocol import LLMRequest, LLMResponse

_log = logging.getLogger(__name__)

_env_lock = asyncio.Lock()


def _build_messages(
    request: LLMRequest,
) -> list[dict[str, str]]:
    """Convert LLMRequest messages to the list-of-dicts format LiteLLM expects."""
    msgs: list[dict[str, str]] = []
    if request.system_prompt is not None:
        msgs.append({"role": "system", "content": request.system_prompt})
    for m in request.messages:
        if isinstance(m, dict):
            msgs.append({"role": m["role"], "content": m["content"]})
        else:
            msgs.append({"role": m.role, "content": m.content})
    return msgs


@contextmanager
def _scoped_env(api_key: str | None, env_var: str | None) -> Iterator[None]:
    """Temporarily set an environment variable for the duration of the call."""
    if api_key is None or env_var is None or env_var == "":
        yield
        return

    previous = os.environ.get(env_var)
    os.environ[env_var] = api_key
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(env_var, None)
        else:
            os.environ[env_var] = previous


class LiteLLMProvider:
    """Routes LLM calls through LiteLLM's acompletion."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        api_base: str | None = None,
        env_var: str | None = None,
        retry_count: int = 2,
        timeout_seconds: float = 120.0,
    ) -> None:
        self._api_key = api_key
        self._api_base = api_base
        self._env_var = env_var
        self._retry_count = retry_count
        self._timeout = timeout_seconds

    async def complete(self, request: LLMRequest) -> LLMResponse:
        messages = _build_messages(request)

        kwargs: dict[str, str | int | float | list[dict[str, str]] | None] = {
            "model": request.model,
            "messages": messages,
            "num_retries": self._retry_count,
            "timeout": self._timeout,
        }
        if request.temperature is not None:
            kwargs["temperature"] = request.temperature
        if request.max_tokens is not None:
            kwargs["max_tokens"] = request.max_tokens
        if self._api_key is not None:
            kwargs["api_key"] = self._api_key
        if self._api_base is not None:
            kwargs["api_base"] = self._api_base

        needs_env = self._env_var is not None and self._env_var != ""
        if needs_env:
            async with _env_lock:
                with _scoped_env(self._api_key, self._env_var):
                    response = await litellm.acompletion(**kwargs)
        else:
            response = await litellm.acompletion(**kwargs)

        usage = response.usage
        prompt_tokens: int = getattr(usage, "prompt_tokens", 0) or 0
        completion_tokens: int = getattr(usage, "completion_tokens", 0) or 0
        total_tokens: int = getattr(usage, "total_tokens", 0) or 0

        content: str = response.choices[0].message.content or ""

        cost_usd: float = 0.0
        try:
            cost_usd = float(litellm.completion_cost(completion_response=response))
        except Exception:
            # litellm raises bare Exception for unknown models (not ValueError/NotFoundError)
            _log.debug("cost calculation unavailable for model %s", request.model)

        model_returned: str = getattr(response, "model", request.model) or request.model

        return LLMResponse(
            content=content,
            model=model_returned,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            cost_usd=cost_usd,
        )
