import uuid
from collections import Counter
from datetime import datetime
from typing import Annotated

from cp_analytics import OfferMetricsInput, ProductMetricsInput, compute_dashboard_metrics
from cp_domain.ai_job import AIJob, AIJobStatus
from cp_domain.offer import Offer
from cp_domain.product import Product
from cp_domain.recommendation import Recommendation
from cp_domain.variant import Variant
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.dependencies import get_current_membership
from app.core.celery_client import get_celery_client
from app.db.base import get_db
from app.db.models.membership import Membership

router = APIRouter(prefix="/analytics", tags=["analytics"])


class TaskTriggeredResponse(BaseModel):
    task_id: str


class DashboardMetricsOut(BaseModel):
    total_products: int
    products_by_status: dict[str, int]
    total_offers: int
    offers_missing_price: int
    out_of_stock_offers: int
    total_catalog_value: str
    average_margin_rate: str | None
    recommendations_by_status: dict[str, int]
    recommendations_by_type: dict[str, int]
    latest_catalog_issue_count: int | None


class DashboardNarrativeOut(BaseModel):
    summary: str
    highlights: list[str]


class AnalyticsReportOut(BaseModel):
    id: uuid.UUID
    status: AIJobStatus
    metrics: DashboardMetricsOut | None = None
    narrative: DashboardNarrativeOut | None = None
    error_message: str | None = None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


async def _load_dashboard_metrics(db: AsyncSession, tenant_id: uuid.UUID) -> DashboardMetricsOut:
    """Live, synchronous computation - a handful of fast SELECTs plus
    pure aggregation (`cp_analytics`), not a slow external call, so this
    is fine to do inline in a request handler (CONTRIBUTING.md #13 is about
    long-running jobs; the AI narrative, which does make a slow LLM
    call, is the part that goes through Celery instead - see
    `trigger_narrative` below)."""
    products = list(
        await db.scalars(
            select(Product)
            .where(Product.tenant_id == tenant_id)
            .options(
                selectinload(Product.variants).selectinload(Variant.offers).selectinload(
                    Offer.price
                ),
                selectinload(Product.variants).selectinload(Variant.offers).selectinload(
                    Offer.stock
                ),
            )
        )
    )
    product_inputs = [
        ProductMetricsInput(
            status=product.status.value,
            offers=[
                OfferMetricsInput(
                    price_amount=offer.price.amount if offer.price else None,
                    cost=product.cost,
                    stock_quantity=offer.stock.quantity if offer.stock else None,
                )
                for variant in product.variants
                for offer in variant.offers
            ],
        )
        for product in products
    ]

    recommendations = list(
        await db.scalars(select(Recommendation).where(Recommendation.tenant_id == tenant_id))
    )
    counts_by_status = Counter(r.status.value for r in recommendations)
    counts_by_type = Counter(r.type.value for r in recommendations)

    latest_catalog_job = await db.scalar(
        select(AIJob)
        .where(AIJob.tenant_id == tenant_id, AIJob.agent_type == "catalog")
        .order_by(AIJob.created_at.desc())
        .limit(1)
    )
    latest_issue_count = (
        len(latest_catalog_job.output_payload["issues"])
        if latest_catalog_job and latest_catalog_job.output_payload
        else None
    )

    metrics = compute_dashboard_metrics(
        products=product_inputs,
        recommendation_counts_by_status=dict(counts_by_status),
        recommendation_counts_by_type=dict(counts_by_type),
        latest_catalog_issue_count=latest_issue_count,
    )

    return DashboardMetricsOut(
        total_products=metrics.total_products,
        products_by_status=metrics.products_by_status,
        total_offers=metrics.total_offers,
        offers_missing_price=metrics.offers_missing_price,
        out_of_stock_offers=metrics.out_of_stock_offers,
        total_catalog_value=str(metrics.total_catalog_value),
        average_margin_rate=(
            str(metrics.average_margin_rate) if metrics.average_margin_rate is not None else None
        ),
        recommendations_by_status=metrics.recommendations_by_status,
        recommendations_by_type=metrics.recommendations_by_type,
        latest_catalog_issue_count=metrics.latest_catalog_issue_count,
    )


@router.get("/dashboard", response_model=DashboardMetricsOut)
async def get_dashboard(
    db: Annotated[AsyncSession, Depends(get_db)],
    membership: Annotated[Membership, Depends(get_current_membership)],
) -> DashboardMetricsOut:
    return await _load_dashboard_metrics(db, membership.tenant_id)


@router.post("/narrative", response_model=TaskTriggeredResponse)
async def trigger_narrative(
    membership: Annotated[Membership, Depends(get_current_membership)],
) -> TaskTriggeredResponse:
    result = get_celery_client().send_task(
        "worker.generate_dashboard_narrative", args=[str(membership.tenant_id)]
    )
    return TaskTriggeredResponse(task_id=result.id)


def _to_report_out(job: AIJob) -> AnalyticsReportOut:
    payload = job.output_payload or {}
    metrics_payload = payload.get("metrics")
    narrative_payload = payload.get("narrative")
    return AnalyticsReportOut(
        id=job.id,
        status=job.status,
        metrics=DashboardMetricsOut(**metrics_payload) if metrics_payload else None,
        narrative=DashboardNarrativeOut(**narrative_payload) if narrative_payload else None,
        error_message=job.error_message,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
    )


@router.get("/narratives", response_model=list[AnalyticsReportOut])
async def list_narratives(
    db: Annotated[AsyncSession, Depends(get_db)],
    membership: Annotated[Membership, Depends(get_current_membership)],
) -> list[AnalyticsReportOut]:
    jobs = await db.scalars(
        select(AIJob)
        .where(AIJob.tenant_id == membership.tenant_id, AIJob.agent_type == "analytics")
        .order_by(AIJob.created_at.desc())
        .limit(50)
    )
    return [_to_report_out(job) for job in jobs]
