import asyncio
import uuid

from cp_ai.agents import build_listing_publish_proposal
from cp_connectors.exceptions import ConnectorError
from cp_domain.audit_event import ActorType, AuditEvent, AuditResult
from cp_domain.connection import Connection
from cp_domain.offer import Offer, OfferStatus
from cp_domain.price import Price
from cp_domain.product import Product
from cp_domain.recommendation import Recommendation, RecommendationStatus, RecommendationType
from cp_domain.variant import Variant
from cp_policies import propose_recommendation, submit_for_approval
from cp_shared.crypto import decrypt_credentials
from cp_sync.connector_factory import build_connector
from sqlalchemy import select

from worker.celery_app import app
from worker.db import get_encryption_keys, session_scope


@app.task(name="worker.generate_listing_publish_recommendation")
def generate_listing_publish_recommendation(tenant_id: str, offer_id: str) -> dict:
    """Celery entrypoint for Phase 11's listing agent: checks whether a
    draft marketplace listing is ready to go live and, if so, submits it
    into the Phase 8 approval queue.

    Never publishes anything itself - like the pricing and product
    agents, it only ever proposes a Recommendation for a human to
    approve (CONTRIBUTING.md: medium/high-risk actions require human
    approval). The actual marketplace call happens in
    `publish_listing_to_marketplace`, only after that approval, and only
    triggered by apps/api's approve route - not here.
    """
    return asyncio.run(
        _generate_listing_publish_recommendation(uuid.UUID(tenant_id), uuid.UUID(offer_id))
    )


async def _generate_listing_publish_recommendation(
    tenant_id: uuid.UUID, offer_id: uuid.UUID
) -> dict:
    async with session_scope() as db:
        offer = await db.scalar(
            select(Offer).where(Offer.id == offer_id, Offer.tenant_id == tenant_id)
        )
        if offer is None:
            return {"proposed": False, "reason": "offer not found"}

        variant = await db.get(Variant, offer.variant_id)
        product = await db.get(Product, variant.product_id)
        price = await db.scalar(select(Price).where(Price.offer_id == offer.id))

        # Idempotency (CONTRIBUTING.md #11): never stack duplicate pending
        # publish proposals for the same offer on a repeated run.
        existing = await db.scalar(
            select(Recommendation).where(
                Recommendation.tenant_id == tenant_id,
                Recommendation.entity_type == "offer",
                Recommendation.entity_id == offer.id,
                Recommendation.type == RecommendationType.LISTING_PUBLISH,
                Recommendation.status.in_(
                    [RecommendationStatus.PROPOSED, RecommendationStatus.PENDING_APPROVAL]
                ),
            )
        )
        if existing is not None:
            return {"proposed": False, "reason": "a publish recommendation is already pending"}

        proposal = build_listing_publish_proposal(offer=offer, product=product, price=price)
        if proposal is None:
            return {"proposed": False, "reason": "listing is not ready to publish"}

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


@app.task(name="worker.publish_listing_to_marketplace")
def publish_listing_to_marketplace(tenant_id: str, offer_id: str) -> dict:
    """Celery entrypoint for the real external mutation a
    `request_listing_publish` approval leaves behind: only apps/api's
    approve route enqueues this, and only after `cp_policies.approve()`
    has already flipped the offer to `PENDING` and written its own
    AuditEvent for that decision (CONTRIBUTING.md #2 - every external mutation
    goes through a typed connector; #11 - retry-safe/idempotent; #12/#13
    - never inline in an HTTP request handler, which is exactly where
    that approval was made).

    Idempotent: an offer that isn't `PENDING` anymore (already `ACTIVE`
    from an earlier successful run of this exact task, e.g. a Celery
    retry) is a no-op, not an error.
    """
    return asyncio.run(_publish_listing_to_marketplace(uuid.UUID(tenant_id), uuid.UUID(offer_id)))


async def _publish_listing_to_marketplace(tenant_id: uuid.UUID, offer_id: uuid.UUID) -> dict:
    async with session_scope() as db:
        offer = await db.scalar(
            select(Offer).where(Offer.id == offer_id, Offer.tenant_id == tenant_id)
        )
        if offer is None:
            raise ValueError(f"Offer {offer_id} not found for tenant {tenant_id}")

        if offer.status is not OfferStatus.PENDING:
            return {
                "published": False,
                "reason": f"offer status is {offer.status.value}, not pending",
            }

        connection = await db.get(Connection, offer.connection_id)
        credentials = decrypt_credentials(
            connection.encrypted_credentials, key=get_encryption_keys()
        )
        connector = build_connector(connection, credentials)

        before = {"status": offer.status.value}
        try:
            await connector.publish_offer(offer.external_id)
        except ConnectorError as exc:
            offer.status = OfferStatus.ERROR
            db.add(
                AuditEvent(
                    tenant_id=tenant_id,
                    actor_type=ActorType.SYSTEM,
                    action="publish_listing_to_marketplace",
                    entity_type="offer",
                    entity_id=offer.id,
                    before=before,
                    after={"status": offer.status.value},
                    result=AuditResult.FAILURE,
                    error_message=str(exc),
                )
            )
            await db.commit()
            return {"published": False, "reason": str(exc)}

        offer.status = OfferStatus.ACTIVE
        db.add(
            AuditEvent(
                tenant_id=tenant_id,
                actor_type=ActorType.SYSTEM,
                action="publish_listing_to_marketplace",
                entity_type="offer",
                entity_id=offer.id,
                before=before,
                after={"status": offer.status.value},
                result=AuditResult.SUCCESS,
            )
        )
        await db.commit()
        return {"published": True}
