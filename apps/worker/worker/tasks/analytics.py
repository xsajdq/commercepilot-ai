import asyncio
import uuid
from collections import Counter
from datetime import UTC, datetime

from cp_ai.agents import build_dashboard_narrative
from cp_ai.providers import AIProvider, AnthropicProvider
from cp_analytics import OfferMetricsInput, ProductMetricsInput, compute_dashboard_metrics
from cp_domain.ai_job import AIJob, AIJobStatus
from cp_domain.offer import Offer
from cp_domain.product import Product
from cp_domain.recommendation import Recommendation
from cp_domain.variant import Variant
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from worker.ai_config import get_anthropic_api_key, get_anthropic_model
from worker.celery_app import app
from worker.db import session_scope


def _get_provider() -> AIProvider:
    """Same seam as `worker.tasks.product_content` - tests monkeypatch
    this to inject a `FakeAIProvider` instead of hitting the real
    Anthropic API."""
    return AnthropicProvider(api_key=get_anthropic_api_key(), model=get_anthropic_model())


async def _load_metrics(db, tenant_id: uuid.UUID):
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

    return compute_dashboard_metrics(
        products=product_inputs,
        recommendation_counts_by_status=dict(counts_by_status),
        recommendation_counts_by_type=dict(counts_by_type),
        latest_catalog_issue_count=latest_issue_count,
    )


def _metrics_to_payload(metrics) -> dict:
    return {
        "total_products": metrics.total_products,
        "products_by_status": metrics.products_by_status,
        "total_offers": metrics.total_offers,
        "offers_missing_price": metrics.offers_missing_price,
        "out_of_stock_offers": metrics.out_of_stock_offers,
        "total_catalog_value": str(metrics.total_catalog_value),
        "average_margin_rate": (
            str(metrics.average_margin_rate) if metrics.average_margin_rate is not None else None
        ),
        "recommendations_by_status": metrics.recommendations_by_status,
        "recommendations_by_type": metrics.recommendations_by_type,
        "latest_catalog_issue_count": metrics.latest_catalog_issue_count,
    }


@app.task(name="worker.generate_dashboard_narrative")
def generate_dashboard_narrative(tenant_id: str) -> dict:
    """Celery entrypoint for Phase 13's analytics agent - the "AI
    narrative" half. Computes the same deterministic `DashboardMetrics`
    apps/api's `GET /analytics/dashboard` computes live, then narrates
    them via `AIProvider`. Read-only throughout: never proposes a
    `Recommendation`, never mutates anything - this exists purely to
    generate insight text, recorded as an `AIJob` (the second real use
    of that table, after Phase 12's catalog agent) so past narratives
    stay browsable.
    """
    return asyncio.run(_generate_dashboard_narrative(uuid.UUID(tenant_id)))


async def _generate_dashboard_narrative(tenant_id: uuid.UUID) -> dict:
    async with session_scope() as db:
        job = AIJob(
            tenant_id=tenant_id,
            agent_type="analytics",
            status=AIJobStatus.RUNNING,
            started_at=datetime.now(UTC),
        )
        db.add(job)
        await db.commit()

        try:
            metrics = await _load_metrics(db, tenant_id)
            narrative = await build_dashboard_narrative(provider=_get_provider(), metrics=metrics)
        except Exception as exc:  # noqa: BLE001 - always record the failure on the job itself
            job.status = AIJobStatus.FAILED
            job.error_message = str(exc)
            job.finished_at = datetime.now(UTC)
            await db.commit()
            raise

        job.status = AIJobStatus.SUCCEEDED
        job.finished_at = datetime.now(UTC)
        job.output_payload = {
            "metrics": _metrics_to_payload(metrics),
            "narrative": narrative.model_dump(),
        }
        await db.commit()

        return {"job_id": str(job.id), "summary": narrative.summary}
