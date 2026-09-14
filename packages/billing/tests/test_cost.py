from decimal import Decimal

from cp_billing.cost import compute_cost


class TestComputeCost:
    def test_computes_a_real_dollar_amount_from_token_counts(self) -> None:
        cost = compute_cost(
            provider="anthropic",
            model="claude-sonnet-5",
            input_tokens=1_000_000,
            output_tokens=1_000_000,
        )
        assert cost == Decimal("3.00") + Decimal("15.00")

    def test_zero_tokens_costs_nothing(self) -> None:
        cost = compute_cost(
            provider="anthropic", model="claude-sonnet-5", input_tokens=0, output_tokens=0
        )
        assert cost == Decimal("0")

    def test_input_and_output_are_priced_independently(self) -> None:
        input_only = compute_cost(
            provider="anthropic", model="claude-sonnet-5", input_tokens=500_000, output_tokens=0
        )
        output_only = compute_cost(
            provider="anthropic", model="claude-sonnet-5", input_tokens=0, output_tokens=500_000
        )
        assert input_only == Decimal("1.50")
        assert output_only == Decimal("7.50")

    def test_unrecognized_model_returns_none_rather_than_a_guess(self) -> None:
        cost = compute_cost(
            provider="openai", model="gpt-not-in-the-table", input_tokens=100, output_tokens=100
        )
        assert cost is None
