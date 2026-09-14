import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated

from cp_billing import check_ai_budget
from cp_domain.ai_job import AIJob
from cp_domain.subscription import PlanTier, Subscription, SubscriptionStatus
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_membership
from app.core.config import Settings, get_settings
from app.core.stripe_client import get_stripe_client
from app.db.base import get_db
from app.db.models.membership import Membership

router = APIRouter(prefix="/billing", tags=["billing"])

_PLAN_TO_PRICE_SETTING = {
    PlanTier.STARTER: "stripe_price_id_starter",
    PlanTier.PRO: "stripe_price_id_pro",
}

_STRIPE_STATUS_MAP = {
    "active": SubscriptionStatus.ACTIVE,
    "trialing": SubscriptionStatus.ACTIVE,
    "past_due": SubscriptionStatus.PAST_DUE,
    "unpaid": SubscriptionStatus.PAST_DUE,
    "canceled": SubscriptionStatus.CANCELED,
    "incomplete_expired": SubscriptionStatus.CANCELED,
    "incomplete": SubscriptionStatus.INCOMPLETE,
}


class BillingStatusOut(BaseModel):
    plan: PlanTier
    status: SubscriptionStatus
    budget: str
    spent_this_period: str
    remaining: str
    is_exceeded: bool
    has_stripe_subscription: bool


class CheckoutRequest(BaseModel):
    plan: PlanTier


class CheckoutOut(BaseModel):
    checkout_url: str


class PortalOut(BaseModel):
    portal_url: str


async def _get_or_create_subscription(db: AsyncSession, tenant_id: uuid.UUID) -> Subscription:
    """Same get-or-create shape as `worker.cost_guard.get_or_create_subscription`,
    deliberately re-implemented rather than imported: apps/api and
    apps/worker never import each other's code (CLAUDE.md), only
    `packages/`, and this needs a live `AsyncSession` + `cp_domain`,
    which `cp_billing` intentionally doesn't depend on (it stays pure
    math - see `packages/billing/README.md`)."""
    subscription = await db.scalar(select(Subscription).where(Subscription.tenant_id == tenant_id))
    if subscription is None:
        subscription = Subscription(tenant_id=tenant_id)
        db.add(subscription)
        await db.commit()
    return subscription


async def _current_period_ai_spend(db: AsyncSession, tenant_id: uuid.UUID) -> Decimal:
    """Same "current calendar month, UTC" definition as
    `worker.cost_guard.current_period_ai_spend` - what this endpoint
    reports must match exactly what the worker's cost guard enforces."""
    period_start = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    total = await db.scalar(
        select(func.sum(AIJob.cost_estimate)).where(
            AIJob.tenant_id == tenant_id, AIJob.created_at >= period_start
        )
    )
    return total or Decimal("0")


def _price_id_for_plan(settings: Settings, plan: PlanTier) -> str | None:
    return getattr(settings, _PLAN_TO_PRICE_SETTING[plan])


def _plan_for_price_id(settings: Settings, price_id: str | None) -> PlanTier | None:
    if price_id is None:
        return None
    for plan, setting_name in _PLAN_TO_PRICE_SETTING.items():
        if getattr(settings, setting_name) == price_id:
            return plan
    return None


@router.get("", response_model=BillingStatusOut)
async def get_billing_status(
    db: Annotated[AsyncSession, Depends(get_db)],
    membership: Annotated[Membership, Depends(get_current_membership)],
) -> BillingStatusOut:
    subscription = await _get_or_create_subscription(db, membership.tenant_id)
    spent = await _current_period_ai_spend(db, membership.tenant_id)
    budget_status = check_ai_budget(plan=subscription.plan.value, spent_this_period=spent)
    return BillingStatusOut(
        plan=subscription.plan,
        status=subscription.status,
        budget=str(budget_status.budget),
        spent_this_period=str(budget_status.spent),
        remaining=str(budget_status.remaining),
        is_exceeded=budget_status.is_exceeded,
        has_stripe_subscription=subscription.stripe_subscription_id is not None,
    )


@router.post("/checkout", response_model=CheckoutOut)
async def create_checkout_session(
    payload: CheckoutRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    membership: Annotated[Membership, Depends(get_current_membership)],
) -> CheckoutOut:
    if payload.plan not in _PLAN_TO_PRICE_SETTING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The free plan has no checkout - only starter/pro can be purchased",
        )

    settings = get_settings()
    client = get_stripe_client()
    price_id = _price_id_for_plan(settings, payload.plan)
    if client is None or not price_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Billing is not configured",
        )

    subscription = await _get_or_create_subscription(db, membership.tenant_id)
    if subscription.stripe_customer_id is None:
        customer = client.Customer.create(
            email=membership.user.email,
            metadata={"tenant_id": str(membership.tenant_id)},
        )
        subscription.stripe_customer_id = customer.id
        await db.commit()

    session = client.checkout.Session.create(
        mode="subscription",
        customer=subscription.stripe_customer_id,
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=f"{settings.billing_return_url}?checkout=success",
        cancel_url=f"{settings.billing_return_url}?checkout=cancelled",
        client_reference_id=str(membership.tenant_id),
        metadata={"tenant_id": str(membership.tenant_id), "plan": payload.plan.value},
    )
    return CheckoutOut(checkout_url=session.url)


@router.post("/portal", response_model=PortalOut)
async def create_portal_session(
    db: Annotated[AsyncSession, Depends(get_db)],
    membership: Annotated[Membership, Depends(get_current_membership)],
) -> PortalOut:
    settings = get_settings()
    client = get_stripe_client()
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Billing is not configured",
        )

    subscription = await _get_or_create_subscription(db, membership.tenant_id)
    if subscription.stripe_customer_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This tenant has no Stripe customer yet - checkout first",
        )

    session = client.billing_portal.Session.create(
        customer=subscription.stripe_customer_id,
        return_url=settings.billing_return_url,
    )
    return PortalOut(portal_url=session.url)


async def _sync_subscription_from_stripe_object(
    db: AsyncSession, settings: Settings, stripe_subscription: dict
) -> None:
    """Applies a Stripe `subscription` object's real, current state onto
    our local row - matched by `stripe_customer_id`, which we set
    ourselves in `create_checkout_session` before Stripe ever creates the
    subscription, so this always finds the right tenant without trusting
    anything from the webhook payload as an identifier we didn't
    originate."""
    customer_id = stripe_subscription.get("customer")
    subscription = await db.scalar(
        select(Subscription).where(Subscription.stripe_customer_id == customer_id)
    )
    if subscription is None:
        return

    subscription.stripe_subscription_id = stripe_subscription.get("id")
    stripe_status = stripe_subscription.get("status")
    if stripe_status in _STRIPE_STATUS_MAP:
        subscription.status = _STRIPE_STATUS_MAP[stripe_status]

    items = (stripe_subscription.get("items") or {}).get("data") or []
    price_id = items[0].get("price", {}).get("id") if items else None
    plan = _plan_for_price_id(settings, price_id)
    if plan is not None:
        subscription.plan = plan

    period_end = stripe_subscription.get("current_period_end")
    if period_end is not None:
        subscription.current_period_end = datetime.fromtimestamp(period_end, tz=UTC)

    await db.commit()


async def _mark_subscription_canceled(db: AsyncSession, stripe_subscription: dict) -> None:
    subscription = await db.scalar(
        select(Subscription).where(
            Subscription.stripe_subscription_id == stripe_subscription.get("id")
        )
    )
    if subscription is None:
        return
    subscription.status = SubscriptionStatus.CANCELED
    subscription.plan = PlanTier.FREE
    await db.commit()


@router.post("/webhook", include_in_schema=False)
async def stripe_webhook(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Public (no auth) by necessity - Stripe calls this directly. Every
    event is signature-verified against our own webhook secret before
    any of its content is trusted or acted on; an unverified or
    malformed payload is rejected outright rather than parsed."""
    settings = get_settings()
    client = get_stripe_client()
    if client is None or not settings.stripe_webhook_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Billing is not configured",
        )

    payload = await request.body()
    signature = request.headers.get("stripe-signature", "")
    try:
        event = client.Webhook.construct_event(payload, signature, settings.stripe_webhook_secret)
    except Exception as exc:  # noqa: BLE001 - any verification failure is an invalid request
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid webhook signature"
        ) from exc

    event_type = event["type"]
    data = event["data"]["object"]

    if event_type in ("customer.subscription.created", "customer.subscription.updated"):
        await _sync_subscription_from_stripe_object(db, settings, data)
    elif event_type == "customer.subscription.deleted":
        await _mark_subscription_canceled(db, data)
    # "checkout.session.completed" carries no new state we don't already
    # get from the subscription.created/updated event Stripe sends
    # alongside it - nothing to do beyond acknowledging receipt below.

    return {"received": True}
