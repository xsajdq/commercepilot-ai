import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from cp_connectors.base import CommerceConnector
from cp_connectors.types import ConnectorProduct
from cp_domain.connection import Connection
from cp_domain.offer import Offer, OfferStatus
from cp_domain.price import Price
from cp_domain.product import Product
from cp_domain.stock import Stock
from cp_domain.variant import Variant
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cp_sync.retry import retry_with_backoff

# Each connector reports status in its own platform's vocabulary (see
# each connector's own tests - WooCommerce: "publish"/"draft"/"pending"/
# "private"; Allegro: "active"/"inactive"; MockConnector/anything else:
# already "draft"/"active"/... per ConnectorProduct's own default).
# Mapping platform vocabulary to our domain's OfferStatus is exactly this
# module's job (it already maps sku/name/price/stock the same way) - an
# unrecognized string is left alone rather than guessed, so a newly
# supported platform's own status wording never gets silently misread.
_STATUS_MAP: dict[str, OfferStatus] = {
    "draft": OfferStatus.DRAFT,
    "pending": OfferStatus.PENDING,
    "active": OfferStatus.ACTIVE,
    "publish": OfferStatus.ACTIVE,
    "private": OfferStatus.PAUSED,
    "paused": OfferStatus.PAUSED,
    "inactive": OfferStatus.DRAFT,
    "error": OfferStatus.ERROR,
}


def _mapped_offer_status(raw_status: str) -> OfferStatus | None:
    return _STATUS_MAP.get(raw_status.lower())


@dataclass
class SyncFailure:
    sku: str
    error: str


@dataclass
class SyncResult:
    products_seen: int = 0
    products_upserted: int = 0
    failures: list[SyncFailure] = field(default_factory=list)
    fatal_error: str | None = None

    def to_dict(self) -> dict:
        return {
            "products_seen": self.products_seen,
            "products_upserted": self.products_upserted,
            "failures": [{"sku": f.sku, "error": f.error} for f in self.failures],
            "fatal_error": self.fatal_error,
        }


async def sync_products(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    connection: Connection,
    connector: CommerceConnector,
    page_limit: int = 50,
    max_attempts: int = 5,
    base_delay: float = 1.0,
) -> SyncResult:
    """Pulls every product from `connector` and upserts it into the
    domain model, scoped to `tenant_id`/`connection`.

    Idempotent: a `Product` is matched by (tenant_id, sku), its `Variant`
    the same way, and its `Offer` by (connection_id, variant_id) - all
    already-unique columns in the schema - so re-running this never
    creates duplicates, only updates. `Price`/`Stock` are matched by
    `offer_id`.

    A single product's mapping/DB error is recorded in the result and
    does not stop the rest of the page or subsequent pages from being
    processed (CLAUDE.md: partial failures must not abort a whole sync).
    Transient failures fetching a page (rate limits, network errors) are
    retried with backoff (see `cp_sync.retry`); a page fetch that
    exhausts its retries stops the sync early with `fatal_error` set,
    but every product already committed from earlier pages stays
    committed.

    Only product-level fields are synced (sku, name, description, ean,
    price, stock, offer status) - category/brand resolution across
    platforms isn't modeled yet (see the package README for why) and
    variants are 1:1 with products until a connector actually exposes
    real variations (WooCommerce/Allegro don't yet, see their
    docstrings).
    """
    result = SyncResult()
    cursor: str | None = None

    while True:
        try:
            page, cursor = await retry_with_backoff(
                lambda c=cursor: connector.get_products(cursor=c, limit=page_limit),
                max_attempts=max_attempts,
                base_delay=base_delay,
            )
        except Exception as exc:  # noqa: BLE001 - any exhausted/non-retryable error ends the sync
            result.fatal_error = str(exc)
            break

        for connector_product in page:
            result.products_seen += 1
            try:
                # A SAVEPOINT, not a full session rollback: on failure this
                # unwinds only this item's flushed statements, leaving the
                # session's transaction (and any earlier, already-committed
                # products) untouched for the next iteration.
                async with db.begin_nested():
                    await _upsert_product(
                        db, tenant_id=tenant_id, connection=connection, product=connector_product
                    )
                await db.commit()
                result.products_upserted += 1
            except Exception as exc:  # noqa: BLE001 - one bad item must not abort the batch
                result.failures.append(SyncFailure(sku=connector_product.sku, error=str(exc)))

        if cursor is None:
            break

    connection.last_synced_at = datetime.now(UTC)
    connection.last_error = result.fatal_error
    await db.commit()

    return result


async def _upsert_product(
    db: AsyncSession, *, tenant_id: uuid.UUID, connection: Connection, product: ConnectorProduct
) -> None:
    domain_product = await db.scalar(
        select(Product).where(Product.tenant_id == tenant_id, Product.sku == product.sku)
    )
    if domain_product is None:
        domain_product = Product(tenant_id=tenant_id, sku=product.sku, name=product.name)
        db.add(domain_product)
        await db.flush()
    else:
        domain_product.name = product.name
        if product.description is not None:
            domain_product.description = product.description
        if product.ean is not None:
            domain_product.ean = product.ean

    variant = await db.scalar(
        select(Variant).where(Variant.tenant_id == tenant_id, Variant.sku == product.sku)
    )
    if variant is None:
        variant = Variant(tenant_id=tenant_id, product_id=domain_product.id, sku=product.sku)
        db.add(variant)
        await db.flush()

    offer = await db.scalar(
        select(Offer).where(Offer.connection_id == connection.id, Offer.variant_id == variant.id)
    )
    mapped_status = _mapped_offer_status(product.status)
    if offer is None:
        offer = Offer(
            tenant_id=tenant_id,
            connection_id=connection.id,
            variant_id=variant.id,
            external_id=product.external_id,
            status=mapped_status or OfferStatus.DRAFT,
        )
        db.add(offer)
        await db.flush()
    else:
        offer.external_id = product.external_id
        if mapped_status is not None:
            offer.status = mapped_status

    if product.price is not None:
        price = await db.scalar(select(Price).where(Price.offer_id == offer.id))
        if price is None:
            db.add(
                Price(
                    tenant_id=tenant_id,
                    offer_id=offer.id,
                    amount=product.price,
                    currency=product.currency,
                )
            )
        else:
            price.amount = product.price
            price.currency = product.currency

    if product.stock_quantity is not None:
        stock = await db.scalar(select(Stock).where(Stock.offer_id == offer.id))
        if stock is None:
            db.add(Stock(tenant_id=tenant_id, offer_id=offer.id, quantity=product.stock_quantity))
        else:
            stock.quantity = product.stock_quantity
