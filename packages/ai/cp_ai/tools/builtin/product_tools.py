import uuid
from decimal import Decimal

from cp_domain.offer import Offer, OfferStatus
from cp_domain.price import Price
from cp_domain.product import Product, ProductStatus
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cp_ai.tools.context import ToolContext
from cp_ai.tools.result import ToolResult
from cp_ai.tools.schema import ToolPermission, ToolRiskLevel, ToolSchema


class GetProductArgs(BaseModel):
    sku: str


async def get_product_handler(
    args: GetProductArgs, context: ToolContext, db: AsyncSession
) -> ToolResult:
    product = await db.scalar(
        select(Product).where(Product.tenant_id == context.tenant_id, Product.sku == args.sku)
    )
    if product is None:
        return ToolResult.fail(f"No product with sku {args.sku!r}")

    return ToolResult.ok(
        {
            "id": str(product.id),
            "sku": product.sku,
            "name": product.name,
            "description": product.description,
            "ean": product.ean,
            "status": product.status.value,
        }
    )


def get_product_tool() -> ToolSchema:
    """Read-only lookup by SKU, scoped to the caller's tenant. LOW risk,
    no mutation - never needs approval and never writes an audit log."""
    return ToolSchema(
        name="get_product",
        description="Look up one of this tenant's products by SKU.",
        args_model=GetProductArgs,
        permission=ToolPermission(risk_level=ToolRiskLevel.LOW, mutates=False),
        handler=get_product_handler,
    )


class UpdatePriceArgs(BaseModel):
    offer_id: uuid.UUID
    new_amount: Decimal = Field(gt=0)


async def update_price_handler(
    args: UpdatePriceArgs, context: ToolContext, db: AsyncSession
) -> ToolResult:
    """Updates our system's own record of an offer's price.

    Deliberately does not push the change to the marketplace - per
    CLAUDE.md #2 ("every external mutation must go through a typed
    connector") and #10 ("deterministic business calculations... must
    not be delegated to an LLM"), pushing a price change to a real store
    is the pricing agent's job (Phase 9), built on top of the
    deterministic pricing engine, not something this generic tool does
    on an AI's say-so. This tool only exists to prove the executor's
    approval gate - HIGH risk means `ToolExecutor` never lets this
    function run without Phase 8's approval workflow, whatever the
    connector-push story ends up being.
    """
    price = await db.scalar(
        select(Price).where(Price.tenant_id == context.tenant_id, Price.offer_id == args.offer_id)
    )
    if price is None:
        offer_exists = await db.scalar(
            select(Offer).where(Offer.tenant_id == context.tenant_id, Offer.id == args.offer_id)
        )
        if offer_exists is None:
            return ToolResult.fail(f"No offer {args.offer_id} for this tenant")
        return ToolResult.fail(f"Offer {args.offer_id} has no price set yet")

    before = {"amount": str(price.amount), "currency": price.currency}
    price.amount = args.new_amount
    after = {"amount": str(price.amount), "currency": price.currency}

    return ToolResult.ok(
        after, entity_type="price", entity_id=price.id, before=before, after=after
    )


def update_price_tool() -> ToolSchema:
    """Changes an offer's price in our own domain model. HIGH risk,
    mutates - `ToolExecutor` always routes this through the (Phase 8)
    approval gate rather than running it immediately."""
    return ToolSchema(
        name="update_price",
        description="Change the price of one of this tenant's offers.",
        args_model=UpdatePriceArgs,
        permission=ToolPermission(risk_level=ToolRiskLevel.HIGH, mutates=True),
        handler=update_price_handler,
    )


class UpdateProductContentArgs(BaseModel):
    sku: str
    new_name: str | None = None
    new_description: str | None = None
    new_extra_attributes: dict | None = None


async def update_product_content_handler(
    args: UpdateProductContentArgs, context: ToolContext, db: AsyncSession
) -> ToolResult:
    """Updates a product's listing content: name, description, and the
    free-form `extra_attributes` bag (bullet points, specifications,
    ...). Never touches `cost`/`vat_rate`/`ean`/etc - those are real
    manufacturer data (CLAUDE.md #9), not listing copy an agent gets to
    rewrite."""
    product = await db.scalar(
        select(Product).where(Product.tenant_id == context.tenant_id, Product.sku == args.sku)
    )
    if product is None:
        return ToolResult.fail(f"No product with sku {args.sku!r}")

    before = {
        "name": product.name,
        "description": product.description,
        "extra_attributes": product.extra_attributes,
    }

    if args.new_name is not None:
        product.name = args.new_name
    if args.new_description is not None:
        product.description = args.new_description
    if args.new_extra_attributes is not None:
        product.extra_attributes = args.new_extra_attributes

    after = {
        "name": product.name,
        "description": product.description,
        "extra_attributes": product.extra_attributes,
    }

    return ToolResult.ok(
        after, entity_type="product", entity_id=product.id, before=before, after=after
    )


def update_product_content_tool() -> ToolSchema:
    """Changes a product's listing content (name/description/extra
    attributes). MEDIUM risk, mutates - a wrong price is a financial
    mistake (HIGH); wrong listing copy is a quality/brand mistake, real
    but a notch less severe, so `ToolExecutor` still requires approval
    but this is the first builtin tool to show risk levels aren't just
    LOW or HIGH."""
    return ToolSchema(
        name="update_product_content",
        description="Update a product's name, description, and extra attributes.",
        args_model=UpdateProductContentArgs,
        permission=ToolPermission(risk_level=ToolRiskLevel.MEDIUM, mutates=True),
        handler=update_product_content_handler,
    )


class RequestListingPublishArgs(BaseModel):
    offer_id: uuid.UUID


async def request_listing_publish_handler(
    args: RequestListingPublishArgs, context: ToolContext, db: AsyncSession
) -> ToolResult:
    """Marks a draft listing as approved to go live - `DRAFT` ->
    `PENDING` - but never talks to the marketplace itself.

    This is the first tool whose approval is meant to result in a real
    external mutation (CLAUDE.md #2), and that's exactly why its handler
    stays DB-only: `cp_policies.approve()` calls a tool's handler
    synchronously, in-process, which for every earlier tool (own-DB
    writes only) was fine, but a real network call to a marketplace
    needs retry-safety (CLAUDE.md #11) and must never run inline in an
    HTTP request handler (CLAUDE.md #12/#13) - which is exactly where a
    human clicking "approve" lands. So this handler only flips our own
    state to PENDING; the caller (apps/api's approve route, seeing this
    was a listing_publish recommendation) enqueues the actual
    `worker.publish_listing_to_marketplace` Celery task, which is the
    one that calls the real connector.
    """
    offer = await db.scalar(
        select(Offer).where(Offer.tenant_id == context.tenant_id, Offer.id == args.offer_id)
    )
    if offer is None:
        return ToolResult.fail(f"No offer {args.offer_id} for this tenant")
    if offer.external_id is None:
        return ToolResult.fail(f"Offer {args.offer_id} has no external_id yet - nothing to publish")
    if offer.status is not OfferStatus.DRAFT:
        return ToolResult.fail(
            f"Offer {args.offer_id} is {offer.status.value}, not draft - nothing to publish"
        )

    before = {"status": offer.status.value}
    offer.status = OfferStatus.PENDING
    after = {"status": offer.status.value}

    return ToolResult.ok(after, entity_type="offer", entity_id=offer.id, before=before, after=after)


def request_listing_publish_tool() -> ToolSchema:
    """Approves a draft listing to be published to its marketplace.
    HIGH risk, mutates - same approval gate as `update_price`, but this
    one's approval is the trigger for a real external mutation once the
    worker picks up the PENDING state it leaves behind (see the
    handler's own docstring for why the actual connector call doesn't
    happen here)."""
    return ToolSchema(
        name="request_listing_publish",
        description="Approve a draft marketplace listing to be published live.",
        args_model=RequestListingPublishArgs,
        permission=ToolPermission(risk_level=ToolRiskLevel.HIGH, mutates=True),
        handler=request_listing_publish_handler,
    )


class UpdateProductStatusArgs(BaseModel):
    sku: str
    new_status: ProductStatus


async def update_product_status_handler(
    args: UpdateProductStatusArgs, context: ToolContext, db: AsyncSession
) -> ToolResult:
    """Changes a product's catalog status (draft/active/archived) -
    visibility/lifecycle bookkeeping, never a financial or content
    change. Backs the catalog agent's one actionable fix today: an
    `ACTIVE` product with no offers on any connection (never actually
    listed anywhere) gets proposed for archiving, since an active
    product nobody can buy is a data-hygiene problem, not something to
    guess a fix for."""
    product = await db.scalar(
        select(Product).where(Product.tenant_id == context.tenant_id, Product.sku == args.sku)
    )
    if product is None:
        return ToolResult.fail(f"No product with sku {args.sku!r}")

    before = {"status": product.status.value}
    product.status = args.new_status
    after = {"status": product.status.value}

    return ToolResult.ok(
        after, entity_type="product", entity_id=product.id, before=before, after=after
    )


def update_product_status_tool() -> ToolSchema:
    """Changes a product's catalog status. MEDIUM risk, mutates - a
    wrong archive is annoying but reversible and non-financial, the same
    tier as `update_product_content`."""
    return ToolSchema(
        name="update_product_status",
        description="Change a product's catalog status (draft/active/archived).",
        args_model=UpdateProductStatusArgs,
        permission=ToolPermission(risk_level=ToolRiskLevel.MEDIUM, mutates=True),
        handler=update_product_status_handler,
    )
