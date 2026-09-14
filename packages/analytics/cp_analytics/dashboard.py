from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import Decimal


@dataclass(frozen=True)
class OfferMetricsInput:
    """Plain, connector/domain-free view of one offer - the caller (an
    app, not this package) is responsible for extracting these from real
    `cp_domain` rows, the same way `cp_pricing.PricingInputs` keeps this
    package dependency-free."""

    price_amount: Decimal | None
    cost: Decimal | None
    stock_quantity: int | None  # None = no stock record at all


@dataclass(frozen=True)
class ProductMetricsInput:
    status: str  # "draft" | "active" | "archived"
    offers: list[OfferMetricsInput] = field(default_factory=list)


@dataclass(frozen=True)
class DashboardMetrics:
    total_products: int
    products_by_status: dict[str, int]
    total_offers: int
    offers_missing_price: int
    out_of_stock_offers: int
    total_catalog_value: Decimal
    average_margin_rate: Decimal | None
    recommendations_by_status: dict[str, int]
    recommendations_by_type: dict[str, int]
    latest_catalog_issue_count: int | None


def compute_dashboard_metrics(
    *,
    products: Iterable[ProductMetricsInput],
    recommendation_counts_by_status: dict[str, int] | None = None,
    recommendation_counts_by_type: dict[str, int] | None = None,
    latest_catalog_issue_count: int | None = None,
) -> DashboardMetrics:
    """Phase 13's "dashboard" half - pure aggregation over already-loaded
    data, no I/O, no AI (CLAUDE.md #10's "math is code" spirit extended
    to reporting, not just pricing: a count is a count, not something an
    LLM should be asked to compute). The "AI narrative" half
    (`cp_ai.agents.analytics_agent`) only ever narrates these exact
    numbers - it never gets to compute or restate them differently.

    `total_catalog_value` sums `price * stock` only where both are
    known (an offer missing either contributes 0, not a guess).
    `average_margin_rate` is the mean of `(price - cost) / price` across
    offers where both are known and price is positive; `None` when no
    offer qualifies (never presented as 0, which would misleadingly read
    as "no margin" rather than "no data").
    """
    products_by_status: dict[str, int] = {}
    total_offers = 0
    offers_missing_price = 0
    out_of_stock_offers = 0
    total_catalog_value = Decimal("0")
    margin_rates: list[Decimal] = []
    total_products = 0

    for product in products:
        total_products += 1
        products_by_status[product.status] = products_by_status.get(product.status, 0) + 1

        for offer in product.offers:
            total_offers += 1

            if offer.price_amount is None:
                offers_missing_price += 1
            else:
                if offer.stock_quantity is not None:
                    total_catalog_value += offer.price_amount * offer.stock_quantity
                if offer.cost is not None and offer.price_amount > 0:
                    margin_rates.append(
                        (offer.price_amount - offer.cost) / offer.price_amount
                    )

            if offer.stock_quantity is not None and offer.stock_quantity <= 0:
                out_of_stock_offers += 1

    average_margin_rate = (
        sum(margin_rates) / len(margin_rates) if margin_rates else None
    )

    return DashboardMetrics(
        total_products=total_products,
        products_by_status=products_by_status,
        total_offers=total_offers,
        offers_missing_price=offers_missing_price,
        out_of_stock_offers=out_of_stock_offers,
        total_catalog_value=total_catalog_value,
        average_margin_rate=average_margin_rate,
        recommendations_by_status=dict(recommendation_counts_by_status or {}),
        recommendations_by_type=dict(recommendation_counts_by_type or {}),
        latest_catalog_issue_count=latest_catalog_issue_count,
    )
