import asyncio
import uuid

import pytest
from cp_connectors.mock import MockConnector
from cp_connectors.types import ConnectorProduct
from cp_domain.audit_event import AuditEvent, AuditResult
from cp_domain.offer import Offer, OfferStatus
from cp_domain.recommendation import Recommendation, RecommendationStatus, RecommendationType
from sqlalchemy import func, select

from tests.conftest import make_connection, make_offer_with_price, make_tenant
from worker.db import async_session_factory
from worker.tasks.listing import (
    generate_listing_publish_recommendation,
    publish_listing_to_marketplace,
)


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


def _get_offer(offer_id: uuid.UUID) -> Offer:
    async def _run() -> Offer:
        async with async_session_factory() as db:
            return await db.get(Offer, offer_id)

    return asyncio.run(_run())


def _get_audit_event(tenant_id: uuid.UUID) -> AuditEvent | None:
    async def _run() -> AuditEvent | None:
        async with async_session_factory() as db:
            return await db.scalar(
                select(AuditEvent).where(AuditEvent.tenant_id == tenant_id)
            )

    return asyncio.run(_run())


class TestGenerateListingPublishRecommendation:
    def test_proposes_when_the_listing_is_ready(self) -> None:
        tenant_id = make_tenant()
        connection_id = make_connection(tenant_id, {"access_token": "tok"})
        offer_id = make_offer_with_price(
            tenant_id,
            connection_id,
            description="A great product",
            external_id="ext-1",
            status=OfferStatus.DRAFT,
        )

        result = generate_listing_publish_recommendation.run(str(tenant_id), str(offer_id))

        assert result["proposed"] is True
        recommendation = _get_recommendation(result["recommendation_id"])
        assert recommendation.status is RecommendationStatus.PENDING_APPROVAL
        assert recommendation.type is RecommendationType.LISTING_PUBLISH
        assert recommendation.entity_type == "offer"
        assert recommendation.entity_id == offer_id
        assert recommendation.payload["tool_name"] == "request_listing_publish"
        assert recommendation.payload["tool_arguments"]["offer_id"] == str(offer_id)

    def test_no_proposal_without_an_external_id(self) -> None:
        tenant_id = make_tenant()
        connection_id = make_connection(tenant_id, {"access_token": "tok"})
        offer_id = make_offer_with_price(
            tenant_id, connection_id, description="A great product", external_id=None
        )

        result = generate_listing_publish_recommendation.run(str(tenant_id), str(offer_id))

        assert result["proposed"] is False
        assert _count_recommendations() == 0

    def test_no_proposal_without_a_description(self) -> None:
        tenant_id = make_tenant()
        connection_id = make_connection(tenant_id, {"access_token": "tok"})
        offer_id = make_offer_with_price(
            tenant_id, connection_id, description=None, external_id="ext-1"
        )

        result = generate_listing_publish_recommendation.run(str(tenant_id), str(offer_id))

        assert result["proposed"] is False
        assert _count_recommendations() == 0

    def test_second_run_does_not_duplicate_a_pending_recommendation(self) -> None:
        tenant_id = make_tenant()
        connection_id = make_connection(tenant_id, {"access_token": "tok"})
        offer_id = make_offer_with_price(
            tenant_id, connection_id, description="A great product", external_id="ext-1"
        )

        first = generate_listing_publish_recommendation.run(str(tenant_id), str(offer_id))
        second = generate_listing_publish_recommendation.run(str(tenant_id), str(offer_id))

        assert first["proposed"] is True
        assert second["proposed"] is False
        assert "pending" in second["reason"]
        assert _count_recommendations() == 1

    def test_missing_offer_is_reported_without_raising(self) -> None:
        tenant_id = make_tenant()

        result = generate_listing_publish_recommendation.run(str(tenant_id), str(uuid.uuid4()))

        assert result == {"proposed": False, "reason": "offer not found"}


class TestPublishListingToMarketplace:
    def test_publishes_and_activates_the_offer(self, monkeypatch) -> None:
        tenant_id = make_tenant()
        connection_id = make_connection(tenant_id, {"access_token": "tok"})
        offer_id = make_offer_with_price(
            tenant_id,
            connection_id,
            description="A great product",
            external_id="ext-1",
            status=OfferStatus.PENDING,
        )

        connector = MockConnector()
        asyncio.run(
            connector.create_product(
                ConnectorProduct(sku="SKU-1", name="X", external_id="ext-1")
            )
        )
        monkeypatch.setattr(
            "worker.tasks.listing.build_connector", lambda connection, credentials: connector
        )

        result = publish_listing_to_marketplace.run(str(tenant_id), str(offer_id))

        assert result == {"published": True}
        offer = _get_offer(offer_id)
        assert offer.status is OfferStatus.ACTIVE

        event = _get_audit_event(tenant_id)
        assert event is not None
        assert event.result is AuditResult.SUCCESS
        assert event.action == "publish_listing_to_marketplace"
        assert event.before == {"status": "pending"}
        assert event.after == {"status": "active"}

    def test_connector_error_marks_the_offer_as_error(self, monkeypatch) -> None:
        tenant_id = make_tenant()
        connection_id = make_connection(tenant_id, {"access_token": "tok"})
        offer_id = make_offer_with_price(
            tenant_id,
            connection_id,
            description="A great product",
            external_id="does-not-exist",
            status=OfferStatus.PENDING,
        )

        connector = MockConnector()
        monkeypatch.setattr(
            "worker.tasks.listing.build_connector", lambda connection, credentials: connector
        )

        result = publish_listing_to_marketplace.run(str(tenant_id), str(offer_id))

        assert result["published"] is False
        offer = _get_offer(offer_id)
        assert offer.status is OfferStatus.ERROR

        event = _get_audit_event(tenant_id)
        assert event is not None
        assert event.result is AuditResult.FAILURE

    def test_is_a_no_op_when_the_offer_is_not_pending(self, monkeypatch) -> None:
        tenant_id = make_tenant()
        connection_id = make_connection(tenant_id, {"access_token": "tok"})
        offer_id = make_offer_with_price(
            tenant_id,
            connection_id,
            description="A great product",
            external_id="ext-1",
            status=OfferStatus.ACTIVE,
        )

        monkeypatch.setattr(
            "worker.tasks.listing.build_connector",
            lambda connection, credentials: (_ for _ in ()).throw(AssertionError("should not run")),
        )

        result = publish_listing_to_marketplace.run(str(tenant_id), str(offer_id))

        assert result["published"] is False
        offer = _get_offer(offer_id)
        assert offer.status is OfferStatus.ACTIVE

    def test_raises_for_missing_offer(self) -> None:
        tenant_id = make_tenant()

        with pytest.raises(ValueError, match="not found"):
            publish_listing_to_marketplace.run(str(tenant_id), str(uuid.uuid4()))
