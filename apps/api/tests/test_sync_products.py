from decimal import Decimal

import pytest
from cp_connectors.exceptions import ConnectorError, ConnectorRateLimitError
from cp_connectors.mock import MockConnector
from cp_connectors.types import ConnectorProduct, PriceUpdate, StockUpdate
from cp_domain.connection import Connection
from cp_domain.offer import Offer, OfferStatus
from cp_domain.price import Price
from cp_domain.product import Product
from cp_domain.stock import Stock
from cp_domain.variant import Variant
from cp_sync.products import sync_products
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import make_connection, make_tenant

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _count(db: AsyncSession, model) -> int:
    return await db.scalar(select(func.count()).select_from(model))


async def _sync(db, connection: Connection, connector, **kwargs):
    return await sync_products(
        db, tenant_id=connection.tenant_id, connection=connection, connector=connector, **kwargs
    )


class TestSyncProducts:
    async def test_first_sync_creates_full_graph(self, db_session: AsyncSession) -> None:
        tenant = await make_tenant(db_session)
        connection = await make_connection(db_session, tenant)
        connector = MockConnector()
        await connector.create_product(
            ConnectorProduct(
                sku="SKU-1", name="Running Shoe", price=Decimal("149.00"), stock_quantity=10
            )
        )

        result = await _sync(db_session, connection, connector)

        assert result.products_seen == 1
        assert result.products_upserted == 1
        assert result.failures == []
        assert result.fatal_error is None

        product = await db_session.scalar(select(Product).where(Product.sku == "SKU-1"))
        assert product is not None
        assert product.name == "Running Shoe"

        variant = await db_session.scalar(select(Variant).where(Variant.product_id == product.id))
        assert variant is not None

        offer = await db_session.scalar(select(Offer).where(Offer.variant_id == variant.id))
        assert offer is not None

        price = await db_session.scalar(select(Price).where(Price.offer_id == offer.id))
        assert price.amount == Decimal("149.00")

        stock = await db_session.scalar(select(Stock).where(Stock.offer_id == offer.id))
        assert stock.quantity == 10

    async def test_re_running_sync_is_idempotent(self, db_session: AsyncSession) -> None:
        tenant = await make_tenant(db_session)
        connection = await make_connection(db_session, tenant)
        connector = MockConnector()
        await connector.create_product(
            ConnectorProduct(sku="SKU-2", name="Hat", price=Decimal("29.99"))
        )

        await _sync(db_session, connection, connector)
        await _sync(db_session, connection, connector)

        assert await _count(db_session, Product) == 1
        assert await _count(db_session, Variant) == 1
        assert await _count(db_session, Offer) == 1
        assert await _count(db_session, Price) == 1

    async def test_re_sync_updates_price_and_stock_in_place(self, db_session: AsyncSession) -> None:
        tenant = await make_tenant(db_session)
        connection = await make_connection(db_session, tenant)
        connector = MockConnector()
        created = await connector.create_product(
            ConnectorProduct(sku="SKU-3", name="Bag", price=Decimal("50.00"), stock_quantity=5)
        )
        await _sync(db_session, connection, connector)

        await connector.update_price(
            PriceUpdate(external_id=created.external_id, price=Decimal("45.00"))
        )
        await connector.update_stock(StockUpdate(external_id=created.external_id, quantity=2))
        result = await _sync(db_session, connection, connector)
        assert result.products_upserted == 1

        product = await db_session.scalar(select(Product).where(Product.sku == "SKU-3"))
        variant = await db_session.scalar(select(Variant).where(Variant.product_id == product.id))
        offer = await db_session.scalar(select(Offer).where(Offer.variant_id == variant.id))
        price = await db_session.scalar(select(Price).where(Price.offer_id == offer.id))
        stock = await db_session.scalar(select(Stock).where(Stock.offer_id == offer.id))

        assert price.amount == Decimal("45.00")
        assert stock.quantity == 2
        assert await _count(db_session, Price) == 1
        assert await _count(db_session, Stock) == 1

    async def test_two_connections_same_sku_share_product_but_have_separate_offers(
        self, db_session: AsyncSession
    ) -> None:
        tenant = await make_tenant(db_session)
        connection_a = await make_connection(db_session, tenant, name="Store A")
        connection_b = await make_connection(db_session, tenant, name="Store B")

        connector_a = MockConnector()
        await connector_a.create_product(ConnectorProduct(sku="SHARED-SKU", name="Shared Product"))
        connector_b = MockConnector()
        await connector_b.create_product(ConnectorProduct(sku="SHARED-SKU", name="Shared Product"))

        await _sync(db_session, connection_a, connector_a)
        await _sync(db_session, connection_b, connector_b)

        assert await _count(db_session, Product) == 1
        assert await _count(db_session, Variant) == 1
        assert await _count(db_session, Offer) == 2

    async def test_partial_failure_does_not_block_other_products(
        self, db_session: AsyncSession
    ) -> None:
        tenant = await make_tenant(db_session)
        connection = await make_connection(db_session, tenant)
        connector = MockConnector()
        await connector.create_product(ConnectorProduct(sku="GOOD-1", name="Fine product"))
        # A name exceeding the products.name column's 500-char limit
        # triggers a real DB-level failure at flush/commit time.
        await connector.create_product(ConnectorProduct(sku="BAD-1", name="x" * 600))
        await connector.create_product(ConnectorProduct(sku="GOOD-2", name="Also fine"))

        result = await _sync(db_session, connection, connector)

        assert result.products_seen == 3
        assert result.products_upserted == 2
        assert len(result.failures) == 1
        assert result.failures[0].sku == "BAD-1"
        assert result.fatal_error is None

        assert await db_session.scalar(select(Product).where(Product.sku == "GOOD-1")) is not None
        assert await db_session.scalar(select(Product).where(Product.sku == "GOOD-2")) is not None
        assert await db_session.scalar(select(Product).where(Product.sku == "BAD-1")) is None

    async def test_pagination_across_multiple_pages(self, db_session: AsyncSession) -> None:
        tenant = await make_tenant(db_session)
        connection = await make_connection(db_session, tenant)
        connector = MockConnector()
        for i in range(5):
            await connector.create_product(ConnectorProduct(sku=f"PAGE-{i}", name=f"Product {i}"))

        result = await _sync(db_session, connection, connector, page_limit=2)

        assert result.products_seen == 5
        assert result.products_upserted == 5
        assert await _count(db_session, Product) == 5

    async def test_transient_page_error_is_retried_then_succeeds(
        self, db_session: AsyncSession
    ) -> None:
        tenant = await make_tenant(db_session)
        connection = await make_connection(db_session, tenant)
        connector = MockConnector()
        await connector.create_product(ConnectorProduct(sku="RETRY-1", name="Retried product"))

        real_get_products = connector.get_products
        calls = {"n": 0}

        async def flaky_get_products(*, cursor=None, limit=50):
            calls["n"] += 1
            if calls["n"] == 1:
                raise ConnectorRateLimitError("slow down", retry_after_seconds=0.001)
            return await real_get_products(cursor=cursor, limit=limit)

        connector.get_products = flaky_get_products

        result = await _sync(db_session, connection, connector, base_delay=0.001)

        assert result.products_upserted == 1
        assert result.fatal_error is None
        assert calls["n"] == 2

    async def test_exhausted_retries_set_fatal_error_without_losing_prior_data(
        self, db_session: AsyncSession
    ) -> None:
        tenant = await make_tenant(db_session)
        connection = await make_connection(db_session, tenant)

        # A prior successful sync already put a product in place.
        good_connector = MockConnector()
        await good_connector.create_product(
            ConnectorProduct(sku="EXISTING", name="Already synced")
        )
        await _sync(db_session, connection, good_connector)
        assert await _count(db_session, Product) == 1

        async def always_fails(*, cursor=None, limit=50):
            raise ConnectorError("platform is down")

        broken_connector = MockConnector()
        broken_connector.get_products = always_fails

        result = await _sync(
            db_session, connection, broken_connector, max_attempts=2, base_delay=0.001
        )

        assert result.fatal_error is not None
        assert result.products_seen == 0

        # The product from the earlier successful sync is untouched.
        assert await _count(db_session, Product) == 1

        await db_session.refresh(connection)
        assert connection.last_error == result.fatal_error

    async def test_successful_sync_clears_previous_error_and_sets_last_synced_at(
        self, db_session: AsyncSession
    ) -> None:
        tenant = await make_tenant(db_session)
        connection = await make_connection(db_session, tenant)
        connection.last_error = "previous failure"
        await db_session.commit()

        connector = MockConnector()
        await connector.create_product(ConnectorProduct(sku="OK-1", name="Fine"))

        await _sync(db_session, connection, connector)

        await db_session.refresh(connection)
        assert connection.last_error is None
        assert connection.last_synced_at is not None


class TestOfferStatusMapping:
    """Phase 11: the Listing Agent's readiness check depends on
    Offer.status reflecting marketplace reality, so a synced product's
    connector-vocabulary status ("publish", "inactive", ...) must land
    as the matching OfferStatus, not silently stay at the column
    default forever."""

    async def test_new_offer_gets_mapped_status_from_connector(
        self, db_session: AsyncSession
    ) -> None:
        tenant = await make_tenant(db_session)
        connection = await make_connection(db_session, tenant)
        connector = MockConnector()
        await connector.create_product(
            ConnectorProduct(sku="ACTIVE-1", name="Live listing", status="active")
        )

        await _sync(db_session, connection, connector)

        offer = await db_session.scalar(select(Offer))
        assert offer.status is OfferStatus.ACTIVE

    async def test_woocommerce_publish_status_maps_to_active(
        self, db_session: AsyncSession
    ) -> None:
        tenant = await make_tenant(db_session)
        connection = await make_connection(db_session, tenant)
        connector = MockConnector()
        await connector.create_product(
            ConnectorProduct(sku="WOO-1", name="Published on Woo", status="publish")
        )

        await _sync(db_session, connection, connector)

        offer = await db_session.scalar(select(Offer))
        assert offer.status is OfferStatus.ACTIVE

    async def test_allegro_inactive_status_maps_to_draft(self, db_session: AsyncSession) -> None:
        tenant = await make_tenant(db_session)
        connection = await make_connection(db_session, tenant)
        connector = MockConnector()
        await connector.create_product(
            ConnectorProduct(sku="ALG-1", name="Allegro draft", status="inactive")
        )

        await _sync(db_session, connection, connector)

        offer = await db_session.scalar(select(Offer))
        assert offer.status is OfferStatus.DRAFT

    async def test_re_sync_updates_status_when_it_changes(self, db_session: AsyncSession) -> None:
        tenant = await make_tenant(db_session)
        connection = await make_connection(db_session, tenant)
        connector = MockConnector()
        created = await connector.create_product(
            ConnectorProduct(sku="ALG-2", name="Goes live later", status="inactive")
        )

        await _sync(db_session, connection, connector)
        offer = await db_session.scalar(select(Offer))
        assert offer.status is OfferStatus.DRAFT

        await connector.publish_offer(created.external_id)
        await _sync(db_session, connection, connector)

        await db_session.refresh(offer)
        assert offer.status is OfferStatus.ACTIVE

    async def test_unrecognized_status_leaves_offer_status_unchanged(
        self, db_session: AsyncSession
    ) -> None:
        tenant = await make_tenant(db_session)
        connection = await make_connection(db_session, tenant)
        connector = MockConnector()
        created = await connector.create_product(
            ConnectorProduct(sku="WEIRD-1", name="Odd status", status="active")
        )

        await _sync(db_session, connection, connector)
        offer = await db_session.scalar(select(Offer))
        assert offer.status is OfferStatus.ACTIVE

        connector._products[created.external_id] = connector._products[
            created.external_id
        ].model_copy(update={"status": "some-unknown-platform-status"})
        await _sync(db_session, connection, connector)

        await db_session.refresh(offer)
        assert offer.status is OfferStatus.ACTIVE


class TestSkulessProducts:
    """WooCommerce (and other platforms) allow a product with no SKU at
    all - real catalogs routinely have some. Before the fix, every such
    product fell back to sku="" and collapsed onto the same Product/
    Variant row on upsert (matched by (tenant_id, sku)) - each later
    product silently overwrote the one before it, so a store with N
    skuless products among its catalog only ever ended up with 1 row for
    all of them combined."""

    async def test_multiple_skuless_products_get_distinct_rows(
        self, db_session: AsyncSession
    ) -> None:
        tenant = await make_tenant(db_session)
        connection = await make_connection(db_session, tenant)
        connector = MockConnector()
        await connector.create_product(ConnectorProduct(sku="", name="First product"))
        await connector.create_product(ConnectorProduct(sku="", name="Second product"))
        await connector.create_product(ConnectorProduct(sku="", name="Third product"))

        result = await _sync(db_session, connection, connector)

        assert result.products_seen == 3
        assert result.products_upserted == 3
        assert await _count(db_session, Product) == 3
        assert await _count(db_session, Variant) == 3
        assert await _count(db_session, Offer) == 3

        names = {
            p.name for p in (await db_session.scalars(select(Product))).all()
        }
        assert names == {"First product", "Second product", "Third product"}

    async def test_resyncing_a_skuless_product_updates_the_same_row(
        self, db_session: AsyncSession
    ) -> None:
        tenant = await make_tenant(db_session)
        connection = await make_connection(db_session, tenant)
        connector = MockConnector()
        created = await connector.create_product(
            ConnectorProduct(sku="", name="Original name", price=Decimal("10.00"))
        )

        await _sync(db_session, connection, connector)
        await connector.update_product(
            created.external_id,
            ConnectorProduct(sku="", name="Renamed", price=Decimal("10.00")),
        )
        await _sync(db_session, connection, connector)

        assert await _count(db_session, Product) == 1
        product = await db_session.scalar(select(Product))
        assert product.name == "Renamed"

    async def test_skuless_products_on_different_connections_stay_distinct(
        self, db_session: AsyncSession
    ) -> None:
        tenant = await make_tenant(db_session)
        connection_a = await make_connection(db_session, tenant, name="Store A")
        connection_b = await make_connection(db_session, tenant, name="Store B")

        # Same platform-assigned external_id on two different stores -
        # a real, plausible collision (each WooCommerce install numbers
        # its own products starting from 1) that the synthetic sku must
        # not conflate.
        connector_a = MockConnector()
        await connector_a.create_product(
            ConnectorProduct(sku="", name="Store A's product", external_id="1")
        )
        connector_b = MockConnector()
        await connector_b.create_product(
            ConnectorProduct(sku="", name="Store B's product", external_id="1")
        )

        await _sync(db_session, connection_a, connector_a)
        await _sync(db_session, connection_b, connector_b)

        assert await _count(db_session, Product) == 2
        names = {
            p.name for p in (await db_session.scalars(select(Product))).all()
        }
        assert names == {"Store A's product", "Store B's product"}

    async def test_skuless_product_gets_a_visibly_synthetic_sku(
        self, db_session: AsyncSession
    ) -> None:
        tenant = await make_tenant(db_session)
        connection = await make_connection(db_session, tenant)
        connector = MockConnector()
        await connector.create_product(ConnectorProduct(sku="", name="No sku here"))

        await _sync(db_session, connection, connector)

        product = await db_session.scalar(select(Product))
        assert product.sku.startswith("noSKU-")
