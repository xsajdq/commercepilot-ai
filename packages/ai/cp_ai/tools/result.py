import uuid
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolResult:
    """What a tool call produced. `entity_type`/`entity_id`/`before`/
    `after` are only meaningful when the tool mutates something - they
    feed directly into the `AuditEvent` the executor writes, so a
    mutating tool's handler should populate them via `ToolResult.ok`.
    """

    success: bool
    data: Any | None = None
    error: str | None = None
    requires_approval: bool = False
    entity_type: str | None = None
    entity_id: uuid.UUID | None = None
    before: dict | None = None
    after: dict | None = None

    @classmethod
    def ok(
        cls,
        data: Any = None,
        *,
        entity_type: str | None = None,
        entity_id: uuid.UUID | None = None,
        before: dict | None = None,
        after: dict | None = None,
    ) -> "ToolResult":
        return cls(
            success=True,
            data=data,
            entity_type=entity_type,
            entity_id=entity_id,
            before=before,
            after=after,
        )

    @classmethod
    def fail(cls, error: str) -> "ToolResult":
        return cls(success=False, error=error)

    @classmethod
    def pending_approval(cls, reason: str) -> "ToolResult":
        """Returned instead of running the handler at all, for anything
        above LOW risk - Phase 8 is what turns this into a real
        Recommendation/Approval row and resumes execution once a human
        approves it. Until then this is a hard stop: no handler call, no
        mutation, no audit log (nothing happened yet to audit)."""
        return cls(success=False, requires_approval=True, error=reason)
