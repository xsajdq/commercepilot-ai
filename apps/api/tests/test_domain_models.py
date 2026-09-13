import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from cp_domain.approval import Approval, ApprovalStatus
from cp_domain.audit_event import ActorType, AuditEvent, AuditResult
from cp_domain.brand import Brand
from cp_domain.category import Category
from cp_domain.offer import Offer, OfferStatus
from cp_domain.order import Order, OrderItem, OrderStatus
from cp_domain.price import Price
from cp_domain.product import Product, ProductStatus
from cp_domain.recommendation import (
    Recommendation,
    RecommendationStatus,
    RecommendationType,
    RiskLevel,
)
from cp_domain.review import Review
from cp_domain.stock import Stock
from cp_domain.variant import Variant
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from tests.conftest import make_connection as _make_connection
from tests.conftest import make_tenant as _make_tenant

pytestmark = pytest.mark.asyncio(loop_scope="session")


class TestProductCatalogGraph:
    async def test_full_graph_persists_and_relates_correctly(
        self, db_session: AsyncSession
    ) -> None:
        tenant = await _make_tenant(db_session)
        brand = Brand(tenant_id=tenant.id, name="Acme")
        category = Category(tenant_id=tenant.id, name="Shoes", slug="shoes")
        db_session.add_all([brand, category])
        await db_session.flush()

        product = Product(
            tenant_id=tenant.id,
            sku="PROD-1",
            name="Running Shoe",
            brand_id=brand.id,
            category_id=category.id,
            status=ProductStatus.ACTIVE,
        )
        db_session.add(product)
        await db_session.flush()

        variant = Variant(tenant_id=tenant.id, product_id=product.id, sku="PROD-1-RED-42")
        db_session.add(variant)
        await db_session.flush()

        connection = await _make_connection(db_session, tenant)
        offer = Offer(
            tenant_id=tenant.id,
            connection_id=connection.id,
            variant_id=variant.id,
            status=OfferStatus.ACTIVE,
        )
        db_session.add(offer)
        await db_session.flush()

        db_session.add(Price(tenant_id=tenant.id, offer_id=offer.id, amount=Decimal("149.00")))
        db_session.add(Stock(tenant_id=tenant.id, offer_id=offer.id, quantity=10))
        await db_session.commit()

        loaded = await db_session.scalar(
            select(Product)
            .where(Product.id == product.id)
            .options(
                selectinload(Product.variants)
                .selectinload(Variant.offers)
                .selectinload(Offer.price),
                selectinload(Product.variants).selectinload(Variant.offers).selectinload(Offer.stock),
            )
        )
        assert loaded is not None
        assert len(loaded.variants) == 1
        [loaded_variant] = loaded.variants
        assert len(loaded_variant.offers) == 1
        [loaded_offer] = loaded_variant.offers
        assert loaded_offer.price.amount == Decimal("149.00")
        assert loaded_offer.stock.quantity == 10

    async def test_sku_unique_per_tenant_not_globally(self, db_session: AsyncSession) -> None:
        tenant_a = await _make_tenant(db_session, "Tenant A")
        tenant_b = await _make_tenant(db_session, "Tenant B")

        db_session.add(Product(tenant_id=tenant_a.id, sku="SHARED-SKU", name="A's product"))
        await db_session.commit()

        # Same SKU, different tenant: must succeed - the constraint is
        # scoped, not global.
        db_session.add(Product(tenant_id=tenant_b.id, sku="SHARED-SKU", name="B's product"))
        await db_session.commit()

        # Same SKU, same tenant: must fail.
        db_session.add(Product(tenant_id=tenant_a.id, sku="SHARED-SKU", name="Duplicate"))
        with pytest.raises(IntegrityError):
            await db_session.commit()
        await db_session.rollback()

    async def test_deleting_product_cascades_to_variants(self, db_session: AsyncSession) -> None:
        tenant = await _make_tenant(db_session)
        product = Product(tenant_id=tenant.id, sku="CASCADE-1", name="Doomed product")
        db_session.add(product)
        await db_session.flush()
        variant = Variant(tenant_id=tenant.id, product_id=product.id, sku="CASCADE-1-V1")
        db_session.add(variant)
        await db_session.commit()
        variant_id = variant.id

        await db_session.delete(product)
        await db_session.commit()

        assert await db_session.get(Variant, variant_id) is None

    async def test_category_parent_deletion_sets_child_null_not_cascade(
        self, db_session: AsyncSession
    ) -> None:
        tenant = await _make_tenant(db_session)
        parent = Category(tenant_id=tenant.id, name="Footwear", slug="footwear")
        db_session.add(parent)
        await db_session.flush()
        child = Category(tenant_id=tenant.id, name="Boots", slug="boots", parent_id=parent.id)
        db_session.add(child)
        await db_session.commit()
        child_id = child.id

        await db_session.delete(parent)
        await db_session.commit()

        reloaded_child = await db_session.get(Category, child_id)
        assert reloaded_child is not None
        assert reloaded_child.parent_id is None

    async def test_offer_unique_per_connection_and_variant(self, db_session: AsyncSession) -> None:
        tenant = await _make_tenant(db_session)
        product = Product(tenant_id=tenant.id, sku="DUP-OFFER", name="Product")
        db_session.add(product)
        await db_session.flush()
        variant = Variant(tenant_id=tenant.id, product_id=product.id, sku="DUP-OFFER-V1")
        db_session.add(variant)
        connection = await _make_connection(db_session, tenant)
        await db_session.flush()

        offer_kwargs = dict(tenant_id=tenant.id, connection_id=connection.id, variant_id=variant.id)
        db_session.add(Offer(**offer_kwargs))
        await db_session.commit()

        db_session.add(Offer(**offer_kwargs))
        with pytest.raises(IntegrityError):
            await db_session.commit()
        await db_session.rollback()


class TestReview:
    async def test_rating_out_of_range_is_rejected(self, db_session: AsyncSession) -> None:
        tenant = await _make_tenant(db_session)
        connection = await _make_connection(db_session, tenant)

        db_session.add(
            Review(
                tenant_id=tenant.id,
                connection_id=connection.id,
                external_id="rev-1",
                rating=6,
                submitted_at=datetime.now(UTC),
            )
        )
        with pytest.raises(IntegrityError):
            await db_session.commit()
        await db_session.rollback()

    async def test_valid_rating_persists(self, db_session: AsyncSession) -> None:
        tenant = await _make_tenant(db_session)
        connection = await _make_connection(db_session, tenant)

        db_session.add(
            Review(
                tenant_id=tenant.id,
                connection_id=connection.id,
                external_id="rev-2",
                rating=5,
                submitted_at=datetime.now(UTC),
            )
        )
        await db_session.commit()


class TestOrder:
    async def test_order_with_items_and_cascade_delete(self, db_session: AsyncSession) -> None:
        tenant = await _make_tenant(db_session)
        connection = await _make_connection(db_session, tenant)

        order = Order(
            tenant_id=tenant.id,
            connection_id=connection.id,
            external_id="ext-order-1",
            status=OrderStatus.PAID,
            total_amount=Decimal("199.98"),
            placed_at=datetime.now(UTC),
        )
        db_session.add(order)
        await db_session.flush()
        db_session.add_all(
            [
                OrderItem(
                    tenant_id=tenant.id,
                    order_id=order.id,
                    sku="ITEM-1",
                    name="Item One",
                    quantity=2,
                    unit_price=Decimal("99.99"),
                )
            ]
        )
        await db_session.commit()
        order_id = order.id

        loaded = await db_session.scalar(
            select(Order).where(Order.id == order_id).options(selectinload(Order.items))
        )
        assert loaded is not None
        assert len(loaded.items) == 1

        await db_session.delete(loaded)
        await db_session.commit()

        remaining_items = await db_session.scalars(
            select(OrderItem).where(OrderItem.order_id == order_id)
        )
        assert remaining_items.first() is None


class TestRecommendationApprovalAudit:
    async def test_recommendation_has_at_most_one_approval(self, db_session: AsyncSession) -> None:
        tenant = await _make_tenant(db_session)
        product_id = uuid.uuid4()
        recommendation = Recommendation(
            tenant_id=tenant.id,
            type=RecommendationType.PRICE_CHANGE,
            risk_level=RiskLevel.MEDIUM,
            status=RecommendationStatus.PENDING_APPROVAL,
            entity_type="product",
            entity_id=product_id,
            title="Lower price to match competitors",
            payload={"old_price": "149.00", "new_price": "129.00"},
        )
        db_session.add(recommendation)
        await db_session.flush()

        approval_kwargs = dict(
            tenant_id=tenant.id, recommendation_id=recommendation.id, status=ApprovalStatus.PENDING
        )
        db_session.add(Approval(**approval_kwargs))
        await db_session.commit()

        db_session.add(Approval(**approval_kwargs))
        with pytest.raises(IntegrityError):
            await db_session.commit()
        await db_session.rollback()

    async def test_audit_event_records_before_after_without_updated_at(
        self, db_session: AsyncSession
    ) -> None:
        tenant = await _make_tenant(db_session)
        event = AuditEvent(
            tenant_id=tenant.id,
            actor_type=ActorType.AI_AGENT,
            action="price_change",
            entity_type="offer",
            entity_id=uuid.uuid4(),
            before={"amount": "149.00"},
            after={"amount": "129.00"},
            ai_model="claude-sonnet-5",
            result=AuditResult.SUCCESS,
        )
        db_session.add(event)
        await db_session.commit()

        assert not hasattr(event, "updated_at")
        loaded = await db_session.get(AuditEvent, event.id)
        assert loaded is not None
        assert loaded.before == {"amount": "149.00"}
        assert loaded.after == {"amount": "129.00"}
