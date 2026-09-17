from abc import ABC, abstractmethod
from dataclasses import dataclass


class AIProviderError(Exception):
    """The provider's underlying API call failed, or its response didn't
    contain the structured output it was asked for."""


@dataclass(frozen=True)
class TokenUsage:
    """Real token counts as reported by the provider's own API response -
    never estimated or invented (CONTRIBUTING.md #9). `None` from a provider
    that genuinely can't report usage (e.g. `FakeAIProvider` unless
    configured otherwise) is left as `None` here too, not defaulted to
    zero - zero would misleadingly read as "no cost" rather than
    "unknown", the same reasoning `cp_analytics.average_margin_rate`
    already applies to missing data."""

    input_tokens: int
    output_tokens: int


@dataclass(frozen=True)
class GeneratedOutput:
    """What `AIProvider.generate_structured` actually returns: the
    structured `data` dict every existing caller already expected, plus
    the real `usage` for that call so callers can record cost (Phase 20)
    without this interface knowing anything about billing itself."""

    data: dict
    usage: TokenUsage | None


class AIProvider(ABC):
    """Replaceable LLM backend (CONTRIBUTING.md #17): business logic calls this
    interface, never a vendor SDK directly, so swapping Anthropic for
    OpenAI (or anything else) never touches an agent's own code."""

    @abstractmethod
    async def generate_structured(
        self, *, system_prompt: str, user_prompt: str, schema: dict, schema_name: str = "output"
    ) -> GeneratedOutput:
        """`GeneratedOutput.data` is shaped like `schema` (a JSON schema,
        typically from `SomePydanticModel.model_json_schema()`). How the
        provider actually achieves structured/constrained output
        (tool-use, function calling, `response_format`, ...) is its own
        concern - callers only see the resulting dict and usage.

        Raises `AIProviderError` if the underlying call fails or the
        provider can't produce structured output for this request.
        """
