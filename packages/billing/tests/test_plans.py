from decimal import Decimal

import pytest

from cp_billing.plans import FREE, PLAN_AI_BUDGETS, PRO, STARTER, ai_budget_for_plan


class TestAiBudgetForPlan:
    def test_free_plan_has_the_smallest_budget(self) -> None:
        assert ai_budget_for_plan(FREE) < ai_budget_for_plan(STARTER) < ai_budget_for_plan(PRO)

    def test_returns_a_decimal_matching_the_table(self) -> None:
        assert ai_budget_for_plan(STARTER) == PLAN_AI_BUDGETS[STARTER]
        assert isinstance(ai_budget_for_plan(STARTER), Decimal)

    def test_unknown_plan_raises_key_error(self) -> None:
        with pytest.raises(KeyError):
            ai_budget_for_plan("enterprise")
