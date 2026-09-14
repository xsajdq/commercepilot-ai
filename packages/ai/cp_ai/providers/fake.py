from dataclasses import dataclass

from cp_ai.providers.base import AIProvider, GeneratedOutput, TokenUsage


@dataclass
class RecordedCall:
    system_prompt: str
    user_prompt: str
    schema: dict
    schema_name: str


class FakeAIProvider(AIProvider):
    """In-memory `AIProvider` for tests - the `MockConnector` of this
    package. Returns whatever `response` it's constructed with,
    regardless of the prompt, and records every call so a test can
    assert on what an agent actually asked for.

    `usage` defaults to `None` (honest "we don't know" - this fake makes
    no real API call, so it has no real token counts to report) but can
    be set to a specific `TokenUsage` when a test needs to exercise cost
    recording without a real Anthropic call.

    Deliberately lets a test hand it an adversarial/hallucinated
    `response` (e.g. specification values an agent has no source data
    for) to prove that CLAUDE.md #9's "never guess" guarantee is
    enforced by the *agent's own code* after the call, not merely hoped
    for from a well-behaved model.
    """

    def __init__(self, response: dict, *, usage: TokenUsage | None = None) -> None:
        self.response = response
        self.usage = usage
        self.calls: list[RecordedCall] = []

    async def generate_structured(
        self, *, system_prompt: str, user_prompt: str, schema: dict, schema_name: str = "output"
    ) -> GeneratedOutput:
        self.calls.append(
            RecordedCall(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                schema=schema,
                schema_name=schema_name,
            )
        )
        return GeneratedOutput(data=self.response, usage=self.usage)
