import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from cp_ai.tools import ToolRegistry
from cp_ai.tools.builtin import register_builtin_tools
from cp_domain.recommendation import (
    Recommendation,
    RecommendationStatus,
    RecommendationType,
    RiskLevel,
)
from cp_policies import (
    RecommendationNotFoundError,
    RecommendationNotPendingError,
)
from cp_policies import (
    approve as approve_recommendation,
)
from cp_policies import (
    reject as reject_recommendation,
)
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_membership, get_current_user
from app.db.base import get_db
from app.db.models.membership import Membership
from app.db.models.user import User

router = APIRouter(prefix="/recommendations", tags=["recommendations"])

# One registry per process is enough: tools are stateless schemas, not
# per-request objects (mirrors how a real agent runtime would hold onto
# one ToolRegistry for its whole lifetime).
_registry = ToolRegistry()
register_builtin_tools(_registry)


class RecommendationOut(BaseModel):
    id: uuid.UUID
    type: RecommendationType
    risk_level: RiskLevel
    status: RecommendationStatus
    entity_type: str
    entity_id: uuid.UUID
    title: str
    reason: str | None
    confidence: Decimal | None
    created_at: datetime

    model_config = {"from_attributes": True}


class DecisionRequest(BaseModel):
    decision_reason: str | None = None


@router.get("", response_model=list[RecommendationOut])
async def list_recommendations(
    db: Annotated[AsyncSession, Depends(get_db)],
    membership: Annotated[Membership, Depends(get_current_membership)],
    status_filter: Annotated[RecommendationStatus | None, Query(alias="status")] = None,
) -> list[Recommendation]:
    query = select(Recommendation).where(Recommendation.tenant_id == membership.tenant_id)
    if status_filter is not None:
        query = query.where(Recommendation.status == status_filter)
    query = query.order_by(Recommendation.created_at.desc()).limit(200)
    return list(await db.scalars(query))


@router.post("/{recommendation_id}/approve", response_model=RecommendationOut)
async def approve_endpoint(
    recommendation_id: uuid.UUID,
    payload: DecisionRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    membership: Annotated[Membership, Depends(get_current_membership)],
    user: Annotated[User, Depends(get_current_user)],
) -> Recommendation:
    try:
        return await approve_recommendation(
            db,
            _registry,
            tenant_id=membership.tenant_id,
            recommendation_id=recommendation_id,
            decided_by=user.id,
            decision_reason=payload.decision_reason,
        )
    except RecommendationNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Recommendation not found"
        ) from exc
    except RecommendationNotPendingError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post("/{recommendation_id}/reject", response_model=RecommendationOut)
async def reject_endpoint(
    recommendation_id: uuid.UUID,
    payload: DecisionRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    membership: Annotated[Membership, Depends(get_current_membership)],
    user: Annotated[User, Depends(get_current_user)],
) -> Recommendation:
    try:
        return await reject_recommendation(
            db,
            tenant_id=membership.tenant_id,
            recommendation_id=recommendation_id,
            decided_by=user.id,
            decision_reason=payload.decision_reason,
        )
    except RecommendationNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Recommendation not found"
        ) from exc
    except RecommendationNotPendingError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
