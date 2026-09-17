import asyncio
import uuid
from datetime import UTC, datetime

from cp_ai.agents import build_product_content_proposal
from cp_ai.providers import AIProvider, AnthropicProvider
from cp_domain.ai_job import AIJob, AIJobStatus
from cp_domain.product import Product
from cp_domain.recommendation import Recommendation, RecommendationStatus, RecommendationType
from cp_policies import propose_recommendation, submit_for_approval
from sqlalchemy import select

from worker.ai_config import get_anthropic_api_key, get_anthropic_model
from worker.celery_app import app
from worker.cost_guard import check_tenant_ai_budget, record_usage_on_job
from worker.db import session_scope


def _get_provider() -> AIProvider:
    """A seam, not a hardcoded call: tests monkeypatch this to inject a
    `FakeAIProvider` instead of hitting the real Anthropic API. Business
    logic below only ever depends on the `AIProvider` interface
    (CONTRIBUTING.md #17), never on `AnthropicProvider` directly."""
    return AnthropicProvider(api_key=get_anthropic_api_key(), model=get_anthropic_model())


@app.task(name="worker.generate_product_content_recommendation")
def generate_product_content_recommendation(tenant_id: str, product_id: str) -> dict:
    """Celery entrypoint for Phase 10's product agent: generates listing
    content (title, description, bullet points, specifications) for one
    product and submits it into the Phase 8 approval queue.

    Never mutates a product itself - like the pricing agent, it only
    ever proposes a Recommendation for a human to approve (CONTRIBUTING.md:
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

        # Idempotency (CONTRIBUTING.md #11): never stack duplicate pending
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

        # Phase 20: this task makes a real (billed) provider call but
        # didn't record it anywhere until now - it gets the same AIJob +
        # cost-guard treatment as the catalog/analytics agents, so the
        # guard actually sees every tenant's real AI spend, not just two
        # of its three sources.
        job = AIJob(
            tenant_id=tenant_id,
            agent_type="product_content",
            status=AIJobStatus.RUNNING,
            started_at=datetime.now(UTC),
        )
        db.add(job)
        await db.commit()

        budget = await check_tenant_ai_budget(db, tenant_id)
        if budget.is_exceeded:
            job.status = AIJobStatus.FAILED
            job.error_message = (
                f"AI budget exceeded for the {budget.plan} plan this period "
                f"(spent {budget.spent} of {budget.budget})"
            )
            job.finished_at = datetime.now(UTC)
            await db.commit()
            return {"proposed": False, "reason": job.error_message, "job_id": str(job.id)}

        try:
            proposal, usage = await build_product_content_proposal(
                provider=_get_provider(), product=product
            )
        except Exception as exc:  # noqa: BLE001 - always record the failure on the job itself
            job.status = AIJobStatus.FAILED
            job.error_message = str(exc)
            job.finished_at = datetime.now(UTC)
            await db.commit()
            raise

        job.status = AIJobStatus.SUCCEEDED
        job.finished_at = datetime.now(UTC)
        job.output_payload = {"title": proposal.title, "reason": proposal.reason}
        record_usage_on_job(job, usage=usage, model=get_anthropic_model())
        await db.commit()

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

        return {
            "proposed": True,
            "recommendation_id": str(recommendation.id),
            "job_id": str(job.id),
        }
