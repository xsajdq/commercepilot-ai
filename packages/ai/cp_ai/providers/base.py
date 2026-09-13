from abc import ABC, abstractmethod


class AIProviderError(Exception):
    """The provider's underlying API call failed, or its response didn't
    contain the structured output it was asked for."""


class AIProvider(ABC):
    """Replaceable LLM backend (CLAUDE.md #17): business logic calls this
    interface, never a vendor SDK directly, so swapping Anthropic for
    OpenAI (or anything else) never touches an agent's own code."""

    @abstractmethod
    async def generate_structured(
        self, *, system_prompt: str, user_prompt: str, schema: dict, schema_name: str = "output"
    ) -> dict:
        """Returns a dict shaped like `schema` (a JSON schema, typically
        from `SomePydanticModel.model_json_schema()`). How the provider
        actually achieves structured/constrained output (tool-use,
        function calling, `response_format`, ...) is its own concern -
        callers only see the resulting dict.

        Raises `AIProviderError` if the underlying call fails or the
        provider can't produce structured output for this request.
        """
