import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from cp_domain.recommendation import Recommendation, RecommendationStatus, RecommendationType
from cp_pricing import PricingInputs, compute_price_bounds
from sqlalchemy import func, select

from tests.conftest import (
    get_product_id,
    make_competitor_price,
    make_connection,
    make_offer_with_price,
    make_tenant,
)
from worker.db import async_session_factory
from worker.tasks.pricing import generate_price_recommendation


def _count_recommendations() -> int:
    async def _run() -> int:
        async with async_session_factory() as db:
            return await db.scalar(select(func.count()).select_from(Recommendation))

    return asyncio.run(_run())


def _get_recommendation(recommendation_id: str) -> Recommendation:
    async def _run() -> Recommendation:
        async with async_session_factory() as db:
            return await db.get(Recommendation, uuid.UUID(recommendation_id))

    return asyncio.run(_run())


class TestGeneratePriceRecommendation:
    def test_proposes_a_recommendation_when_price_should_change(self) -> None:
        tenant_id = make_tenant()
        connection_id = make_connection(tenant_id, {"access_token": "tok"})
        offer_id = make_offer_with_price(
            tenant_id, connection_id, cost=Decimal("60"), price_amount=Decimal("100.00")
        )

        result = generate_price_recommendation.run(str(tenant_id), str(offer_id))

        assert result["proposed"] is True
        recommendation = _get_recommendation(result["recommendation_id"])
        assert recommendation.status is RecommendationStatus.PENDING_APPROVAL
        assert recommendation.type is RecommendationType.PRICE_CHANGE
        assert recommendation.entity_type == "offer"
        assert recommendation.entity_id == offer_id
        assert recommendation.payload["tool_name"] == "update_price"
        assert recommendation.payload["tool_arguments"]["offer_id"] == str(offer_id)

    def test_no_proposal_when_already_at_the_recommended_price(self) -> None:
        tenant_id = make_tenant()
        connection_id = make_connection(tenant_id, {"access_token": "tok"})
        already_recommended = compute_price_bounds(
            PricingInputs(cost=Decimal("60"))
        ).recommended_price
        offer_id = make_offer_with_price(
            tenant_id, connection_id, cost=Decimal("60"), price_amount=already_recommended
        )

        result = generate_price_recommendation.run(str(tenant_id), str(offer_id))

        assert result["proposed"] is False
        assert _count_recommendations() == 0

    def test_second_run_does_not_duplicate_a_pending_recommendation(self) -> None:
        tenant_id = make_tenant()
        connection_id = make_connection(tenant_id, {"access_token": "tok"})
        offer_id = make_offer_with_price(
            tenant_id, connection_id, cost=Decimal("60"), price_amount=Decimal("100.00")
        )

        first = generate_price_recommendation.run(str(tenant_id), str(offer_id))
        second = generate_price_recommendation.run(str(tenant_id), str(offer_id))

        assert first["proposed"] is True
        assert second["proposed"] is False
        assert "pending" in second["reason"]
        assert _count_recommendations() == 1

    def test_missing_offer_is_reported_without_raising(self) -> None:
        tenant_id = make_tenant()

        result = generate_price_recommendation.run(str(tenant_id), str(uuid.uuid4()))

        assert result == {"proposed": False, "reason": "offer not found"}

    def test_missing_cost_produces_no_proposal(self) -> None:
        tenant_id = make_tenant()
        connection_id = make_connection(tenant_id, {"access_token": "tok"})
        offer_id = make_offer_with_price(
            tenant_id, connection_id, cost=None, price_amount=Decimal("100.00")
        )

        result = generate_price_recommendation.run(str(tenant_id), str(offer_id))

        assert result["proposed"] is False
        assert _count_recommendations() == 0

    def test_a_recent_competitor_price_caps_the_recommendation(self) -> None:
        """Phase 14: cp_pricing has accepted competitor_prices since
        Phase 9, but nothing ever populated it until now - this proves
        the wiring actually changes the recommended price, not just that
        a recommendation gets proposed."""
        tenant_id = make_tenant()
        connection_id = make_connection(tenant_id, {"access_token": "tok"})
        offer_id = make_offer_with_price(
            tenant_id, connection_id, cost=Decimal("60"), price_amount=Decimal("100.00")
        )
        product_id = get_product_id(tenant_id, "SKU-1")
        # Uncapped, cost=60 targets ~85.71 (see the no-competitor test
        # above) - a competitor at 70 sits below that but above the
        # margin floor (~66.67), so the engine should cap there instead.
        make_competitor_price(tenant_id, product_id, price=Decimal("70.00"))

        result = generate_price_recommendation.run(str(tenant_id), str(offer_id))

        assert result["proposed"] is True
        recommendation = _get_recommendation(result["recommendation_id"])
        assert Decimal(recommendation.payload["tool_arguments"]["new_amount"]) == Decimal("70.00")

    def test_a_stale_competitor_price_is_ignored(self) -> None:
        tenant_id = make_tenant()
        connection_id = make_connection(tenant_id, {"access_token": "tok"})
        offer_id = make_offer_with_price(
            tenant_id, connection_id, cost=Decimal("60"), price_amount=Decimal("100.00")
        )
        product_id = get_product_id(tenant_id, "SKU-1")
        make_competitor_price(
            tenant_id,
            product_id,
            price=Decimal("70.00"),
            observed_at=datetime.now(UTC) - timedelta(days=40),
        )

        result = generate_price_recommendation.run(str(tenant_id), str(offer_id))

        recommendation = _get_recommendation(result["recommendation_id"])
        uncapped = compute_price_bounds(PricingInputs(cost=Decimal("60"))).recommended_price
        assert Decimal(recommendation.payload["tool_arguments"]["new_amount"]) == uncapped
