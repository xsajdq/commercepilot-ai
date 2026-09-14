import uuid
from decimal import Decimal

from cp_domain.offer import Offer, OfferStatus
from cp_domain.price import Price
from cp_domain.product import Product
from cp_domain.recommendation import RecommendationType, RiskLevel

from cp_ai.agents import build_listing_publish_proposal
from cp_ai.tools.builtin.product_tools import request_listing_publish_tool


def _offer(
    *, external_id: str | None = "ext-1", status: OfferStatus = OfferStatus.DRAFT
) -> Offer:
    return Offer(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        connection_id=uuid.uuid4(),
        variant_id=uuid.uuid4(),
        external_id=external_id,
        status=status,
    )


def _product(*, name: str = "Widget", description: str | None = "A fine widget") -> Product:
    return Product(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        sku="SKU-1",
        name=name,
        description=description,
    )


def _price() -> Price:
    return Price(
        id=uuid.uuid4(), tenant_id=uuid.uuid4(), offer_id=uuid.uuid4(), amount=Decimal("99.99")
    )


def test_builds_a_proposal_when_the_listing_is_ready() -> None:
    offer = _offer()
    product = _product()

    proposal = build_listing_publish_proposal(offer=offer, product=product, price=_price())

    assert proposal is not None
    assert proposal.type is RecommendationType.LISTING_PUBLISH
    assert proposal.risk_level is RiskLevel(
        request_listing_publish_tool().permission.risk_level.value
    )
    assert proposal.entity_type == "offer"
    assert proposal.entity_id == offer.id
    assert proposal.tool_name == "request_listing_publish"
    assert proposal.tool_arguments == {"offer_id": str(offer.id)}
    assert product.sku in proposal.title
    assert proposal.reason


def test_returns_none_without_an_external_id() -> None:
    offer = _offer(external_id=None)

    proposal = build_listing_publish_proposal(offer=offer, product=_product(), price=_price())

    assert proposal is None


def test_returns_none_when_not_draft() -> None:
    offer = _offer(status=OfferStatus.ACTIVE)

    proposal = build_listing_publish_proposal(offer=offer, product=_product(), price=_price())

    assert proposal is None


def test_returns_none_without_a_name() -> None:
    offer = _offer()
    product = _product(name="   ")

    proposal = build_listing_publish_proposal(offer=offer, product=product, price=_price())

    assert proposal is None


def test_returns_none_without_a_description() -> None:
    offer = _offer()
    product = _product(description=None)

    proposal = build_listing_publish_proposal(offer=offer, product=product, price=_price())

    assert proposal is None


def test_returns_none_without_a_price() -> None:
    offer = _offer()

    proposal = build_listing_publish_proposal(offer=offer, product=_product(), price=None)

    assert proposal is None
