import uuid
from decimal import Decimal

from cp_domain.price import Price
from cp_domain.product import Product
from cp_domain.recommendation import RecommendationType, RiskLevel
from cp_pricing import PricingInputs, compute_price_bounds

from cp_ai.agents import build_pricing_proposal
from cp_ai.tools.builtin.product_tools import update_price_tool


def _product(*, cost: Decimal | None = Decimal("60"), vat_rate: Decimal | None = None) -> Product:
    return Product(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        sku="SKU-1",
        name="Widget",
        cost=cost,
        vat_rate=vat_rate,
    )


def _price(amount: Decimal, currency: str = "PLN") -> Price:
    return Price(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        offer_id=uuid.uuid4(),
        amount=amount,
        currency=currency,
    )


def test_returns_none_when_cost_is_unknown() -> None:
    product = _product(cost=None)
    price = _price(Decimal("50.00"))

    proposal = build_pricing_proposal(product=product, price=price, offer_id=uuid.uuid4())

    assert proposal is None


def test_builds_a_proposal_when_current_price_differs_from_recommendation() -> None:
    product = _product(cost=Decimal("60"))
    price = _price(Decimal("70.00"))
    offer_id = uuid.uuid4()

    proposal = build_pricing_proposal(product=product, price=price, offer_id=offer_id)

    assert proposal is not None
    assert proposal.type is RecommendationType.PRICE_CHANGE
    assert proposal.risk_level is RiskLevel(update_price_tool().permission.risk_level.value)
    assert proposal.entity_type == "offer"
    assert proposal.entity_id == offer_id
    assert proposal.tool_name == "update_price"
    assert proposal.tool_arguments["offer_id"] == str(offer_id)
    assert Decimal(proposal.tool_arguments["new_amount"]) != price.amount
    assert product.sku in proposal.title
    assert proposal.reason
    assert Decimal("0.1") <= proposal.confidence <= Decimal("1.0")


def test_returns_none_when_already_at_the_recommended_price() -> None:
    product = _product(cost=Decimal("60"))
    inputs = PricingInputs(cost=Decimal("60"))
    already_recommended = compute_price_bounds(inputs).recommended_price
    price = _price(already_recommended)

    proposal = build_pricing_proposal(product=product, price=price, offer_id=uuid.uuid4())

    assert proposal is None


def test_returns_none_when_the_margin_target_is_infeasible() -> None:
    product = _product(cost=Decimal("10"))
    price = _price(Decimal("50.00"))

    proposal = build_pricing_proposal(
        product=product,
        price=price,
        offer_id=uuid.uuid4(),
        marketplace_fee_rate=Decimal("0.85"),
    )

    assert proposal is None


def test_product_vat_rate_percentage_is_converted_to_a_fraction() -> None:
    product = _product(cost=Decimal("60"), vat_rate=Decimal("23"))
    price = _price(Decimal("999.00"))

    proposal = build_pricing_proposal(product=product, price=price, offer_id=uuid.uuid4())

    direct_result = compute_price_bounds(
        PricingInputs(cost=Decimal("60"), vat_rate=Decimal("0.23"))
    )

    assert proposal is not None
    assert Decimal(proposal.tool_arguments["new_amount"]) == direct_result.recommended_price
