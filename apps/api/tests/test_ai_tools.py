from decimal import Decimal

import pytest
from cp_ai.tools import (
    ToolCall,
    ToolContext,
    ToolExecutor,
    ToolPermission,
    ToolRegistry,
    ToolResult,
    ToolRiskLevel,
    ToolSchema,
)
from cp_ai.tools.builtin.product_tools import (
    GetProductArgs,
    RequestListingPublishArgs,
    UpdatePriceArgs,
    UpdateProductContentArgs,
    UpdateProductStatusArgs,
    get_product_tool,
    request_listing_publish_handler,
    request_listing_publish_tool,
    update_price_handler,
    update_price_tool,
    update_product_content_handler,
    update_product_content_tool,
    update_product_status_handler,
    update_product_status_tool,
)
from cp_domain.audit_event import ActorType, AuditEvent
from cp_domain.offer import Offer, OfferStatus
from cp_domain.price import Price
from cp_domain.product import Product, ProductStatus
from cp_domain.variant import Variant
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import make_connection, make_tenant

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _make_product(db: AsyncSession, tenant, sku: str, name: str) -> Product:
    product = Product(tenant_id=tenant.id, sku=sku, name=name)
    db.add(product)
    await db.flush()
    return product


async def _make_offer_with_price(
    db: AsyncSession, tenant, connection, sku: str, amount: Decimal
) -> Offer:
    product = await _make_product(db, tenant, sku, "Priced product")
    variant = Variant(tenant_id=tenant.id, product_id=product.id, sku=sku)
    db.add(variant)
    await db.flush()
    offer = Offer(tenant_id=tenant.id, connection_id=connection.id, variant_id=variant.id)
    db.add(offer)
    await db.flush()
    db.add(Price(tenant_id=tenant.id, offer_id=offer.id, amount=amount))
    await db.commit()
    return offer


async def _make_draft_offer_with_external_id(
    db: AsyncSession, tenant, connection, sku: str, external_id: str = "ext-1"
) -> Offer:
    product = await _make_product(db, tenant, sku, "Draft listing")
    variant = Variant(tenant_id=tenant.id, product_id=product.id, sku=sku)
    db.add(variant)
    await db.flush()
    offer = Offer(
        tenant_id=tenant.id,
        connection_id=connection.id,
        variant_id=variant.id,
        external_id=external_id,
        status=OfferStatus.DRAFT,
    )
    db.add(offer)
    await db.commit()
    return offer


class TestGetProductTool:
    async def test_returns_the_matching_product(self, db_session: AsyncSession) -> None:
        tenant = await make_tenant(db_session)
        await _make_product(db_session, tenant, "SKU-1", "Running Shoe")
        await db_session.commit()

        registry = ToolRegistry()
        registry.register(get_product_tool())
        executor = ToolExecutor(registry, db_session)
        context = ToolContext(tenant_id=tenant.id, actor_type=ActorType.AI_AGENT)

        result = await executor.execute(
            ToolCall(name="get_product", arguments={"sku": "SKU-1"}), context
        )

        assert result.success is True
        assert result.data["sku"] == "SKU-1"
        assert result.data["name"] == "Running Shoe"

    async def test_unknown_sku_fails(self, db_session: AsyncSession) -> None:
        tenant = await make_tenant(db_session)
        registry = ToolRegistry()
        registry.register(get_product_tool())
        executor = ToolExecutor(registry, db_session)
        context = ToolContext(tenant_id=tenant.id, actor_type=ActorType.AI_AGENT)

        result = await executor.execute(
            ToolCall(name="get_product", arguments={"sku": "NOPE"}), context
        )

        assert result.success is False

    async def test_tenant_isolation_cannot_see_another_tenants_product(
        self, db_session: AsyncSession
    ) -> None:
        tenant_a = await make_tenant(db_session, "Tenant A")
        tenant_b = await make_tenant(db_session, "Tenant B")
        await _make_product(db_session, tenant_a, "SHARED-SKU", "A's product")
        await db_session.commit()

        registry = ToolRegistry()
        registry.register(get_product_tool())
        executor = ToolExecutor(registry, db_session)
        context_b = ToolContext(tenant_id=tenant_b.id, actor_type=ActorType.AI_AGENT)

        result = await executor.execute(
            ToolCall(name="get_product", arguments={"sku": "SHARED-SKU"}), context_b
        )

        assert result.success is False

    async def test_no_audit_log_is_written_for_a_read(self, db_session: AsyncSession) -> None:
        tenant = await make_tenant(db_session)
        await _make_product(db_session, tenant, "SKU-1", "Running Shoe")
        await db_session.commit()

        registry = ToolRegistry()
        registry.register(get_product_tool())
        executor = ToolExecutor(registry, db_session)
        context = ToolContext(tenant_id=tenant.id, actor_type=ActorType.AI_AGENT)

        await executor.execute(ToolCall(name="get_product", arguments={"sku": "SKU-1"}), context)

        event = await db_session.scalar(select(AuditEvent).where(AuditEvent.tenant_id == tenant.id))
        assert event is None


class TestUpdatePriceTool:
    async def test_high_risk_tool_never_runs_and_never_mutates(
        self, db_session: AsyncSession
    ) -> None:
        tenant = await make_tenant(db_session)
        connection = await make_connection(db_session, tenant)
        offer = await _make_offer_with_price(
            db_session, tenant, connection, "SKU-PRICE", Decimal("100.00")
        )

        registry = ToolRegistry()
        registry.register(update_price_tool())
        executor = ToolExecutor(registry, db_session)
        context = ToolContext(tenant_id=tenant.id, actor_type=ActorType.AI_AGENT)

        result = await executor.execute(
            ToolCall(
                name="update_price",
                arguments={"offer_id": str(offer.id), "new_amount": "80.00"},
            ),
            context,
        )

        assert result.success is False
        assert result.requires_approval is True

        price = await db_session.scalar(select(Price).where(Price.offer_id == offer.id))
        assert price.amount == Decimal("100.00")

        event = await db_session.scalar(select(AuditEvent).where(AuditEvent.tenant_id == tenant.id))
        assert event is None

    async def test_handler_itself_correctly_updates_the_price(
        self, db_session: AsyncSession
    ) -> None:
        """`update_price_handler` is never reachable through the real
        (HIGH-risk) tool without Phase 8's approval workflow - this
        exercises its own logic directly, the way Phase 8 will once it
        resumes execution after an approval."""
        tenant = await make_tenant(db_session)
        connection = await make_connection(db_session, tenant)
        offer = await _make_offer_with_price(
            db_session, tenant, connection, "SKU-PRICE", Decimal("100.00")
        )
        context = ToolContext(tenant_id=tenant.id, actor_type=ActorType.AI_AGENT)

        result = await update_price_handler(
            UpdatePriceArgs(offer_id=offer.id, new_amount=Decimal("80.00")), context, db_session
        )

        assert result.success is True
        assert result.before == {"amount": "100.00", "currency": "PLN"}
        assert result.after == {"amount": "80.00", "currency": "PLN"}

        price = await db_session.scalar(select(Price).where(Price.offer_id == offer.id))
        assert price.amount == Decimal("80.00")

    async def test_handler_rejects_offer_outside_tenant(self, db_session: AsyncSession) -> None:
        tenant_a = await make_tenant(db_session, "Tenant A")
        tenant_b = await make_tenant(db_session, "Tenant B")
        connection_a = await make_connection(db_session, tenant_a)
        offer = await _make_offer_with_price(
            db_session, tenant_a, connection_a, "SKU-PRICE", Decimal("100.00")
        )
        context_b = ToolContext(tenant_id=tenant_b.id, actor_type=ActorType.AI_AGENT)

        result = await update_price_handler(
            UpdatePriceArgs(offer_id=offer.id, new_amount=Decimal("1.00")), context_b, db_session
        )

        assert result.success is False

        price = await db_session.scalar(select(Price).where(Price.offer_id == offer.id))
        assert price.amount == Decimal("100.00")


class TestUpdateProductContentTool:
    async def test_medium_risk_tool_never_runs_through_the_executor(
        self, db_session: AsyncSession
    ) -> None:
        tenant = await make_tenant(db_session)
        await _make_product(db_session, tenant, "SKU-1", "Old name")
        await db_session.commit()

        registry = ToolRegistry()
        registry.register(update_product_content_tool())
        executor = ToolExecutor(registry, db_session)
        context = ToolContext(tenant_id=tenant.id, actor_type=ActorType.AI_AGENT)

        result = await executor.execute(
            ToolCall(
                name="update_product_content",
                arguments={"sku": "SKU-1", "new_name": "New name"},
            ),
            context,
        )

        assert result.success is False
        assert result.requires_approval is True

        product = await db_session.scalar(select(Product).where(Product.sku == "SKU-1"))
        assert product.name == "Old name"

        event = await db_session.scalar(select(AuditEvent).where(AuditEvent.tenant_id == tenant.id))
        assert event is None

    async def test_handler_updates_name_description_and_extra_attributes(
        self, db_session: AsyncSession
    ) -> None:
        tenant = await make_tenant(db_session)
        product = await _make_product(db_session, tenant, "SKU-1", "Old name")
        product.description = "Old description"
        await db_session.commit()
        context = ToolContext(tenant_id=tenant.id, actor_type=ActorType.AI_AGENT)

        result = await update_product_content_handler(
            UpdateProductContentArgs(
                sku="SKU-1",
                new_name="New name",
                new_description="New description",
                new_extra_attributes={"specifications": {"ean": "UNKNOWN"}},
            ),
            context,
            db_session,
        )

        assert result.success is True
        assert result.before == {
            "name": "Old name",
            "description": "Old description",
            "extra_attributes": None,
        }
        assert result.after == {
            "name": "New name",
            "description": "New description",
            "extra_attributes": {"specifications": {"ean": "UNKNOWN"}},
        }

        reloaded = await db_session.scalar(select(Product).where(Product.sku == "SKU-1"))
        assert reloaded.name == "New name"
        assert reloaded.extra_attributes == {"specifications": {"ean": "UNKNOWN"}}

    async def test_handler_rejects_product_outside_tenant(self, db_session: AsyncSession) -> None:
        tenant_a = await make_tenant(db_session, "Tenant A")
        tenant_b = await make_tenant(db_session, "Tenant B")
        await _make_product(db_session, tenant_a, "SKU-1", "Old name")
        await db_session.commit()
        context_b = ToolContext(tenant_id=tenant_b.id, actor_type=ActorType.AI_AGENT)

        result = await update_product_content_handler(
            UpdateProductContentArgs(sku="SKU-1", new_name="Hijacked"), context_b, db_session
        )

        assert result.success is False

        product = await db_session.scalar(select(Product).where(Product.sku == "SKU-1"))
        assert product.name == "Old name"


class _SetDescriptionArgs(BaseModel):
    sku: str
    new_description: str


async def _set_description_handler(
    args: _SetDescriptionArgs, context: ToolContext, db: AsyncSession
) -> ToolResult:
    product = await db.scalar(
        select(Product).where(Product.tenant_id == context.tenant_id, Product.sku == args.sku)
    )
    if product is None:
        return ToolResult.fail(f"No product with sku {args.sku!r}")

    before = {"description": product.description}
    product.description = args.new_description
    after = {"description": product.description}
    return ToolResult.ok(
        after, entity_type="product", entity_id=product.id, before=before, after=after
    )


class TestAuditLogForLowRiskMutation:
    """`get_product`/`update_price` are the two builtin tools, but neither
    proves a LOW-risk *mutation* being auto-executed and audited - that
    combination doesn't have a real builtin tool yet, so this defines a
    minimal one inline to prove the executor's audit-log write actually
    persists correctly against a real Postgres schema (packages/ai's own
    tests cover the same behavior against a mocked session)."""

    async def test_low_risk_mutation_executes_and_persists_an_audit_event(
        self, db_session: AsyncSession
    ) -> None:
        tenant = await make_tenant(db_session)
        product = await _make_product(db_session, tenant, "SKU-DESC", "Old name")
        await db_session.commit()

        registry = ToolRegistry()
        registry.register(
            ToolSchema(
                name="set_description",
                description="test-only tool",
                args_model=_SetDescriptionArgs,
                permission=ToolPermission(risk_level=ToolRiskLevel.LOW, mutates=True),
                handler=_set_description_handler,
            )
        )
        executor = ToolExecutor(registry, db_session)
        context = ToolContext(
            tenant_id=tenant.id, actor_type=ActorType.AI_AGENT, ai_model="claude-sonnet-5"
        )

        result = await executor.execute(
            ToolCall(
                name="set_description",
                arguments={"sku": "SKU-DESC", "new_description": "New description"},
            ),
            context,
        )

        assert result.success is True

        await db_session.refresh(product)
        assert product.description == "New description"

        event = await db_session.scalar(
            select(AuditEvent).where(AuditEvent.tenant_id == tenant.id)
        )
        assert event is not None
        assert event.actor_type == ActorType.AI_AGENT
        assert event.action == "set_description"
        assert event.entity_type == "product"
        assert event.entity_id == product.id
        assert event.after == {"description": "New description"}
        assert event.ai_model == "claude-sonnet-5"


class TestRequestListingPublishTool:
    async def test_high_risk_tool_never_runs_through_the_executor(
        self, db_session: AsyncSession
    ) -> None:
        tenant = await make_tenant(db_session)
        connection = await make_connection(db_session, tenant)
        offer = await _make_draft_offer_with_external_id(db_session, tenant, connection, "SKU-1")

        registry = ToolRegistry()
        registry.register(request_listing_publish_tool())
        executor = ToolExecutor(registry, db_session)
        context = ToolContext(tenant_id=tenant.id, actor_type=ActorType.AI_AGENT)

        result = await executor.execute(
            ToolCall(name="request_listing_publish", arguments={"offer_id": str(offer.id)}),
            context,
        )

        assert result.success is False
        assert result.requires_approval is True

        await db_session.refresh(offer)
        assert offer.status is OfferStatus.DRAFT

        event = await db_session.scalar(select(AuditEvent).where(AuditEvent.tenant_id == tenant.id))
        assert event is None

    async def test_handler_moves_a_draft_offer_to_pending(self, db_session: AsyncSession) -> None:
        tenant = await make_tenant(db_session)
        connection = await make_connection(db_session, tenant)
        offer = await _make_draft_offer_with_external_id(db_session, tenant, connection, "SKU-1")
        context = ToolContext(tenant_id=tenant.id, actor_type=ActorType.AI_AGENT)

        result = await request_listing_publish_handler(
            RequestListingPublishArgs(offer_id=offer.id), context, db_session
        )

        assert result.success is True
        assert result.before == {"status": "draft"}
        assert result.after == {"status": "pending"}

        reloaded = await db_session.scalar(select(Offer).where(Offer.id == offer.id))
        assert reloaded.status is OfferStatus.PENDING

    async def test_handler_rejects_an_offer_with_no_external_id(
        self, db_session: AsyncSession
    ) -> None:
        tenant = await make_tenant(db_session)
        connection = await make_connection(db_session, tenant)
        offer = await _make_offer_with_price(
            db_session, tenant, connection, "SKU-1", Decimal("10.00")
        )
        context = ToolContext(tenant_id=tenant.id, actor_type=ActorType.AI_AGENT)

        result = await request_listing_publish_handler(
            RequestListingPublishArgs(offer_id=offer.id), context, db_session
        )

        assert result.success is False
        await db_session.refresh(offer)
        assert offer.status is OfferStatus.DRAFT

    async def test_handler_rejects_an_offer_that_is_not_draft(
        self, db_session: AsyncSession
    ) -> None:
        tenant = await make_tenant(db_session)
        connection = await make_connection(db_session, tenant)
        offer = await _make_draft_offer_with_external_id(db_session, tenant, connection, "SKU-1")
        offer.status = OfferStatus.ACTIVE
        await db_session.commit()
        context = ToolContext(tenant_id=tenant.id, actor_type=ActorType.AI_AGENT)

        result = await request_listing_publish_handler(
            RequestListingPublishArgs(offer_id=offer.id), context, db_session
        )

        assert result.success is False
        await db_session.refresh(offer)
        assert offer.status is OfferStatus.ACTIVE

    async def test_handler_rejects_offer_outside_tenant(self, db_session: AsyncSession) -> None:
        tenant_a = await make_tenant(db_session, "Tenant A")
        tenant_b = await make_tenant(db_session, "Tenant B")
        connection_a = await make_connection(db_session, tenant_a)
        offer = await _make_draft_offer_with_external_id(
            db_session, tenant_a, connection_a, "SKU-1"
        )
        context_b = ToolContext(tenant_id=tenant_b.id, actor_type=ActorType.AI_AGENT)

        result = await request_listing_publish_handler(
            RequestListingPublishArgs(offer_id=offer.id), context_b, db_session
        )

        assert result.success is False
        await db_session.refresh(offer)
        assert offer.status is OfferStatus.DRAFT


class TestUpdateProductStatusTool:
    async def test_medium_risk_tool_never_runs_through_the_executor(
        self, db_session: AsyncSession
    ) -> None:
        tenant = await make_tenant(db_session)
        await _make_product(db_session, tenant, "SKU-1", "Old name")
        await db_session.commit()

        registry = ToolRegistry()
        registry.register(update_product_status_tool())
        executor = ToolExecutor(registry, db_session)
        context = ToolContext(tenant_id=tenant.id, actor_type=ActorType.AI_AGENT)

        result = await executor.execute(
            ToolCall(
                name="update_product_status",
                arguments={"sku": "SKU-1", "new_status": "archived"},
            ),
            context,
        )

        assert result.success is False
        assert result.requires_approval is True

        product = await db_session.scalar(select(Product).where(Product.sku == "SKU-1"))
        assert product.status is ProductStatus.DRAFT

        event = await db_session.scalar(select(AuditEvent).where(AuditEvent.tenant_id == tenant.id))
        assert event is None

    async def test_handler_changes_the_status(self, db_session: AsyncSession) -> None:
        tenant = await make_tenant(db_session)
        product = await _make_product(db_session, tenant, "SKU-1", "Old name")
        product.status = ProductStatus.ACTIVE
        await db_session.commit()
        context = ToolContext(tenant_id=tenant.id, actor_type=ActorType.AI_AGENT)

        result = await update_product_status_handler(
            UpdateProductStatusArgs(sku="SKU-1", new_status=ProductStatus.ARCHIVED),
            context,
            db_session,
        )

        assert result.success is True
        assert result.before == {"status": "active"}
        assert result.after == {"status": "archived"}

        reloaded = await db_session.scalar(select(Product).where(Product.sku == "SKU-1"))
        assert reloaded.status is ProductStatus.ARCHIVED

    async def test_handler_rejects_product_outside_tenant(self, db_session: AsyncSession) -> None:
        tenant_a = await make_tenant(db_session, "Tenant A")
        tenant_b = await make_tenant(db_session, "Tenant B")
        await _make_product(db_session, tenant_a, "SKU-1", "Old name")
        await db_session.commit()
        context_b = ToolContext(tenant_id=tenant_b.id, actor_type=ActorType.AI_AGENT)

        result = await update_product_status_handler(
            UpdateProductStatusArgs(sku="SKU-1", new_status=ProductStatus.ARCHIVED),
            context_b,
            db_session,
        )

        assert result.success is False
        product = await db_session.scalar(select(Product).where(Product.sku == "SKU-1"))
        assert product.status is ProductStatus.DRAFT


class TestGetProductArgsRejectsTenantId:
    async def test_builtin_args_models_never_declare_tenant_id(self) -> None:
        assert "tenant_id" not in GetProductArgs.model_fields
        assert "tenant_id" not in UpdatePriceArgs.model_fields
        assert "tenant_id" not in UpdateProductContentArgs.model_fields
        assert "tenant_id" not in RequestListingPublishArgs.model_fields
        assert "tenant_id" not in UpdateProductStatusArgs.model_fields
