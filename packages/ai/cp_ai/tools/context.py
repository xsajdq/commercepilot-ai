import uuid
from dataclasses import dataclass

from cp_domain.audit_event import ActorType


@dataclass(frozen=True)
class ToolContext:
    """Where a tool call's `tenant_id` and actor identity come from.

    Always constructed by the caller (an agent runtime, later phases)
    from the authenticated session or AI job - never from a tool
    argument, and never from anything the model itself supplies. This is
    CONTRIBUTING.md #7 ("never trust tenant_id from client input") applied to
    tool calls: an AI provider echoing attacker-influenced external
    content (#18) must not be able to smuggle a different tenant_id
    through a tool's arguments, because the arguments schema is never
    even given the chance to declare that field - see
    `ToolRegistry.register`.
    """

    tenant_id: uuid.UUID
    actor_type: ActorType
    actor_id: uuid.UUID | None = None
    ai_model: str | None = None
