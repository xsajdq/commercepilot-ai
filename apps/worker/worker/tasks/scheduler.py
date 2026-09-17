import asyncio

from cp_domain.connection import Connection
from cp_domain.offer import Offer
from cp_domain.price import Price
from cp_domain.product import Product
from sqlalchemy import select

from worker.celery_app import app
from worker.db import session_scope
from worker.tasks.analytics import generate_dashboard_narrative
from worker.tasks.catalog import run_catalog_audit
from worker.tasks.listing import generate_listing_publish_recommendation
from worker.tasks.pricing import generate_price_recommendation
from worker.tasks.sync import sync_connection


@app.task(name="worker.dispatch_daily_sync")
def dispatch_daily_sync() -> dict:
    """Celery Beat's daily 01:00 UTC entrypoint - keeps every tenant's
    catalog fresh before `dispatch_daily_recommendations` runs an hour
    later. Fans out one `worker.sync_connection` per `Connection`, itself
    already retry-safe/idempotent (CONTRIBUTING.md #11) - this task does no
    sync work itself, only enqueues.

    A dispatcher, not a full pipeline: Celery gives no ordering
    guarantee between this task's fan-out and the next beat entry's, so
    "an hour's head start" is a pragmatic staggering, not a guaranteed
    happens-before. Good enough for a daily cadence; a real
    sync-then-recommend pipeline (a chord/callback) is more machinery
    than this phase needs.
    """
    return asyncio.run(_dispatch_daily_sync())


async def _dispatch_daily_sync() -> dict:
    async with session_scope() as db:
        connections = (await db.execute(select(Connection.id, Connection.tenant_id))).all()
        for connection_id, tenant_id in connections:
            sync_connection.delay(str(tenant_id), str(connection_id))
        return {"connections_synced": len(connections)}


@app.task(name="worker.dispatch_daily_recommendations")
def dispatch_daily_recommendations() -> dict:
    """Celery Beat's daily 02:00 UTC entrypoint - the "daily scheduler
    tying agents together" this phase is named for. Fans out to every
    agent whose own cost is bounded and predictable (a deterministic
    calculation, or at most one LLM call per tenant per day): the
    catalog audit and analytics narrative (once per tenant that
    actually has products), plus a pricing check per priced offer and a
    listing-publish check per offer that already exists on a
    marketplace (has an `external_id`).

    Deliberately excludes `generate_product_content_recommendation`:
    that makes one real LLM call *per product*, and with no AI usage/
    cost guard yet (Phase 20 - "Billing"), auto-triggering it for every
    product across every tenant, daily, unbounded, is a real cost risk
    this phase isn't the place to accept. A human still has to click
    "Generate content" per product until that guard exists - every task
    dispatched here already only *proposes* a recommendation anyway
    (never mutates), so the risk being managed is API spend, not safety.
    """
    return asyncio.run(_dispatch_daily_recommendations())


async def _dispatch_daily_recommendations() -> dict:
    async with session_scope() as db:
        tenant_ids = list(await db.scalars(select(Product.tenant_id).distinct()))
        for tenant_id in tenant_ids:
            run_catalog_audit.delay(str(tenant_id))
            generate_dashboard_narrative.delay(str(tenant_id))

        priced_offers = (
            await db.execute(
                select(Offer.id, Offer.tenant_id).join(Price, Price.offer_id == Offer.id)
            )
        ).all()
        for offer_id, tenant_id in priced_offers:
            generate_price_recommendation.delay(str(tenant_id), str(offer_id))

        listable_offers = (
            await db.execute(
                select(Offer.id, Offer.tenant_id).where(Offer.external_id.is_not(None))
            )
        ).all()
        for offer_id, tenant_id in listable_offers:
            generate_listing_publish_recommendation.delay(str(tenant_id), str(offer_id))

        return {
            "tenants_processed": len(tenant_ids),
            "pricing_checks_queued": len(priced_offers),
            "listing_checks_queued": len(listable_offers),
        }
