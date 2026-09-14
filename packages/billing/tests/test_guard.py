from decimal import Decimal

import pytest

from cp_billing.guard import check_ai_budget
from cp_billing.plans import FREE, STARTER, ai_budget_for_plan


class TestCheckAiBudget:
    def test_under_budget_is_not_exceeded(self) -> None:
        status = check_ai_budget(plan=STARTER, spent_this_period=Decimal("2.00"))
        assert status.is_exceeded is False
        assert status.budget == ai_budget_for_plan(STARTER)
        assert status.remaining == ai_budget_for_plan(STARTER) - Decimal("2.00")

    def test_spending_exactly_the_budget_counts_as_exceeded(self) -> None:
        budget = ai_budget_for_plan(FREE)
        status = check_ai_budget(plan=FREE, spent_this_period=budget)
        assert status.is_exceeded is True
        assert status.remaining == Decimal("0")

    def test_over_budget_is_exceeded_with_negative_remaining(self) -> None:
        budget = ai_budget_for_plan(FREE)
        status = check_ai_budget(plan=FREE, spent_this_period=budget + Decimal("5.00"))
        assert status.is_exceeded is True
        assert status.remaining == Decimal("-5.00")

    def test_zero_spend_is_never_exceeded(self) -> None:
        status = check_ai_budget(plan=FREE, spent_this_period=Decimal("0"))
        assert status.is_exceeded is False

    def test_unknown_plan_raises_key_error(self) -> None:
        with pytest.raises(KeyError):
            check_ai_budget(plan="enterprise", spent_this_period=Decimal("0"))
