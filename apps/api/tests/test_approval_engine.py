from decimal import Decimal

import pytest
from cp_ai.tools import ToolCall, ToolContext, ToolExecutor, ToolRegistry
from cp_ai.tools.builtin.product_tools import update_price_tool
from cp_domain.audit_event import ActorType, AuditEvent
from cp_domain.offer import Offer
from cp_domain.price import Price
from cp_domain.product import Product
from cp_domain.recommendation import (
    Recommendation,
    RecommendationStatus,
    RecommendationType,
    RiskLevel,
)
from cp_domain.variant import Variant
from cp_policies import (
    RecommendationNotFoundError,
    RecommendationNotPendingError,
    approve,
    propose_recommendation,
    reject,
    submit_for_approval,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import make_connection, make_tenant, make_user

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _make_offer_with_price(
    db: AsyncSession, tenant, connection, sku: str, amount: Decimal
) -> Offer:
    product = Product(tenant_id=tenant.id, sku=sku, name="Priced product")
    db.add(product)
    await db.flush()
    variant = Variant(tenant_id=tenant.id, product_id=product.id, sku=sku)
    db.add(variant)
    await db.flush()
    offer = Offer(tenant_id=tenant.id, connection_id=connection.id, variant_id=variant.id)
    db.add(offer)
    await db.flush()
    db.add(Price(tenant_id=tenant.id, offer_id=offer.id, amount=amount))
    await db.commit()
    return offer


async def _propose_price_change(db, tenant, offer, new_amount: Decimal) -> Recommendation:
    """What an agent runtime (Phase 9) will do when `ToolExecutor.execute`
    comes back `requires_approval`: turn the exact same tool call into a
    Recommendation using the tool's own arguments."""
    return await propose_recommendation(
        db,
        tenant_id=tenant.id,
        type=RecommendationType.PRICE_CHANGE,
        risk_level=RiskLevel.HIGH,
        entity_type="offer",
        entity_id=offer.id,
        title="Lower price to match competitors",
        tool_name="update_price",
        tool_arguments={"offer_id": str(offer.id), "new_amount": str(new_amount)},
        reason="Competitor X dropped their price by 20%",
    )


class TestFullApprovalFlow:
    async def test_gated_tool_call_comes_back_requires_approval(
        self, db_session: AsyncSession
    ) -> None:
        tenant = await make_tenant(db_session)
        connection = await make_connection(db_session, tenant)
        offer = await _make_offer_with_price(
            db_session, tenant, connection, "SKU-1", Decimal("100.00")
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

        assert result.requires_approval is True

    async def test_propose_submit_approve_executes_the_tool_and_audits(
        self, db_session: AsyncSession
    ) -> None:
        tenant = await make_tenant(db_session)
        connection = await make_connection(db_session, tenant)
        approver = await make_user(db_session)
        offer = await _make_offer_with_price(
            db_session, tenant, connection, "SKU-1", Decimal("100.00")
        )

        recommendation = await _propose_price_change(db_session, tenant, offer, Decimal("80.00"))
        assert recommendation.status is RecommendationStatus.PROPOSED

        approval = await submit_for_approval(db_session, recommendation)
        assert recommendation.status is RecommendationStatus.PENDING_APPROVAL
        assert approval.recommendation_id == recommendation.id

        registry = ToolRegistry()
        registry.register(update_price_tool())

        result = await approve(
            db_session,
            registry,
            tenant_id=tenant.id,
            recommendation_id=recommendation.id,
            decided_by=approver.id,
            decision_reason="Looks reasonable",
        )

        assert result.status is RecommendationStatus.SUCCESS

        price = await db_session.scalar(select(Price).where(Price.offer_id == offer.id))
        assert price.amount == Decimal("80.00")

        event = await db_session.scalar(
            select(AuditEvent).where(AuditEvent.tenant_id == tenant.id)
        )
        assert event is not None
        assert event.action == "update_price"
        assert event.entity_type == "price"
        assert event.actor_type == ActorType.USER
        assert event.actor_id == approver.id
        assert event.approval_id is not None
        assert event.before == {"amount": "100.00", "currency": "PLN"}
        assert event.after == {"amount": "80.00", "currency": "PLN"}

    async def test_rejecting_leaves_the_price_untouched_and_writes_no_audit(
        self, db_session: AsyncSession
    ) -> None:
        tenant = await make_tenant(db_session)
        connection = await make_connection(db_session, tenant)
        approver = await make_user(db_session)
        offer = await _make_offer_with_price(
            db_session, tenant, connection, "SKU-1", Decimal("100.00")
        )

        recommendation = await _propose_price_change(db_session, tenant, offer, Decimal("80.00"))
        await submit_for_approval(db_session, recommendation)

        result = await reject(
            db_session,
            tenant_id=tenant.id,
            recommendation_id=recommendation.id,
            decided_by=approver.id,
            decision_reason="Not competitive enough to matter",
        )

        assert result.status is RecommendationStatus.REJECTED

        price = await db_session.scalar(select(Price).where(Price.offer_id == offer.id))
        assert price.amount == Decimal("100.00")

        event = await db_session.scalar(
            select(AuditEvent).where(AuditEvent.tenant_id == tenant.id)
        )
        assert event is None

    async def test_approving_a_recommendation_outside_your_tenant_is_rejected(
        self, db_session: AsyncSession
    ) -> None:
        tenant_a = await make_tenant(db_session, "Tenant A")
        tenant_b = await make_tenant(db_session, "Tenant B")
        connection_a = await make_connection(db_session, tenant_a)
        approver_b = await make_user(db_session)
        offer = await _make_offer_with_price(
            db_session, tenant_a, connection_a, "SKU-1", Decimal("100.00")
        )

        recommendation = await _propose_price_change(db_session, tenant_a, offer, Decimal("80.00"))
        await submit_for_approval(db_session, recommendation)

        registry = ToolRegistry()
        registry.register(update_price_tool())

        with pytest.raises(RecommendationNotFoundError):
            await approve(
                db_session,
                registry,
                tenant_id=tenant_b.id,
                recommendation_id=recommendation.id,
                decided_by=approver_b.id,
            )

        price = await db_session.scalar(select(Price).where(Price.offer_id == offer.id))
        assert price.amount == Decimal("100.00")

    async def test_double_decision_is_rejected(self, db_session: AsyncSession) -> None:
        tenant = await make_tenant(db_session)
        connection = await make_connection(db_session, tenant)
        approver = await make_user(db_session)
        offer = await _make_offer_with_price(
            db_session, tenant, connection, "SKU-1", Decimal("100.00")
        )

        recommendation = await _propose_price_change(db_session, tenant, offer, Decimal("80.00"))
        await submit_for_approval(db_session, recommendation)

        registry = ToolRegistry()
        registry.register(update_price_tool())
        await approve(
            db_session,
            registry,
            tenant_id=tenant.id,
            recommendation_id=recommendation.id,
            decided_by=approver.id,
        )

        with pytest.raises(RecommendationNotPendingError):
            await reject(
                db_session,
                tenant_id=tenant.id,
                recommendation_id=recommendation.id,
                decided_by=approver.id,
            )

    async def test_submitting_something_not_proposed_is_rejected(
        self, db_session: AsyncSession
    ) -> None:
        tenant = await make_tenant(db_session)
        connection = await make_connection(db_session, tenant)
        offer = await _make_offer_with_price(
            db_session, tenant, connection, "SKU-1", Decimal("100.00")
        )

        recommendation = await _propose_price_change(db_session, tenant, offer, Decimal("80.00"))
        await submit_for_approval(db_session, recommendation)

        with pytest.raises(RecommendationNotPendingError):
            await submit_for_approval(db_session, recommendation)
