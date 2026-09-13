import uuid
from dataclasses import dataclass
from decimal import Decimal

from cp_domain.price import Price
from cp_domain.product import Product
from cp_domain.recommendation import RecommendationType, RiskLevel
from cp_pricing import PricingInfeasibleError, PricingInputs, compute_price_bounds

from cp_ai.tools.builtin.product_tools import update_price_tool

_HUNDRED = Decimal("100")


@dataclass(frozen=True)
class PricingProposal:
    """Everything `cp_policies.propose_recommendation` needs to record
    this as a pending recommendation - the caller (a Celery task, see
    `apps/worker`) just has to pass these straight through, plus a
    `tenant_id`."""

    tool_name: str
    tool_arguments: dict
    type: RecommendationType
    risk_level: RiskLevel
    entity_type: str
    entity_id: uuid.UUID
    title: str
    reason: str
    confidence: Decimal


def build_pricing_proposal(
    *,
    product: Product,
    price: Price,
    offer_id: uuid.UUID,
    competitor_prices: tuple[Decimal, ...] = (),
    current_stock: int | None = None,
    sales_velocity: Decimal | None = None,
    target_margin_rate: Decimal = Decimal("0.30"),
    minimum_margin_rate: Decimal = Decimal("0.10"),
    marketplace_fee_rate: Decimal = Decimal("0"),
    payment_fee_rate: Decimal = Decimal("0"),
    shipping_cost: Decimal = Decimal("0"),
) -> PricingProposal | None:
    """Decides whether this offer's price is worth proposing a change
    for, and if so, builds the proposal - never the change itself. The
    actual price mutation still only ever happens through
    `cp_ai`'s own `update_price` tool, gated behind Phase 8's approval
    workflow like any other HIGH-risk tool call; this function's only
    job is producing that tool call's `tool_name`/`tool_arguments` from
    a deterministic pricing calculation (CLAUDE.md #10 - math is code,
    not an LLM call).

    Returns `None` - nothing to propose - when: `product.cost` is
    `UNKNOWN` (`None`), per CLAUDE.md #9 never guessed; the margin
    targets are mathematically unreachable at any price
    (`PricingInfeasibleError`); or the computed recommendation already
    matches the current price.
    """
    if product.cost is None:
        return None

    vat_rate = (product.vat_rate / _HUNDRED) if product.vat_rate is not None else Decimal("0")

    inputs = PricingInputs(
        cost=product.cost,
        vat_rate=vat_rate,
        marketplace_fee_rate=marketplace_fee_rate,
        payment_fee_rate=payment_fee_rate,
        shipping_cost=shipping_cost,
        target_margin_rate=target_margin_rate,
        minimum_margin_rate=minimum_margin_rate,
        competitor_prices=competitor_prices,
        current_stock=current_stock,
        sales_velocity=sales_velocity,
    )

    try:
        result = compute_price_bounds(inputs)
    except PricingInfeasibleError:
        return None

    if result.recommended_price == price.amount:
        return None

    # Derived from the real tool's own permission, not duplicated here,
    # so the two can never silently drift apart.
    risk_level = RiskLevel(update_price_tool().permission.risk_level.value)

    return PricingProposal(
        tool_name="update_price",
        tool_arguments={"offer_id": str(offer_id), "new_amount": str(result.recommended_price)},
        type=RecommendationType.PRICE_CHANGE,
        risk_level=risk_level,
        entity_type="offer",
        entity_id=offer_id,
        title=(
            f"Change price of {product.sku} from {price.amount} to "
            f"{result.recommended_price} {price.currency}"
        ),
        reason=result.reason,
        confidence=result.confidence,
    )
