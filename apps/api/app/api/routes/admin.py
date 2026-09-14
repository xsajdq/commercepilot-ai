import uuid
from datetime import datetime
from typing import Annotated

from cp_domain.ai_job import AIJob
from cp_domain.connection import Connection, ConnectionPlatform, ConnectionStatus
from cp_domain.recommendation import (
    Recommendation,
    RecommendationStatus,
    RecommendationType,
    RiskLevel,
)
from cp_domain.subscription import PlanTier, Subscription, SubscriptionStatus
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_platform_admin
from app.db.base import get_db
from app.db.models.membership import Membership
from app.db.models.tenant import Tenant
from app.db.models.user import User

# Read-only cross-tenant visibility for support/ops during the beta - see
# `require_platform_admin`. No route here creates, updates, or deletes
# anything; every mutation a support engineer needs still goes through
# the normal per-tenant control flow, from that tenant's own session.
router = APIRouter(prefix="/admin", tags=["admin"])


class AdminTenantSummary(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    created_at: datetime
    plan: PlanTier
    subscription_status: SubscriptionStatus
    member_count: int
    connection_count: int
    connection_error_count: int
    latest_ai_job_status: str | None
    latest_ai_job_at: datetime | None


class AdminConnectionOut(BaseModel):
    id: uuid.UUID
    platform: ConnectionPlatform
    name: str
    status: ConnectionStatus
    last_synced_at: datetime | None
    last_error: str | None

    model_config = {"from_attributes": True}


class AdminAIJobOut(BaseModel):
    id: uuid.UUID
    agent_type: str
    status: str
    error_message: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AdminRecommendationOut(BaseModel):
    id: uuid.UUID
    type: RecommendationType
    risk_level: RiskLevel
    status: RecommendationStatus
    title: str
    created_at: datetime

    model_config = {"from_attributes": True}


class AdminMemberOut(BaseModel):
    user_id: uuid.UUID
    email: str
    full_name: str
    role: str


class AdminTenantDetail(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    created_at: datetime
    plan: PlanTier
    subscription_status: SubscriptionStatus
    members: list[AdminMemberOut]
    connections: list[AdminConnectionOut]
    recent_ai_jobs: list[AdminAIJobOut]
    recent_recommendations: list[AdminRecommendationOut]


@router.get("/tenants", response_model=list[AdminTenantSummary])
async def list_tenants(
    db: Annotated[AsyncSession, Depends(get_db)],
    _admin: Annotated[User, Depends(require_platform_admin)],
) -> list[AdminTenantSummary]:
    tenants = (await db.scalars(select(Tenant).order_by(Tenant.created_at.desc()))).all()

    summaries: list[AdminTenantSummary] = []
    for tenant in tenants:
        subscription = await db.scalar(
            select(Subscription).where(Subscription.tenant_id == tenant.id)
        )
        member_count = await db.scalar(
            select(func.count()).select_from(Membership).where(Membership.tenant_id == tenant.id)
        )
        connection_count = await db.scalar(
            select(func.count()).select_from(Connection).where(Connection.tenant_id == tenant.id)
        )
        connection_error_count = await db.scalar(
            select(func.count())
            .select_from(Connection)
            .where(Connection.tenant_id == tenant.id, Connection.status == ConnectionStatus.ERROR)
        )
        latest_job = await db.scalar(
            select(AIJob)
            .where(AIJob.tenant_id == tenant.id)
            .order_by(AIJob.created_at.desc())
            .limit(1)
        )

        summaries.append(
            AdminTenantSummary(
                id=tenant.id,
                name=tenant.name,
                slug=tenant.slug,
                created_at=tenant.created_at,
                plan=subscription.plan if subscription else PlanTier.FREE,
                subscription_status=(
                    subscription.status if subscription else SubscriptionStatus.ACTIVE
                ),
                member_count=member_count or 0,
                connection_count=connection_count or 0,
                connection_error_count=connection_error_count or 0,
                latest_ai_job_status=latest_job.status.value if latest_job else None,
                latest_ai_job_at=latest_job.created_at if latest_job else None,
            )
        )
    return summaries


@router.get("/tenants/{tenant_id}", response_model=AdminTenantDetail)
async def get_tenant_detail(
    tenant_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    _admin: Annotated[User, Depends(require_platform_admin)],
) -> AdminTenantDetail:
    tenant = await db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    subscription = await db.scalar(
        select(Subscription).where(Subscription.tenant_id == tenant_id)
    )

    memberships = (
        await db.scalars(
            select(Membership)
            .where(Membership.tenant_id == tenant_id)
            .join(User, User.id == Membership.user_id)
        )
    ).all()
    members = []
    for membership in memberships:
        user = await db.get(User, membership.user_id)
        if user is not None:
            members.append(
                AdminMemberOut(
                    user_id=user.id,
                    email=user.email,
                    full_name=user.full_name,
                    role=membership.role.value,
                )
            )

    connections = (
        await db.scalars(select(Connection).where(Connection.tenant_id == tenant_id))
    ).all()

    recent_jobs = (
        await db.scalars(
            select(AIJob)
            .where(AIJob.tenant_id == tenant_id)
            .order_by(AIJob.created_at.desc())
            .limit(10)
        )
    ).all()

    recent_recommendations = (
        await db.scalars(
            select(Recommendation)
            .where(Recommendation.tenant_id == tenant_id)
            .order_by(Recommendation.created_at.desc())
            .limit(10)
        )
    ).all()

    return AdminTenantDetail(
        id=tenant.id,
        name=tenant.name,
        slug=tenant.slug,
        created_at=tenant.created_at,
        plan=subscription.plan if subscription else PlanTier.FREE,
        subscription_status=subscription.status if subscription else SubscriptionStatus.ACTIVE,
        members=members,
        connections=[AdminConnectionOut.model_validate(c) for c in connections],
        recent_ai_jobs=[
            AdminAIJobOut(
                id=job.id,
                agent_type=job.agent_type,
                status=job.status.value,
                error_message=job.error_message,
                created_at=job.created_at,
            )
            for job in recent_jobs
        ],
        recent_recommendations=[
            AdminRecommendationOut.model_validate(r) for r in recent_recommendations
        ],
    )
