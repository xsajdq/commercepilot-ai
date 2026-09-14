from decimal import Decimal

# Plan tier identifiers - plain strings, not an enum, so this package
# stays dependency-free like cp_pricing/cp_analytics.
# `cp_domain.subscription.PlanTier` is the canonical enum a caller
# actually stores; it never imports this package, and callers translate
# `PlanTier.value` into these same string keys instead.
FREE = "free"
STARTER = "starter"
PRO = "pro"

# Monthly AI spend budget per plan, in USD - our own product decision,
# not a claim about external fact. Update this table (and the Stripe
# price ids apps/api's config points at) together when pricing changes.
PLAN_AI_BUDGETS: dict[str, Decimal] = {
    FREE: Decimal("1.00"),
    STARTER: Decimal("10.00"),
    PRO: Decimal("50.00"),
}


def ai_budget_for_plan(plan: str) -> Decimal:
    """Raises KeyError for an unrecognized plan - callers should treat
    that as a bug (a new plan added without updating this table), not
    silently fall back to some default budget."""
    return PLAN_AI_BUDGETS[plan]
