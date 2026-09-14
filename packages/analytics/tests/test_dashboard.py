from decimal import Decimal

from cp_analytics import (
    OfferMetricsInput,
    ProductMetricsInput,
    compute_dashboard_metrics,
)


def _offer(
    *,
    price_amount: Decimal | None = Decimal("100.00"),
    cost: Decimal | None = None,
    stock_quantity: int | None = 5,
) -> OfferMetricsInput:
    return OfferMetricsInput(price_amount=price_amount, cost=cost, stock_quantity=stock_quantity)


def test_counts_products_by_status() -> None:
    products = [
        ProductMetricsInput(status="active", offers=[_offer()]),
        ProductMetricsInput(status="active", offers=[_offer()]),
        ProductMetricsInput(status="draft", offers=[]),
        ProductMetricsInput(status="archived", offers=[]),
    ]

    metrics = compute_dashboard_metrics(products=products)

    assert metrics.total_products == 4
    assert metrics.products_by_status == {"active": 2, "draft": 1, "archived": 1}


def test_counts_total_offers_and_missing_price() -> None:
    products = [
        ProductMetricsInput(status="active", offers=[_offer(), _offer(price_amount=None)]),
    ]

    metrics = compute_dashboard_metrics(products=products)

    assert metrics.total_offers == 2
    assert metrics.offers_missing_price == 1


def test_out_of_stock_counted_only_when_stock_known_and_nonpositive() -> None:
    products = [
        ProductMetricsInput(
            status="active",
            offers=[
                _offer(stock_quantity=0),
                _offer(stock_quantity=-1),
                _offer(stock_quantity=5),
                _offer(stock_quantity=None),
            ],
        ),
    ]

    metrics = compute_dashboard_metrics(products=products)

    assert metrics.out_of_stock_offers == 2


def test_total_catalog_value_sums_price_times_stock() -> None:
    products = [
        ProductMetricsInput(
            status="active",
            offers=[
                _offer(price_amount=Decimal("10.00"), stock_quantity=3),
                _offer(price_amount=Decimal("5.00"), stock_quantity=2),
            ],
        ),
    ]

    metrics = compute_dashboard_metrics(products=products)

    assert metrics.total_catalog_value == Decimal("40.00")


def test_catalog_value_ignores_offers_missing_price_or_stock() -> None:
    products = [
        ProductMetricsInput(
            status="active",
            offers=[
                _offer(price_amount=None, stock_quantity=10),
                _offer(price_amount=Decimal("10.00"), stock_quantity=None),
            ],
        ),
    ]

    metrics = compute_dashboard_metrics(products=products)

    assert metrics.total_catalog_value == Decimal("0")


def test_average_margin_rate_across_offers_with_cost_and_price() -> None:
    products = [
        ProductMetricsInput(
            status="active",
            offers=[
                _offer(price_amount=Decimal("100"), cost=Decimal("50")),  # 0.5
                _offer(price_amount=Decimal("100"), cost=Decimal("75")),  # 0.25
            ],
        ),
    ]

    metrics = compute_dashboard_metrics(products=products)

    assert metrics.average_margin_rate == Decimal("0.375")


def test_average_margin_rate_is_none_without_any_qualifying_offer() -> None:
    products = [
        ProductMetricsInput(status="active", offers=[_offer(cost=None)]),
    ]

    metrics = compute_dashboard_metrics(products=products)

    assert metrics.average_margin_rate is None


def test_recommendation_and_catalog_counts_pass_through() -> None:
    metrics = compute_dashboard_metrics(
        products=[],
        recommendation_counts_by_status={"pending_approval": 3, "success": 5},
        recommendation_counts_by_type={"price_change": 2, "catalog_fix": 1},
        latest_catalog_issue_count=7,
    )

    assert metrics.recommendations_by_status == {"pending_approval": 3, "success": 5}
    assert metrics.recommendations_by_type == {"price_change": 2, "catalog_fix": 1}
    assert metrics.latest_catalog_issue_count == 7


def test_empty_catalog_produces_zeroed_metrics() -> None:
    metrics = compute_dashboard_metrics(products=[])

    assert metrics.total_products == 0
    assert metrics.products_by_status == {}
    assert metrics.total_offers == 0
    assert metrics.total_catalog_value == Decimal("0")
    assert metrics.average_margin_rate is None
    assert metrics.latest_catalog_issue_count is None
