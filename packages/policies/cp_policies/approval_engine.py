import uuid
from datetime import UTC, datetime
from decimal import Decimal

from cp_ai.tools import ToolContext, ToolRegistry, ToolResult
from cp_domain.approval import Approval, ApprovalStatus
from cp_domain.audit_event import ActorType, AuditEvent, AuditResult
from cp_domain.recommendation import (
    Recommendation,
    RecommendationStatus,
    RecommendationType,
    RiskLevel,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class RecommendationNotFoundError(Exception):
    pass


class RecommendationNotPendingError(Exception):
    """A decision (approve/reject) is made exactly once: raised when the
    recommendation's Approval isn't PENDING anymore, or when
    `submit_for_approval` is called on something other than a freshly
    PROPOSED recommendation."""


async def propose_recommendation(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    type: RecommendationType,
    risk_level: RiskLevel,
    entity_type: str,
    entity_id: uuid.UUID,
    title: str,
    tool_name: str,
    tool_arguments: dict,
    reason: str | None = None,
    confidence: Decimal | None = None,
) -> Recommendation:
    """Records an AI-proposed action, `PROPOSED` - not yet in front of a
    human. `tool_name`/`tool_arguments` are exactly what a blocked
    `cp_ai.ToolExecutor.execute()` call was made with, stored in
    `payload` so `approve()` can resolve and run that same tool call
    later: the AI gets one shot at what it's asking for, not a second
    one after a human has already read and approved the first.
    """
    recommendation = Recommendation(
        tenant_id=tenant_id,
        type=type,
        risk_level=risk_level,
        status=RecommendationStatus.PROPOSED,
        entity_type=entity_type,
        entity_id=entity_id,
        title=title,
        reason=reason,
        confidence=confidence,
        payload={"tool_name": tool_name, "tool_arguments": tool_arguments},
    )
    db.add(recommendation)
    await db.commit()
    return recommendation


async def submit_for_approval(db: AsyncSession, recommendation: Recommendation) -> Approval:
    """Moves a `PROPOSED` recommendation into the human queue.

    This is where a real Policy Engine would run further checks before a
    human ever sees it - Phase 8 keeps this a pass-through; the only gate
    that exists today is the risk-based one `cp_ai.ToolExecutor` already
    enforces before a recommendation is even proposed.
    """
    if recommendation.status is not RecommendationStatus.PROPOSED:
        raise RecommendationNotPendingError(
            f"Recommendation {recommendation.id} is {recommendation.status.value}, "
            "not proposed"
        )
    recommendation.status = RecommendationStatus.PENDING_APPROVAL
    approval = Approval(
        tenant_id=recommendation.tenant_id,
        recommendation_id=recommendation.id,
        status=ApprovalStatus.PENDING,
    )
    db.add(approval)
    await db.commit()
    return approval


async def _load_pending(
    db: AsyncSession, *, tenant_id: uuid.UUID, recommendation_id: uuid.UUID
) -> tuple[Recommendation, Approval]:
    recommendation = await db.scalar(
        select(Recommendation).where(
            Recommendation.id == recommendation_id, Recommendation.tenant_id == tenant_id
        )
    )
    if recommendation is None:
        raise RecommendationNotFoundError(f"No recommendation {recommendation_id}")

    approval = await db.scalar(
        select(Approval).where(
            Approval.recommendation_id == recommendation.id, Approval.tenant_id == tenant_id
        )
    )
    if approval is None or approval.status is not ApprovalStatus.PENDING:
        raise RecommendationNotPendingError(
            f"Recommendation {recommendation_id} has no pending approval"
        )
    return recommendation, approval


async def reject(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    recommendation_id: uuid.UUID,
    decided_by: uuid.UUID,
    decision_reason: str | None = None,
) -> Recommendation:
    """Rejecting never executes anything - no tool call, no mutation, no
    audit log (there is nothing to audit)."""
    recommendation, approval = await _load_pending(
        db, tenant_id=tenant_id, recommendation_id=recommendation_id
    )

    approval.status = ApprovalStatus.REJECTED
    approval.decided_by = decided_by
    approval.decided_at = datetime.now(UTC)
    approval.decision_reason = decision_reason
    recommendation.status = RecommendationStatus.REJECTED

    await db.commit()
    return recommendation


async def approve(
    db: AsyncSession,
    registry: ToolRegistry,
    *,
    tenant_id: uuid.UUID,
    recommendation_id: uuid.UUID,
    decided_by: uuid.UUID,
    decision_reason: str | None = None,
    actor_type: ActorType = ActorType.USER,
) -> Recommendation:
    """Approves a recommendation and immediately resumes execution of the
    tool call it was proposing - calling the tool's handler directly,
    not through `ToolExecutor.execute()` again (that would just re-hit
    the same risk gate and come back `requires_approval` forever now
    that a human has actually signed off).

    Once approved, the recommendation always ends at a terminal status:
    `SUCCESS` or `FAILED` - never left hanging in `EXECUTING` - whether
    the tool ran cleanly, returned its own failure, or the tool name/
    arguments stored on it turned out to be bad. A `mutates` tool's
    audit log (`AuditEvent.approval_id`) is written either way, exactly
    like `ToolExecutor` does for an auto-executed low-risk tool.
    """
    recommendation, approval = await _load_pending(
        db, tenant_id=tenant_id, recommendation_id=recommendation_id
    )

    approval.status = ApprovalStatus.APPROVED
    approval.decided_by = decided_by
    approval.decided_at = datetime.now(UTC)
    approval.decision_reason = decision_reason
    recommendation.status = RecommendationStatus.EXECUTING
    await db.commit()

    tool_name = recommendation.payload["tool_name"]
    tool_arguments = recommendation.payload["tool_arguments"]
    context = ToolContext(tenant_id=tenant_id, actor_type=actor_type, actor_id=decided_by)

    tool = None
    try:
        tool = registry.get(tool_name)
        args = tool.args_model.model_validate(tool_arguments)
        result = await tool.handler(args, context, db)
    except Exception as exc:  # noqa: BLE001 - any failure here ends in FAILED, never a crash
        result = ToolResult.fail(str(exc))

    recommendation.status = (
        RecommendationStatus.SUCCESS if result.success else RecommendationStatus.FAILED
    )

    if tool is None or tool.permission.mutates:
        db.add(
            AuditEvent(
                tenant_id=tenant_id,
                actor_type=actor_type,
                actor_id=decided_by,
                action=tool_name,
                entity_type=result.entity_type or recommendation.entity_type,
                entity_id=result.entity_id or recommendation.entity_id,
                before=result.before,
                after=result.after,
                approval_id=approval.id,
                result=AuditResult.SUCCESS if result.success else AuditResult.FAILURE,
                error_message=result.error,
            )
        )

    await db.commit()
    return recommendation
