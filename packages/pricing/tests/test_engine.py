from decimal import Decimal

import pytest

from cp_pricing import PricingInfeasibleError, PricingInputs, compute_price_bounds


def test_basic_case_with_no_fees_hits_target_margin_exactly() -> None:
    inputs = PricingInputs(
        cost=Decimal("60"),
        target_margin_rate=Decimal("0.4"),
        minimum_margin_rate=Decimal("0.2"),
    )

    result = compute_price_bounds(inputs)

    assert result.minimum_price == Decimal("75.00")
    assert result.recommended_price == Decimal("100.00")
    assert result.maximum_price is None
    assert result.expected_margin == Decimal("0.400")
    assert Decimal("0.1") <= result.confidence < Decimal("1.0")


def test_no_competitor_data_and_no_stock_data_lowers_confidence() -> None:
    inputs = PricingInputs(
        cost=Decimal("60"), target_margin_rate=Decimal("0.4"), minimum_margin_rate=Decimal("0.2")
    )

    result = compute_price_bounds(inputs)

    assert result.confidence == Decimal("0.70")
    assert "No competitor prices available" in result.reason


def test_recommendation_is_capped_at_the_priciest_competitor() -> None:
    inputs = PricingInputs(
        cost=Decimal("60"),
        target_margin_rate=Decimal("0.4"),
        minimum_margin_rate=Decimal("0.2"),
        competitor_prices=(Decimal("90"), Decimal("95")),
    )

    result = compute_price_bounds(inputs)

    assert result.maximum_price == Decimal("95")
    assert result.recommended_price == Decimal("95")
    assert result.expected_margin == Decimal("0.368")
    assert "Capped at the highest competitor price" in result.reason
    assert result.confidence == Decimal("0.75")


def test_recommendation_under_target_when_below_maximum_competitor() -> None:
    inputs = PricingInputs(
        cost=Decimal("60"),
        target_margin_rate=Decimal("0.4"),
        minimum_margin_rate=Decimal("0.2"),
        competitor_prices=(Decimal("150"), Decimal("200")),
    )

    result = compute_price_bounds(inputs)

    assert result.maximum_price == Decimal("200")
    assert result.recommended_price == Decimal("100.00")
    assert result.expected_margin == Decimal("0.400")


def test_holds_at_the_margin_floor_when_all_competitors_price_below_it() -> None:
    inputs = PricingInputs(
        cost=Decimal("60"),
        target_margin_rate=Decimal("0.4"),
        minimum_margin_rate=Decimal("0.2"),
        competitor_prices=(Decimal("50"), Decimal("60")),
    )

    result = compute_price_bounds(inputs)

    assert result.recommended_price == Decimal("75.00")
    assert result.expected_margin == Decimal("0.200")
    assert "price below our" in result.reason
    assert result.confidence == Decimal("0.50")


def test_low_stock_relative_to_velocity_adds_a_note_without_changing_price() -> None:
    inputs = PricingInputs(
        cost=Decimal("60"),
        target_margin_rate=Decimal("0.4"),
        minimum_margin_rate=Decimal("0.2"),
        current_stock=5,
        sales_velocity=Decimal("2"),
    )

    result = compute_price_bounds(inputs)

    assert result.recommended_price == Decimal("100.00")
    assert "Stock is low" in result.reason


def test_high_stock_relative_to_velocity_adds_a_different_note() -> None:
    inputs = PricingInputs(
        cost=Decimal("60"),
        target_margin_rate=Decimal("0.4"),
        minimum_margin_rate=Decimal("0.2"),
        current_stock=1000,
        sales_velocity=Decimal("1"),
    )

    result = compute_price_bounds(inputs)

    assert "Stock is high" in result.reason


def test_fees_and_vat_reduce_the_keepable_fraction_of_price() -> None:
    inputs = PricingInputs(
        cost=Decimal("50"),
        vat_rate=Decimal("0.23"),
        marketplace_fee_rate=Decimal("0.10"),
        payment_fee_rate=Decimal("0.02"),
        shipping_cost=Decimal("5"),
        target_margin_rate=Decimal("0.20"),
        minimum_margin_rate=Decimal("0.05"),
    )

    result = compute_price_bounds(inputs)

    # With VAT/fees eating into revenue, hitting even a modest 20% margin
    # requires a price well above the raw cost+shipping (55).
    assert result.recommended_price > Decimal("100")
    assert result.expected_margin == Decimal("0.200")


def test_infeasible_margin_raises_instead_of_returning_a_number() -> None:
    inputs = PricingInputs(
        cost=Decimal("10"),
        marketplace_fee_rate=Decimal("0.85"),
        minimum_margin_rate=Decimal("0.2"),
        target_margin_rate=Decimal("0.2"),
    )

    with pytest.raises(PricingInfeasibleError):
        compute_price_bounds(inputs)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"cost": Decimal("-1")},
        {"cost": Decimal("10"), "vat_rate": Decimal("-0.1")},
        {"cost": Decimal("10"), "marketplace_fee_rate": Decimal("-0.1")},
        {"cost": Decimal("10"), "payment_fee_rate": Decimal("-0.1")},
        {"cost": Decimal("10"), "shipping_cost": Decimal("-1")},
        {"cost": Decimal("10"), "minimum_margin_rate": Decimal("1")},
        {"cost": Decimal("10"), "target_margin_rate": Decimal("1")},
        {
            "cost": Decimal("10"),
            "target_margin_rate": Decimal("0.1"),
            "minimum_margin_rate": Decimal("0.2"),
        },
    ],
)
def test_invalid_inputs_are_rejected(kwargs: dict) -> None:
    with pytest.raises(ValueError):
        PricingInputs(**kwargs)
