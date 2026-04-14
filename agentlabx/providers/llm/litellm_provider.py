"""Production LLM provider using LiteLLM for multi-provider support."""

from __future__ import annotations

import asyncio

from litellm import AuthenticationError, RateLimitError, Timeout, acompletion, completion_cost

from agentlabx.providers.llm.base import BaseLLMProvider, LLMResponse


class LiteLLMProvider(BaseLLMProvider):
    """LLM provider backed by LiteLLM.

    Supports all LiteLLM-compatible providers via "provider/model" format:
    - "openai/gpt-4o"
    - "anthropic/claude-sonnet-4-6"
    - "gemini/gemini-2.0-pro"
    - "deepseek/deepseek-chat"
    - "ollama/llama2"

    API keys read from environment (OPENAI_API_KEY, ANTHROPIC_API_KEY, etc.).
    """

    name = "litellm"
    description = (
        "Multi-provider LLM gateway via LiteLLM. "
        "Routes to OpenAI, Anthropic, Gemini, DeepSeek, Ollama and more "
        "using provider/model identifiers. Reads API keys from environment."
    )

    def __init__(
        self,
        *,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        timeout: float = 120.0,
    ) -> None:
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.timeout = timeout

    async def query(
        self,
        *,
        model: str | None,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.0,
    ) -> LLMResponse:
        if model is None:
            raise ValueError(
                "model must be a non-None string for LiteLLMProvider. "
                "Set AGENTLABX_LLM__DEFAULT_MODEL env var (e.g. 'gemini/gemini-2.5-flash') "
                "or pass config_overrides={'llm': {'default_model': '...'}} when creating the session."
            )
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        last_error: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                response = await acompletion(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    timeout=self.timeout,
                )

                content = response.choices[0].message.content or ""
                tokens_in = response.usage.prompt_tokens
                tokens_out = response.usage.completion_tokens

                try:
                    cost = completion_cost(completion_response=response)
                except Exception:
                    cost = 0.0

                return LLMResponse(
                    content=content,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    model=getattr(response, "model", model),
                    cost=float(cost or 0.0),
                )

            except (RateLimitError, Timeout) as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay * (2**attempt))
                    continue
                raise
            except AuthenticationError:
                raise

        if last_error:
            raise last_error
        msg = f"LLM query failed after {self.max_retries} retries"
        raise RuntimeError(msg)
