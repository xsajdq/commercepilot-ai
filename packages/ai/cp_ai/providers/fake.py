from dataclasses import dataclass
from typing import Any

from cp_ai.providers.base import AIProvider


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

    Deliberately lets a test hand it an adversarial/hallucinated
    `response` (e.g. specification values an agent has no source data
    for) to prove that CLAUDE.md #9's "never guess" guarantee is
    enforced by the *agent's own code* after the call, not merely hoped
    for from a well-behaved model.
    """

    def __init__(self, response: dict) -> None:
        self.response = response
        self.calls: list[RecordedCall] = []

    async def generate_structured(
        self, *, system_prompt: str, user_prompt: str, schema: dict, schema_name: str = "output"
    ) -> dict[str, Any]:
        self.calls.append(
            RecordedCall(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                schema=schema,
                schema_name=schema_name,
            )
        )
        return self.response
