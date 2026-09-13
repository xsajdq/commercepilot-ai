from anthropic import APIError, AsyncAnthropic
from httpx import AsyncClient

from cp_ai.providers.base import AIProvider, AIProviderError


class AnthropicProvider(AIProvider):
    """The first concrete `AIProvider` (CLAUDE.md #17: replaceable, never
    hardcoded into business logic - an agent only ever depends on
    `AIProvider`, never on this class or the `anthropic` SDK directly).

    Structured output is Anthropic's tool-use mechanism: `schema` is
    handed to the model as a single tool's `input_schema` with
    `tool_choice` forcing exactly that tool, so the model's only possible
    response is a call to it - never free-form text to parse.
    """

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        max_tokens: int = 4096,
        http_client: AsyncClient | None = None,
    ) -> None:
        self._client = AsyncAnthropic(api_key=api_key, http_client=http_client)
        self._model = model
        self._max_tokens = max_tokens

    async def generate_structured(
        self, *, system_prompt: str, user_prompt: str, schema: dict, schema_name: str = "output"
    ) -> dict:
        try:
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
                tools=[
                    {
                        "name": schema_name,
                        "description": "Return the structured result for this request.",
                        "input_schema": schema,
                    }
                ],
                tool_choice={"type": "tool", "name": schema_name},
            )
        except APIError as exc:
            raise AIProviderError(f"Anthropic API call failed: {exc}") from exc

        for block in response.content:
            if block.type == "tool_use" and block.name == schema_name:
                return block.input

        raise AIProviderError(
            f"Anthropic response did not include the expected {schema_name!r} tool call "
            f"(stop_reason={response.stop_reason!r})"
        )
