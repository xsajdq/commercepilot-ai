import asyncio
import uuid
from datetime import UTC, datetime

from cp_ai.agents import audit_products, build_catalog_fix_proposals
from cp_domain.ai_job import AIJob, AIJobStatus
from cp_domain.offer import Offer
from cp_domain.product import Product
from cp_domain.recommendation import Recommendation, RecommendationStatus, RecommendationType
from cp_domain.variant import Variant
from cp_policies import propose_recommendation, submit_for_approval
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from worker.celery_app import app
from worker.db import session_scope


@app.task(name="worker.run_catalog_audit")
def run_catalog_audit(tenant_id: str) -> dict:
    """Celery entrypoint for Phase 12's catalog agent: scans every one of
    a tenant's products for structural problems (missing price/stock/
    description/EAN, out-of-stock, priced below cost, an active product
    with no offers anywhere) and records the run as an `AIJob` - the
    first task in this codebase to actually use that table (scaffolded
    since Phase 2).

    Not every problem becomes a `Recommendation` (see the agent's own
    docstring for why) - only the ones with a safe, unambiguous fix do,
    proposed exactly like any other agent (never mutates directly, never
    double-proposes on a repeated run). No daily schedule wires this up
    yet - that's Phase 15's job.
    """
    return asyncio.run(_run_catalog_audit(uuid.UUID(tenant_id)))


async def _run_catalog_audit(tenant_id: uuid.UUID) -> dict:
    async with session_scope() as db:
        job = AIJob(
            tenant_id=tenant_id,
            agent_type="catalog",
            status=AIJobStatus.RUNNING,
            started_at=datetime.now(UTC),
        )
        db.add(job)
        await db.commit()

        try:
            products = list(
                await db.scalars(
                    select(Product)
                    .where(Product.tenant_id == tenant_id)
                    .options(
                        selectinload(Product.variants)
                        .selectinload(Variant.offers)
                        .selectinload(Offer.price),
                        selectinload(Product.variants)
                        .selectinload(Variant.offers)
                        .selectinload(Offer.stock),
                    )
                )
            )

            report = audit_products(products)
            proposals = build_catalog_fix_proposals(report)

            proposed_count = 0
            for proposal in proposals:
                # Idempotency (CLAUDE.md #11): never stack duplicate
                # pending catalog-fix proposals for the same entity on a
                # repeated run.
                existing = await db.scalar(
                    select(Recommendation).where(
                        Recommendation.tenant_id == tenant_id,
                        Recommendation.entity_type == proposal.entity_type,
                        Recommendation.entity_id == proposal.entity_id,
                        Recommendation.type == RecommendationType.CATALOG_FIX,
                        Recommendation.status.in_(
                            [RecommendationStatus.PROPOSED, RecommendationStatus.PENDING_APPROVAL]
                        ),
                    )
                )
                if existing is not None:
                    continue

                recommendation = await propose_recommendation(
                    db,
                    tenant_id=tenant_id,
                    type=proposal.type,
                    risk_level=proposal.risk_level,
                    entity_type=proposal.entity_type,
                    entity_id=proposal.entity_id,
                    title=proposal.title,
                    tool_name=proposal.tool_name,
                    tool_arguments=proposal.tool_arguments,
                    reason=proposal.reason,
                )
                await submit_for_approval(db, recommendation)
                proposed_count += 1
        except Exception as exc:  # noqa: BLE001 - always record the failure on the job itself
            job.status = AIJobStatus.FAILED
            job.error_message = str(exc)
            job.finished_at = datetime.now(UTC)
            await db.commit()
            raise

        job.status = AIJobStatus.SUCCEEDED
        job.finished_at = datetime.now(UTC)
        job.output_payload = {
            "products_scanned": report.products_scanned,
            "recommendations_proposed": proposed_count,
            "issues": [
                {
                    "type": issue.type.value,
                    "severity": issue.severity.value,
                    "entity_type": issue.entity_type,
                    "entity_id": str(issue.entity_id),
                    "sku": issue.sku,
                    "message": issue.message,
                }
                for issue in report.issues
            ],
        }
        await db.commit()

        return {
            "job_id": str(job.id),
            "products_scanned": report.products_scanned,
            "issues_found": len(report.issues),
            "recommendations_proposed": proposed_count,
        }
