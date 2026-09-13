import asyncio
import uuid

from cp_ai.agents import build_product_content_proposal
from cp_ai.providers import AIProvider, AnthropicProvider
from cp_domain.product import Product
from cp_domain.recommendation import Recommendation, RecommendationStatus, RecommendationType
from cp_policies import propose_recommendation, submit_for_approval
from sqlalchemy import select

from worker.ai_config import get_anthropic_api_key, get_anthropic_model
from worker.celery_app import app
from worker.db import session_scope


def _get_provider() -> AIProvider:
    """A seam, not a hardcoded call: tests monkeypatch this to inject a
    `FakeAIProvider` instead of hitting the real Anthropic API. Business
    logic below only ever depends on the `AIProvider` interface
    (CLAUDE.md #17), never on `AnthropicProvider` directly."""
    return AnthropicProvider(api_key=get_anthropic_api_key(), model=get_anthropic_model())


@app.task(name="worker.generate_product_content_recommendation")
def generate_product_content_recommendation(tenant_id: str, product_id: str) -> dict:
    """Celery entrypoint for Phase 10's product agent: generates listing
    content (title, description, bullet points, specifications) for one
    product and submits it into the Phase 8 approval queue.

    Never mutates a product itself - like the pricing agent, it only
    ever proposes a Recommendation for a human to approve (CLAUDE.md:
    medium/high-risk actions require human approval).
    """
    return asyncio.run(
        _generate_product_content_recommendation(uuid.UUID(tenant_id), uuid.UUID(product_id))
    )


async def _generate_product_content_recommendation(
    tenant_id: uuid.UUID, product_id: uuid.UUID
) -> dict:
    async with session_scope() as db:
        product = await db.scalar(
            select(Product).where(Product.id == product_id, Product.tenant_id == tenant_id)
        )
        if product is None:
            return {"proposed": False, "reason": "product not found"}

        # Idempotency (CLAUDE.md #11): never stack duplicate pending
        # content proposals for the same product on a repeated run.
        existing = await db.scalar(
            select(Recommendation).where(
                Recommendation.tenant_id == tenant_id,
                Recommendation.entity_type == "product",
                Recommendation.entity_id == product.id,
                Recommendation.type == RecommendationType.CONTENT_UPDATE,
                Recommendation.status.in_(
                    [RecommendationStatus.PROPOSED, RecommendationStatus.PENDING_APPROVAL]
                ),
            )
        )
        if existing is not None:
            return {"proposed": False, "reason": "a content recommendation is already pending"}

        proposal = await build_product_content_proposal(provider=_get_provider(), product=product)

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

        return {"proposed": True, "recommendation_id": str(recommendation.id)}
