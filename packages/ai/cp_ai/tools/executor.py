from dataclasses import dataclass
from typing import Any

from cp_domain.audit_event import AuditEvent, AuditResult
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from cp_ai.tools.context import ToolContext
from cp_ai.tools.registry import ToolNotFoundError, ToolRegistry
from cp_ai.tools.result import ToolResult


@dataclass
class ToolCall:
    """One request to run a tool: whatever an AIProvider's tool-use
    response gives back - a name and a raw arguments dict, not yet
    validated against anything."""

    name: str
    arguments: dict[str, Any]


class ToolExecutor:
    """The control flow from CONTRIBUTING.md, minus the Policy Engine and the
    real Approval workflow - both land in Phase 8:

        AI -> Tool -> Validation -> [Policy] -> Risk -> Approval
            -> Execution -> Audit Log

    Until Phase 8 exists, anything above LOW risk is refused outright
    rather than silently executed or silently approved:
    `tool.permission.requires_approval` short-circuits before `handler`
    ever runs, so no mutation happens outside that gate. A tool's own
    exceptions are caught and turned into a failed `ToolResult` - a
    single bad tool call must never crash the caller.
    """

    def __init__(self, registry: ToolRegistry, db: AsyncSession) -> None:
        self._registry = registry
        self._db = db

    async def execute(self, call: ToolCall, context: ToolContext) -> ToolResult:
        try:
            tool = self._registry.get(call.name)
        except ToolNotFoundError as exc:
            return ToolResult.fail(str(exc))

        try:
            args = tool.args_model.model_validate(call.arguments)
        except ValidationError as exc:
            return ToolResult.fail(f"Invalid arguments for {call.name!r}: {exc}")

        # Policy Engine (Phase 8) runs here, before the risk/approval gate.

        if tool.permission.requires_approval:
            return ToolResult.pending_approval(
                f"{call.name!r} is {tool.permission.risk_level.value}-risk and needs "
                "human approval (Phase 8) before it can execute."
            )

        try:
            result = await tool.handler(args, context, self._db)
        except Exception as exc:  # noqa: BLE001 - a tool crashing must not crash the caller
            result = ToolResult.fail(str(exc))

        if tool.permission.mutates:
            await self._audit(tool_name=call.name, context=context, result=result)

        return result

    async def _audit(self, *, tool_name: str, context: ToolContext, result: ToolResult) -> None:
        self._db.add(
            AuditEvent(
                tenant_id=context.tenant_id,
                actor_type=context.actor_type,
                actor_id=context.actor_id,
                action=tool_name,
                entity_type=result.entity_type or "unknown",
                entity_id=result.entity_id,
                before=result.before,
                after=result.after,
                ai_model=context.ai_model,
                result=AuditResult.SUCCESS if result.success else AuditResult.FAILURE,
                error_message=result.error,
            )
        )
        await self._db.commit()
