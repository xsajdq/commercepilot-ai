import enum
import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field

from cp_domain.product import Product, ProductStatus
from cp_domain.recommendation import RecommendationType, RiskLevel

from cp_ai.tools.builtin.product_tools import update_product_status_tool


class CatalogIssueType(str, enum.Enum):
    MISSING_PRICE = "missing_price"
    MISSING_STOCK = "missing_stock"
    OUT_OF_STOCK = "out_of_stock"
    MISSING_DESCRIPTION = "missing_description"
    MISSING_EAN = "missing_ean"
    PRICE_BELOW_COST = "price_below_cost"
    ORPHAN_PRODUCT = "orphan_product"


class IssueSeverity(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True)
class CatalogIssue:
    """One problem found in the catalog. Not every issue becomes a
    `Recommendation` - most of these have no safe, non-guessed fix (a
    missing price or EAN can't be invented per CLAUDE.md #9, and a wrong
    price is the pricing agent's job, not this one's to re-derive) and
    exist purely to be surfaced to a human, e.g. on a future dashboard
    (Phase 16). Only `ORPHAN_PRODUCT` currently maps to an actionable,
    unambiguous fix - see `build_catalog_fix_proposals`."""

    type: CatalogIssueType
    severity: IssueSeverity
    entity_type: str
    entity_id: uuid.UUID
    sku: str
    message: str


@dataclass(frozen=True)
class CatalogAuditReport:
    products_scanned: int
    issues: list[CatalogIssue] = field(default_factory=list)


def audit_products(products: Iterable[Product]) -> CatalogAuditReport:
    """Deterministic catalog health checklist - no `AIProvider` call,
    same reasoning as the pricing and listing agents: "is this product
    missing X" is a checklist against data already on hand, not a
    creative judgement CLAUDE.md #10 would want kept out of an LLM's
    hands anyway.

    Expects each `Product` to already have `variants` (and each
    variant's `offers`, each offer's `price`/`stock`) eager-loaded by the
    caller - this function does no I/O of its own, matching every other
    agent in this package.
    """
    issues: list[CatalogIssue] = []
    products_scanned = 0

    for product in products:
        products_scanned += 1
        offers = [offer for variant in product.variants for offer in variant.offers]

        if not product.description or not product.description.strip():
            issues.append(
                CatalogIssue(
                    type=CatalogIssueType.MISSING_DESCRIPTION,
                    severity=IssueSeverity.LOW,
                    entity_type="product",
                    entity_id=product.id,
                    sku=product.sku,
                    message=f"{product.sku} has no description",
                )
            )

        if not product.ean:
            issues.append(
                CatalogIssue(
                    type=CatalogIssueType.MISSING_EAN,
                    severity=IssueSeverity.LOW,
                    entity_type="product",
                    entity_id=product.id,
                    sku=product.sku,
                    message=f"{product.sku} has no EAN",
                )
            )

        if product.status is ProductStatus.ACTIVE and not offers:
            issues.append(
                CatalogIssue(
                    type=CatalogIssueType.ORPHAN_PRODUCT,
                    severity=IssueSeverity.MEDIUM,
                    entity_type="product",
                    entity_id=product.id,
                    sku=product.sku,
                    message=f"{product.sku} is active but has no offers on any connection",
                )
            )

        for offer in offers:
            if offer.price is None:
                issues.append(
                    CatalogIssue(
                        type=CatalogIssueType.MISSING_PRICE,
                        severity=IssueSeverity.HIGH,
                        entity_type="offer",
                        entity_id=offer.id,
                        sku=product.sku,
                        message=f"{product.sku} has an offer with no price set",
                    )
                )
            elif product.cost is not None and offer.price.amount < product.cost:
                issues.append(
                    CatalogIssue(
                        type=CatalogIssueType.PRICE_BELOW_COST,
                        severity=IssueSeverity.HIGH,
                        entity_type="offer",
                        entity_id=offer.id,
                        sku=product.sku,
                        message=(
                            f"{product.sku} is priced below cost "
                            f"({offer.price.amount} < {product.cost})"
                        ),
                    )
                )

            if offer.stock is None:
                issues.append(
                    CatalogIssue(
                        type=CatalogIssueType.MISSING_STOCK,
                        severity=IssueSeverity.LOW,
                        entity_type="offer",
                        entity_id=offer.id,
                        sku=product.sku,
                        message=f"{product.sku} has an offer with no stock record",
                    )
                )
            elif offer.stock.quantity <= 0:
                issues.append(
                    CatalogIssue(
                        type=CatalogIssueType.OUT_OF_STOCK,
                        severity=IssueSeverity.MEDIUM,
                        entity_type="offer",
                        entity_id=offer.id,
                        sku=product.sku,
                        message=f"{product.sku} is out of stock",
                    )
                )

    return CatalogAuditReport(products_scanned=products_scanned, issues=issues)


@dataclass(frozen=True)
class CatalogFixProposal:
    """Everything `cp_policies.propose_recommendation` needs to record
    this as a pending recommendation - mirrors `PricingProposal`/
    `ListingPublishProposal`."""

    tool_name: str
    tool_arguments: dict
    type: RecommendationType
    risk_level: RiskLevel
    entity_type: str
    entity_id: uuid.UUID
    title: str
    reason: str


def build_catalog_fix_proposals(report: CatalogAuditReport) -> list[CatalogFixProposal]:
    """Turns the actionable subset of a `CatalogAuditReport` into
    concrete tool-call proposals - today, only `ORPHAN_PRODUCT`
    (archiving a product nobody can actually buy). Every other issue
    type has no safe automated fix (a missing price/EAN can't be
    invented; a wrong price belongs to the pricing agent) and is left as
    a plain finding for a human to act on manually.
    """
    proposals: list[CatalogFixProposal] = []
    risk_level = RiskLevel(update_product_status_tool().permission.risk_level.value)

    for issue in report.issues:
        if issue.type is not CatalogIssueType.ORPHAN_PRODUCT:
            continue
        proposals.append(
            CatalogFixProposal(
                tool_name="update_product_status",
                tool_arguments={"sku": issue.sku, "new_status": "archived"},
                type=RecommendationType.CATALOG_FIX,
                risk_level=risk_level,
                entity_type=issue.entity_type,
                entity_id=issue.entity_id,
                title=f"Archive orphaned product {issue.sku}",
                reason=issue.message,
            )
        )

    return proposals
