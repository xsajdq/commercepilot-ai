import uuid
from datetime import UTC, datetime
from decimal import Decimal

from cp_ai.providers import TokenUsage
from cp_billing import AIBudgetStatus, check_ai_budget, compute_cost
from cp_domain.ai_job import AIJob
from cp_domain.subscription import Subscription
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

_AI_PROVIDER_NAME = "anthropic"


async def get_or_create_subscription(db: AsyncSession, tenant_id: uuid.UUID) -> Subscription:
    """Every tenant gets a `Subscription` row at registration (Phase 20),
    but a tenant created before this phase existed won't have one yet -
    get-or-create here rather than assuming the row exists, so this
    never breaks on a tenant that predates the migration."""
    subscription = await db.scalar(
        select(Subscription).where(Subscription.tenant_id == tenant_id)
    )
    if subscription is None:
        subscription = Subscription(tenant_id=tenant_id)
        db.add(subscription)
        await db.flush()
    return subscription


async def current_period_ai_spend(db: AsyncSession, tenant_id: uuid.UUID) -> Decimal:
    """Sums real `AIJob.cost_estimate` rows for the tenant since the
    start of the current calendar month (UTC) - a simplification kept
    deliberately independent of Stripe's own billing-cycle boundaries,
    so the guard works the same for a free tenant with no Stripe
    subscription at all. A job with `cost_estimate IS NULL` (the
    provider reported no usage, or failed before any API call) is
    excluded rather than counted as zero or guessed - we can't sum what
    we don't know."""
    period_start = datetime.now(UTC).replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )
    total = await db.scalar(
        select(func.sum(AIJob.cost_estimate)).where(
            AIJob.tenant_id == tenant_id, AIJob.created_at >= period_start
        )
    )
    return total or Decimal("0")


async def check_tenant_ai_budget(db: AsyncSession, tenant_id: uuid.UUID) -> AIBudgetStatus:
    """The one thing every AI-calling worker task should check before
    making a real (billed) provider call - see `cp_billing.check_ai_budget`
    for what the result actually means; this function only gathers the
    real numbers it needs."""
    subscription = await get_or_create_subscription(db, tenant_id)
    spent = await current_period_ai_spend(db, tenant_id)
    return check_ai_budget(plan=subscription.plan.value, spent_this_period=spent)


def record_usage_on_job(job: AIJob, *, usage: TokenUsage | None, model: str) -> None:
    """Records real token usage and its deterministic cost estimate on
    an `AIJob` after a successful provider call. A `None` usage (the
    provider genuinely couldn't report it) leaves tokens_used/cost_estimate
    at their honest `None` default rather than guessing zero."""
    if usage is None:
        return
    job.ai_provider = _AI_PROVIDER_NAME
    job.ai_model = model
    job.tokens_used = usage.input_tokens + usage.output_tokens
    job.cost_estimate = compute_cost(
        provider=_AI_PROVIDER_NAME,
        model=model,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
    )
