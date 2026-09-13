import uuid
from decimal import Decimal

from cp_domain.offer import Offer
from cp_domain.price import Price
from cp_domain.product import Product
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
