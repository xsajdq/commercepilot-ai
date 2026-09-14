import enum
from datetime import datetime

from cp_shared.db import Base, TenantScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin
from sqlalchemy import DateTime, String, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column


class PlanTier(str, enum.Enum):
    """String values double as the plan-tier keys `cp_billing.plans
    .PLAN_AI_BUDGETS` is keyed by - `cp_billing` itself never imports
    this enum (it stays dependency-free like `cp_pricing`/`cp_analytics`)
    so a caller always bridges the two via `PlanTier.value`."""

    FREE = "free"
    STARTER = "starter"
    PRO = "pro"


class SubscriptionStatus(str, enum.Enum):
    """Mirrors Stripe's own subscription status vocabulary (translated,
    not copied 1:1 - Stripe has more statuses than we act on
    differently) - the same "each platform's own vocabulary, mapped
    deliberately" approach `cp_sync.products._STATUS_MAP` already uses
    for connector platforms."""

    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELED = "canceled"
    INCOMPLETE = "incomplete"


class Subscription(UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin, Base):
    """One row per tenant (unique on `tenant_id`) - a tenant with no
    Stripe subscription yet is still `PlanTier.FREE`/
    `SubscriptionStatus.ACTIVE` with both Stripe ids `None`, so every
    tenant always has exactly one `Subscription` to read a plan/budget
    from, never a nullable "no subscription" case callers have to
    special-case."""

    __tablename__ = "subscriptions"
    __table_args__ = (UniqueConstraint("tenant_id", name="uq_subscriptions_tenant_id"),)

    plan: Mapped[PlanTier] = mapped_column(
        SAEnum(PlanTier, name="plan_tier"), nullable=False, default=PlanTier.FREE
    )
    status: Mapped[SubscriptionStatus] = mapped_column(
        SAEnum(SubscriptionStatus, name="subscription_status"),
        nullable=False,
        default=SubscriptionStatus.ACTIVE,
    )
    stripe_customer_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(
        String(255), unique=True, nullable=True
    )
    current_period_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
