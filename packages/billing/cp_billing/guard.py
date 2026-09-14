from dataclasses import dataclass
from decimal import Decimal

from cp_billing.plans import ai_budget_for_plan


@dataclass(frozen=True)
class AIBudgetStatus:
    plan: str
    budget: Decimal
    spent: Decimal
    remaining: Decimal
    is_exceeded: bool


def check_ai_budget(*, plan: str, spent_this_period: Decimal) -> AIBudgetStatus:
    """Pure comparison - the caller computes `spent_this_period` (a real
    sum of `AIJob.cost_estimate` for the tenant's current billing
    period) and is responsible for actually refusing to run an agent
    when `is_exceeded` is True (see `apps/worker`'s cost-guard helper).
    This function only decides the number; it enforces nothing itself,
    the same separation `cp_pricing.compute_price_bounds` keeps between
    computing a price and anything acting on it."""
    budget = ai_budget_for_plan(plan)
    remaining = budget - spent_this_period
    return AIBudgetStatus(
        plan=plan,
        budget=budget,
        spent=spent_this_period,
        remaining=remaining,
        is_exceeded=spent_this_period >= budget,
    )
