import json

import httpx
import pytest

from cp_ai.providers import AIProviderError, AnthropicProvider, TokenUsage


def _response(*, content: list[dict], stop_reason: str = "tool_use") -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "id": "msg_1",
            "type": "message",
            "role": "assistant",
            "model": "claude-sonnet-5",
            "content": content,
            "stop_reason": stop_reason,
            "stop_sequence": None,
            "usage": {"input_tokens": 10, "output_tokens": 5},
        },
    )


def _provider(handler) -> AnthropicProvider:
    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return AnthropicProvider(api_key="test-key", model="claude-sonnet-5", http_client=http_client)


class TestAnthropicProvider:
    async def test_returns_the_tool_use_input_matching_the_schema_name(self) -> None:
        captured: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured.update(json.loads(request.content))
            return _response(
                content=[
                    {
                        "type": "tool_use",
                        "id": "toolu_1",
                        "name": "product_content",
                        "input": {"title": "Great Widget"},
                    }
                ]
            )

        provider = _provider(handler)

        result = await provider.generate_structured(
            system_prompt="You are a copywriter.",
            user_prompt="Write about SKU-1.",
            schema={"type": "object", "properties": {"title": {"type": "string"}}},
            schema_name="product_content",
        )

        assert result.data == {"title": "Great Widget"}
        assert result.usage == TokenUsage(input_tokens=10, output_tokens=5)
        assert captured["model"] == "claude-sonnet-5"
        assert captured["system"] == "You are a copywriter."
        assert captured["messages"] == [{"role": "user", "content": "Write about SKU-1."}]
        assert captured["tool_choice"] == {"type": "tool", "name": "product_content"}
        [tool] = captured["tools"]
        assert tool["name"] == "product_content"
        assert tool["input_schema"] == {
            "type": "object",
            "properties": {"title": {"type": "string"}},
        }

    async def test_raises_when_the_model_does_not_return_the_expected_tool_call(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return _response(
                content=[{"type": "text", "text": "I'd rather not."}], stop_reason="end_turn"
            )

        provider = _provider(handler)

        with pytest.raises(AIProviderError):
            await provider.generate_structured(
                system_prompt="sys",
                user_prompt="usr",
                schema={"type": "object"},
                schema_name="product_content",
            )

    async def test_raises_on_an_api_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, json={"error": {"type": "api_error", "message": "boom"}})

        provider = _provider(handler)

        with pytest.raises(AIProviderError):
            await provider.generate_structured(
                system_prompt="sys", user_prompt="usr", schema={"type": "object"}
            )
