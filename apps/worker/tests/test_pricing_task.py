import asyncio
import uuid
from decimal import Decimal

from cp_domain.recommendation import Recommendation, RecommendationStatus, RecommendationType
from cp_pricing import PricingInputs, compute_price_bounds
from sqlalchemy import func, select

from tests.conftest import make_connection, make_offer_with_price, make_tenant
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
