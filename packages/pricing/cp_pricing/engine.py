from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

_CENT = Decimal("0.01")
_ZERO = Decimal("0")
_ONE = Decimal("1")


class PricingInfeasibleError(Exception):
    """No finite price can achieve the requested margin: percentage-based
    costs (VAT + marketplace fee + payment fee) alone already consume
    the requested margin's share of revenue, or more. This is arithmetic,
    not a guess - CLAUDE.md #9/#10 say don't invent a number when the
    real answer is "no price works," so this is raised instead of
    returning something misleading.
    """


@dataclass(frozen=True)
class PricingInputs:
    """All rates are fractions of the gross (VAT-inclusive) selling
    price, not percentages - 0.23, not 23. `shipping_cost` and `cost`
    are absolute per-unit amounts in the same currency as the price.

    Assumes the common "free shipping to the buyer" e-commerce model:
    the listed price is what the customer pays in full, and
    `shipping_cost` is the seller's own cost of fulfilling it, eaten
    out of margin like any other cost - not a separate line the
    customer pays on top.
    """

    cost: Decimal
    vat_rate: Decimal = _ZERO
    marketplace_fee_rate: Decimal = _ZERO
    payment_fee_rate: Decimal = _ZERO
    shipping_cost: Decimal = _ZERO
    target_margin_rate: Decimal = Decimal("0.30")
    minimum_margin_rate: Decimal = Decimal("0.10")
    competitor_prices: tuple[Decimal, ...] = field(default_factory=tuple)
    current_stock: int | None = None
    sales_velocity: Decimal | None = None

    def __post_init__(self) -> None:
        if self.cost < _ZERO:
            raise ValueError("cost cannot be negative")
        for name in ("vat_rate", "marketplace_fee_rate", "payment_fee_rate"):
            value = getattr(self, name)
            if value < _ZERO:
                raise ValueError(f"{name} cannot be negative")
        if self.shipping_cost < _ZERO:
            raise ValueError("shipping_cost cannot be negative")
        if not (_ZERO <= self.minimum_margin_rate < _ONE):
            raise ValueError("minimum_margin_rate must be in [0, 1)")
        if not (_ZERO <= self.target_margin_rate < _ONE):
            raise ValueError("target_margin_rate must be in [0, 1)")
        if self.target_margin_rate < self.minimum_margin_rate:
            raise ValueError("target_margin_rate cannot be below minimum_margin_rate")


@dataclass(frozen=True)
class PricingResult:
    minimum_price: Decimal
    recommended_price: Decimal
    maximum_price: Decimal | None
    expected_margin: Decimal
    reason: str
    confidence: Decimal


def _round_money(value: Decimal) -> Decimal:
    return value.quantize(_CENT, rounding=ROUND_HALF_UP)


def _keepable_fraction(inputs: PricingInputs) -> Decimal:
    """Fraction of the gross price left after VAT (remitted, never the
    seller's to keep) and the two percentage-based fees. What's left
    over still has to cover `shipping_cost + cost` before anything is
    profit."""
    vat_share = inputs.vat_rate / (_ONE + inputs.vat_rate)
    return _ONE - vat_share - inputs.marketplace_fee_rate - inputs.payment_fee_rate


def _price_for_margin(inputs: PricingInputs, k: Decimal, margin_rate: Decimal) -> Decimal:
    headroom = k - margin_rate
    if headroom <= _ZERO:
        raise PricingInfeasibleError(
            f"A {margin_rate:.0%} margin is unreachable at any price: VAT/fees alone leave "
            f"only {k:.0%} of revenue, which must also cover margin."
        )
    fixed_costs = inputs.shipping_cost + inputs.cost
    return _round_money(fixed_costs / headroom)


def _margin_at_price(inputs: PricingInputs, k: Decimal, price: Decimal) -> Decimal:
    fixed_costs = inputs.shipping_cost + inputs.cost
    return k - (fixed_costs / price)


def compute_price_bounds(inputs: PricingInputs) -> PricingResult:
    """Deterministic pricing math - CLAUDE.md #10: this is code, never an
    LLM call. Given costs/fees/margins (and, optionally, competitor
    prices and stock/velocity for context), returns the price floor that
    protects `minimum_margin_rate`, a recommendation aimed at
    `target_margin_rate` but never priced above the most expensive
    visible competitor, and the margin that recommendation actually
    delivers.

    Raises `PricingInfeasibleError` if even the *minimum* margin can't
    be reached at any price - a real signal ("this SKU can't be
    profitable under these fees") that callers should treat as
    `UNKNOWN`/unactionable, not paper over.
    """
    k = _keepable_fraction(inputs)

    minimum_price = _price_for_margin(inputs, k, inputs.minimum_margin_rate)
    target_price = _price_for_margin(inputs, k, inputs.target_margin_rate)

    reason_parts = [
        f"Target margin {inputs.target_margin_rate:.0%} after VAT "
        f"({inputs.vat_rate:.0%}), marketplace fee ({inputs.marketplace_fee_rate:.0%}), "
        f"and payment fee ({inputs.payment_fee_rate:.0%}) gives a base price of "
        f"{target_price}."
    ]
    confidence = Decimal("1.0")

    maximum_price: Decimal | None = None
    recommended_price = target_price

    if inputs.competitor_prices:
        maximum_price = max(inputs.competitor_prices)
        if recommended_price > maximum_price:
            if maximum_price < minimum_price:
                recommended_price = minimum_price
                reason_parts.append(
                    f"All visible competitors ({min(inputs.competitor_prices)}-"
                    f"{maximum_price}) price below our {inputs.minimum_margin_rate:.0%} "
                    "margin floor - holding at the floor price instead of matching them."
                )
                confidence -= Decimal("0.4")
            else:
                recommended_price = maximum_price
                reason_parts.append(
                    f"Capped at the highest competitor price ({maximum_price}) rather than "
                    "pricing above the whole market."
                )
                confidence -= Decimal("0.15")
    else:
        reason_parts.append("No competitor prices available - recommendation is cost-based only.")
        confidence -= Decimal("0.2")

    if inputs.current_stock is None or inputs.sales_velocity is None:
        confidence -= Decimal("0.1")
    elif inputs.sales_velocity > 0:
        days_of_stock = Decimal(inputs.current_stock) / inputs.sales_velocity
        if days_of_stock < Decimal("7"):
            reason_parts.append(
                f"Stock is low ({inputs.current_stock} units, ~{days_of_stock:.0f} days at "
                "current sales velocity) - consider holding this price rather than discounting."
            )
        elif days_of_stock > Decimal("60"):
            reason_parts.append(
                f"Stock is high ({inputs.current_stock} units, ~{days_of_stock:.0f} days at "
                "current sales velocity) - a more aggressive price may help it move."
            )

    expected_margin = _margin_at_price(inputs, k, recommended_price)
    confidence = max(Decimal("0.1"), min(Decimal("1.0"), confidence))

    return PricingResult(
        minimum_price=minimum_price,
        recommended_price=recommended_price,
        maximum_price=maximum_price,
        expected_margin=expected_margin.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP),
        reason=" ".join(reason_parts),
        confidence=confidence.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
    )
