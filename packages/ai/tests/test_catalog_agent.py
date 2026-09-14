import uuid
from decimal import Decimal

from cp_domain.offer import Offer, OfferStatus
from cp_domain.price import Price
from cp_domain.product import Product, ProductStatus
from cp_domain.recommendation import RecommendationType, RiskLevel
from cp_domain.stock import Stock
from cp_domain.variant import Variant

from cp_ai.agents.catalog_agent import (
    CatalogIssueType,
    IssueSeverity,
    audit_products,
    build_catalog_fix_proposals,
)
from cp_ai.tools.builtin.product_tools import update_product_status_tool

_TENANT = uuid.uuid4()


def _offer(
    *,
    has_price: bool = True,
    price_amount=Decimal("10.00"),
    has_stock: bool = True,
    quantity: int = 5,
) -> Offer:
    offer = Offer(
        id=uuid.uuid4(),
        tenant_id=_TENANT,
        connection_id=uuid.uuid4(),
        variant_id=uuid.uuid4(),
        status=OfferStatus.ACTIVE,
    )
    offer.price = (
        Price(id=uuid.uuid4(), tenant_id=_TENANT, offer_id=offer.id, amount=price_amount)
        if has_price
        else None
    )
    offer.stock = (
        Stock(id=uuid.uuid4(), tenant_id=_TENANT, offer_id=offer.id, quantity=quantity)
        if has_stock
        else None
    )
    return offer


def _product(
    *,
    sku: str = "SKU-1",
    description: str | None = "A fine product",
    ean: str | None = "1234567890123",
    cost: Decimal | None = None,
    status: ProductStatus = ProductStatus.DRAFT,
    offers: tuple[Offer, ...] = (),
) -> Product:
    product = Product(
        id=uuid.uuid4(),
        tenant_id=_TENANT,
        sku=sku,
        name="Widget",
        description=description,
        ean=ean,
        cost=cost,
        status=status,
    )
    variant = Variant(id=uuid.uuid4(), tenant_id=_TENANT, product_id=product.id, sku=sku)
    variant.offers = list(offers)
    product.variants = [variant]
    return product


class TestAuditProducts:
    def test_counts_every_product_scanned(self) -> None:
        report = audit_products([_product(sku="A"), _product(sku="B"), _product(sku="C")])

        assert report.products_scanned == 3

    def test_flags_missing_description(self) -> None:
        report = audit_products([_product(description=None, offers=(_offer(),))])

        assert any(i.type is CatalogIssueType.MISSING_DESCRIPTION for i in report.issues)

    def test_flags_missing_description_when_blank(self) -> None:
        report = audit_products([_product(description="   ", offers=(_offer(),))])

        assert any(i.type is CatalogIssueType.MISSING_DESCRIPTION for i in report.issues)

    def test_no_missing_description_flag_when_present(self) -> None:
        report = audit_products([_product(description="Real copy", offers=(_offer(),))])

        assert not any(i.type is CatalogIssueType.MISSING_DESCRIPTION for i in report.issues)

    def test_flags_missing_ean(self) -> None:
        report = audit_products([_product(ean=None, offers=(_offer(),))])

        assert any(i.type is CatalogIssueType.MISSING_EAN for i in report.issues)

    def test_flags_missing_price(self) -> None:
        report = audit_products([_product(offers=(_offer(has_price=False),))])

        issue = next(i for i in report.issues if i.type is CatalogIssueType.MISSING_PRICE)
        assert issue.severity is IssueSeverity.HIGH
        assert issue.entity_type == "offer"

    def test_flags_price_below_cost(self) -> None:
        report = audit_products(
            [_product(cost=Decimal("50.00"), offers=(_offer(price_amount=Decimal("30.00")),))]
        )

        assert any(i.type is CatalogIssueType.PRICE_BELOW_COST for i in report.issues)

    def test_no_price_below_cost_flag_when_cost_is_unknown(self) -> None:
        report = audit_products(
            [_product(cost=None, offers=(_offer(price_amount=Decimal("1.00")),))]
        )

        assert not any(i.type is CatalogIssueType.PRICE_BELOW_COST for i in report.issues)

    def test_no_price_below_cost_flag_when_price_is_missing(self) -> None:
        # missing_price already covers this offer - don't double-flag it
        # as also "below" an unknown/incomparable price.
        report = audit_products(
            [_product(cost=Decimal("50.00"), offers=(_offer(has_price=False),))]
        )

        assert not any(i.type is CatalogIssueType.PRICE_BELOW_COST for i in report.issues)

    def test_flags_missing_stock(self) -> None:
        report = audit_products([_product(offers=(_offer(has_stock=False),))])

        assert any(i.type is CatalogIssueType.MISSING_STOCK for i in report.issues)

    def test_flags_out_of_stock(self) -> None:
        report = audit_products([_product(offers=(_offer(quantity=0),))])

        assert any(i.type is CatalogIssueType.OUT_OF_STOCK for i in report.issues)

    def test_no_out_of_stock_flag_when_in_stock(self) -> None:
        report = audit_products([_product(offers=(_offer(quantity=3),))])

        assert not any(i.type is CatalogIssueType.OUT_OF_STOCK for i in report.issues)

    def test_flags_orphan_active_product_with_no_offers(self) -> None:
        report = audit_products([_product(status=ProductStatus.ACTIVE, offers=())])

        issue = next(i for i in report.issues if i.type is CatalogIssueType.ORPHAN_PRODUCT)
        assert issue.severity is IssueSeverity.MEDIUM
        assert issue.entity_type == "product"

    def test_no_orphan_flag_for_draft_product_with_no_offers(self) -> None:
        report = audit_products([_product(status=ProductStatus.DRAFT, offers=())])

        assert not any(i.type is CatalogIssueType.ORPHAN_PRODUCT for i in report.issues)

    def test_no_orphan_flag_for_active_product_with_offers(self) -> None:
        report = audit_products([_product(status=ProductStatus.ACTIVE, offers=(_offer(),))])

        assert not any(i.type is CatalogIssueType.ORPHAN_PRODUCT for i in report.issues)

    def test_clean_product_produces_no_issues(self) -> None:
        report = audit_products([_product(offers=(_offer(),))])

        assert report.issues == []


class TestBuildCatalogFixProposals:
    def test_builds_a_proposal_only_for_orphan_product_issues(self) -> None:
        report = audit_products(
            [
                _product(sku="ORPHAN-1", status=ProductStatus.ACTIVE, offers=()),
                _product(sku="MISSING-PRICE-1", offers=(_offer(has_price=False),)),
            ]
        )

        proposals = build_catalog_fix_proposals(report)

        assert len(proposals) == 1
        proposal = proposals[0]
        assert proposal.tool_name == "update_product_status"
        assert proposal.tool_arguments == {"sku": "ORPHAN-1", "new_status": "archived"}
        assert proposal.type is RecommendationType.CATALOG_FIX
        assert proposal.risk_level is RiskLevel(
            update_product_status_tool().permission.risk_level.value
        )
        assert "ORPHAN-1" in proposal.title

    def test_no_proposals_when_no_actionable_issues(self) -> None:
        report = audit_products([_product(ean=None, offers=(_offer(),))])

        assert build_catalog_fix_proposals(report) == []
