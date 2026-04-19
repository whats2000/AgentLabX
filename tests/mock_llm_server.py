"""Standalone OpenAI-compatible mock LLM server for integration tests.

Runs as a real HTTP server. LiteLLM connects to it via
  model="openai/<model_name>", api_base="http://localhost:<port>/v1"

Responses are deterministic: the reply content is always a fixed string
(configurable), token counts are based on simple character-length heuristics,
and cost is always 0.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field

from fastapi import FastAPI
from pydantic import BaseModel

# --- Request / response shapes matching OpenAI's chat completions API ---


class ChatMessage(BaseModel):  # type: ignore[explicit-any]
    role: str
    content: str


class ChatCompletionRequest(BaseModel):  # type: ignore[explicit-any]
    model: str
    messages: list[ChatMessage]
    temperature: float | None = None
    max_tokens: int | None = None


class UsageInfo(BaseModel):  # type: ignore[explicit-any]
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ChoiceMessage(BaseModel):  # type: ignore[explicit-any]
    role: str
    content: str


class Choice(BaseModel):  # type: ignore[explicit-any]
    index: int
    message: ChoiceMessage
    finish_reason: str


class ChatCompletionResponse(BaseModel):  # type: ignore[explicit-any]
    id: str
    object: str
    created: int
    model: str
    choices: list[Choice]
    usage: UsageInfo


# --- Server state ---


@dataclass
class MockServerState:
    """Mutable state shared across requests. Configure before starting the server."""

    default_content: str = "This is a mock response."
    response_map: dict[str, str] = field(default_factory=dict)
    history: list[ChatCompletionRequest] = field(default_factory=list)
    fail_next_n: int = 0  # return 429 for the next N requests, then succeed


def create_mock_app(state: MockServerState | None = None) -> FastAPI:
    """Create a FastAPI app implementing OpenAI's /v1/chat/completions."""
    app = FastAPI(title="Mock LLM Server")
    server_state = state or MockServerState()
    app.state.mock = server_state

    @app.post("/v1/chat/completions", response_model=ChatCompletionResponse)
    async def chat_completions(
        req: ChatCompletionRequest,
    ) -> ChatCompletionResponse:
        server_state.history.append(req)

        # Simulate transient failures (429 rate-limit) for retry testing
        if server_state.fail_next_n > 0:
            server_state.fail_next_n -= 1
            from fastapi.responses import JSONResponse

            return JSONResponse(  # type: ignore[return-value]
                status_code=429,
                content={"error": {"message": "Rate limit exceeded", "type": "rate_limit"}},
            )

        # Determine response content
        content = server_state.default_content
        for msg in reversed(req.messages):
            if msg.role == "user" and msg.content in server_state.response_map:
                content = server_state.response_map[msg.content]
                break

        # Simple token count heuristic: ~4 chars per token
        prompt_text = " ".join(m.content for m in req.messages)
        prompt_tokens = max(1, len(prompt_text) // 4)
        completion_tokens = max(1, len(content) // 4)

        return ChatCompletionResponse(
            id=f"chatcmpl-mock-{uuid.uuid4().hex[:8]}",
            object="chat.completion",
            created=int(time.time()),
            model=req.model,
            choices=[
                Choice(
                    index=0,
                    message=ChoiceMessage(role="assistant", content=content),
                    finish_reason="stop",
                )
            ],
            usage=UsageInfo(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
            ),
        )

    @app.get("/v1/models")
    async def list_models() -> dict[str, list[dict[str, str]]]:
        return {
            "data": [
                {"id": "mock-model", "object": "model", "owned_by": "mock"},
            ]
        }

    return app
