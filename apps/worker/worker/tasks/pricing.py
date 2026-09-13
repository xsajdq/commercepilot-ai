import asyncio
import uuid

from cp_ai.agents import build_pricing_proposal
from cp_domain.offer import Offer
from cp_domain.price import Price
from cp_domain.product import Product
from cp_domain.recommendation import Recommendation, RecommendationStatus, RecommendationType
from cp_domain.variant import Variant
from cp_policies import propose_recommendation, submit_for_approval
from sqlalchemy import select

from worker.celery_app import app
from worker.db import session_scope


@app.task(name="worker.generate_price_recommendation")
def generate_price_recommendation(tenant_id: str, offer_id: str) -> dict:
    """Celery entrypoint for Phase 9's pricing agent: runs the
    deterministic pricing engine (cp_pricing, via cp_ai's pricing agent)
    against one offer and, if a price change is worth proposing, submits
    it into the Phase 8 approval queue.

    Never mutates a price itself - it only ever proposes a Recommendation
    for a human to approve, same as any other medium/high-risk tool call
    (CLAUDE.md: medium/high-risk actions require human approval; AI may
    recommend, math is code).
    """
    return asyncio.run(_generate_price_recommendation(uuid.UUID(tenant_id), uuid.UUID(offer_id)))


async def _generate_price_recommendation(tenant_id: uuid.UUID, offer_id: uuid.UUID) -> dict:
    async with session_scope() as db:
        offer = await db.scalar(
            select(Offer).where(Offer.id == offer_id, Offer.tenant_id == tenant_id)
        )
        if offer is None:
            return {"proposed": False, "reason": "offer not found"}

        price = await db.scalar(select(Price).where(Price.offer_id == offer.id))
        if price is None:
            return {"proposed": False, "reason": "offer has no price set"}

        variant = await db.get(Variant, offer.variant_id)
        product = await db.get(Product, variant.product_id)

        # Idempotency (CLAUDE.md #11): a job that runs repeatedly (a
        # schedule, a re-trigger) must never spam the approval queue
        # with duplicate proposals for the same offer.
        existing = await db.scalar(
            select(Recommendation).where(
                Recommendation.tenant_id == tenant_id,
                Recommendation.entity_type == "offer",
                Recommendation.entity_id == offer.id,
                Recommendation.type == RecommendationType.PRICE_CHANGE,
                Recommendation.status.in_(
                    [RecommendationStatus.PROPOSED, RecommendationStatus.PENDING_APPROVAL]
                ),
            )
        )
        if existing is not None:
            return {"proposed": False, "reason": "a price recommendation is already pending"}

        proposal = build_pricing_proposal(product=product, price=price, offer_id=offer.id)
        if proposal is None:
            return {"proposed": False, "reason": "no price change to propose"}

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
            confidence=proposal.confidence,
        )
        await submit_for_approval(db, recommendation)

        return {"proposed": True, "recommendation_id": str(recommendation.id)}
