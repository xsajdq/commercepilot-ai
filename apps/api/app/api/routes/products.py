import uuid
from decimal import Decimal
from typing import Annotated

from cp_domain.connection import Connection
from cp_domain.offer import Offer, OfferStatus
from cp_domain.price import Price
from cp_domain.product import Product, ProductStatus
from cp_domain.stock import Stock
from cp_domain.variant import Variant
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.dependencies import get_current_membership
from app.core.celery_client import get_celery_client
from app.db.base import get_db
from app.db.models.membership import Membership

router = APIRouter(prefix="/products", tags=["products"])
offers_router = APIRouter(prefix="/offers", tags=["products"])


class CreateProductRequest(BaseModel):
    connection_id: uuid.UUID
    sku: str
    name: str
    cost: Decimal | None = None
    vat_rate: Decimal | None = None
    price_amount: Decimal
    currency: str = "PLN"
    stock_quantity: int | None = None


class OfferOut(BaseModel):
    id: uuid.UUID
    connection_id: uuid.UUID
    status: OfferStatus
    price_amount: Decimal | None = None
    currency: str | None = None
    stock_quantity: int | None = None


class ProductOut(BaseModel):
    id: uuid.UUID
    sku: str
    name: str
    description: str | None
    cost: Decimal | None
    status: ProductStatus
    offers: list[OfferOut]

    model_config = {"from_attributes": True}


class TaskTriggeredResponse(BaseModel):
    task_id: str


def _to_product_out(product: Product) -> ProductOut:
    offers = [
        OfferOut(
            id=offer.id,
            connection_id=offer.connection_id,
            status=offer.status,
            price_amount=offer.price.amount if offer.price else None,
            currency=offer.price.currency if offer.price else None,
            stock_quantity=offer.stock.quantity if offer.stock else None,
        )
        for variant in product.variants
        for offer in variant.offers
    ]
    return ProductOut(
        id=product.id,
        sku=product.sku,
        name=product.name,
        description=product.description,
        cost=product.cost,
        status=product.status,
        offers=offers,
    )


@router.get("", response_model=list[ProductOut])
async def list_products(
    db: Annotated[AsyncSession, Depends(get_db)],
    membership: Annotated[Membership, Depends(get_current_membership)],
) -> list[ProductOut]:
    result = await db.scalars(
        select(Product)
        .where(Product.tenant_id == membership.tenant_id)
        .options(
            selectinload(Product.variants)
            .selectinload(Variant.offers)
            .selectinload(Offer.price),
            selectinload(Product.variants).selectinload(Variant.offers).selectinload(Offer.stock),
        )
        .order_by(Product.created_at.desc())
        .limit(200)
    )
    return [_to_product_out(p) for p in result]


@router.post("", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
async def create_product(
    payload: CreateProductRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    membership: Annotated[Membership, Depends(get_current_membership)],
) -> ProductOut:
    connection = await db.scalar(
        select(Connection).where(
            Connection.id == payload.connection_id, Connection.tenant_id == membership.tenant_id
        )
    )
    if connection is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found")

    product = Product(
        tenant_id=membership.tenant_id,
        sku=payload.sku,
        name=payload.name,
        cost=payload.cost,
        vat_rate=payload.vat_rate,
    )
    db.add(product)
    try:
        await db.flush()
    except Exception as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A product with this SKU already exists",
        ) from exc

    variant = Variant(tenant_id=membership.tenant_id, product_id=product.id, sku=payload.sku)
    db.add(variant)
    await db.flush()

    offer = Offer(
        tenant_id=membership.tenant_id, connection_id=connection.id, variant_id=variant.id
    )
    db.add(offer)
    await db.flush()

    db.add(
        Price(
            tenant_id=membership.tenant_id,
            offer_id=offer.id,
            amount=payload.price_amount,
            currency=payload.currency,
        )
    )
    if payload.stock_quantity is not None:
        db.add(
            Stock(
                tenant_id=membership.tenant_id, offer_id=offer.id, quantity=payload.stock_quantity
            )
        )
    await db.commit()

    reloaded = await db.scalar(
        select(Product)
        .where(Product.id == product.id)
        .options(
            selectinload(Product.variants)
            .selectinload(Variant.offers)
            .selectinload(Offer.price),
            selectinload(Product.variants).selectinload(Variant.offers).selectinload(Offer.stock),
        )
    )
    return _to_product_out(reloaded)


@router.post(
    "/{product_id}/generate-content-recommendation", response_model=TaskTriggeredResponse
)
async def generate_content_recommendation(
    product_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    membership: Annotated[Membership, Depends(get_current_membership)],
) -> TaskTriggeredResponse:
    product = await db.scalar(
        select(Product).where(
            Product.id == product_id, Product.tenant_id == membership.tenant_id
        )
    )
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    result = get_celery_client().send_task(
        "worker.generate_product_content_recommendation",
        args=[str(membership.tenant_id), str(product.id)],
    )
    return TaskTriggeredResponse(task_id=result.id)


@offers_router.post(
    "/{offer_id}/generate-pricing-recommendation", response_model=TaskTriggeredResponse
)
async def generate_pricing_recommendation(
    offer_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    membership: Annotated[Membership, Depends(get_current_membership)],
) -> TaskTriggeredResponse:
    offer = await db.scalar(
        select(Offer).where(Offer.id == offer_id, Offer.tenant_id == membership.tenant_id)
    )
    if offer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Offer not found")

    result = get_celery_client().send_task(
        "worker.generate_price_recommendation", args=[str(membership.tenant_id), str(offer.id)]
    )
    return TaskTriggeredResponse(task_id=result.id)


@offers_router.post(
    "/{offer_id}/generate-listing-publish-recommendation", response_model=TaskTriggeredResponse
)
async def generate_listing_publish_recommendation(
    offer_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    membership: Annotated[Membership, Depends(get_current_membership)],
) -> TaskTriggeredResponse:
    offer = await db.scalar(
        select(Offer).where(Offer.id == offer_id, Offer.tenant_id == membership.tenant_id)
    )
    if offer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Offer not found")

    result = get_celery_client().send_task(
        "worker.generate_listing_publish_recommendation",
        args=[str(membership.tenant_id), str(offer.id)],
    )
    return TaskTriggeredResponse(task_id=result.id)
