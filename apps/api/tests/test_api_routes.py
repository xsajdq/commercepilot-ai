import uuid
from datetime import UTC, datetime

import pytest
from cp_domain.ai_job import AIJob, AIJobStatus
from cp_domain.offer import Offer, OfferStatus
from cp_domain.recommendation import RecommendationType, RiskLevel
from cp_policies import propose_recommendation, submit_for_approval
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio(loop_scope="session")

ALICE = {
    "email": "alice@example.com",
    "password": "supersecret123",
    "full_name": "Alice A",
    "tenant_name": "Alice Shop",
}
BOB = {
    "email": "bob@example.com",
    "password": "supersecret123",
    "full_name": "Bob B",
    "tenant_name": "Bob Shop",
}


async def _register(client: AsyncClient, payload: dict) -> str:
    response = await client.post("/auth/register", json=payload)
    assert response.status_code == 201, response.text
    return response.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


class TestConnectionsRoutes:
    async def test_create_and_list_connections(self, client: AsyncClient) -> None:
        token = await _register(client, ALICE)

        create = await client.post(
            "/connections",
            json={"platform": "woocommerce", "name": "My Store", "credentials": {}},
            headers=_auth(token),
        )
        assert create.status_code == 201, create.text
        connection = create.json()
        assert connection["platform"] == "woocommerce"
        assert connection["status"] == "connected"

        listed = await client.get("/connections", headers=_auth(token))
        assert listed.status_code == 200
        assert [c["id"] for c in listed.json()] == [connection["id"]]

    async def test_duplicate_connection_name_conflicts(self, client: AsyncClient) -> None:
        token = await _register(client, ALICE)
        payload = {"platform": "woocommerce", "name": "Dup", "credentials": {}}
        await client.post("/connections", json=payload, headers=_auth(token))

        second = await client.post("/connections", json=payload, headers=_auth(token))
        assert second.status_code == 409

    async def test_tenant_isolation(self, client: AsyncClient) -> None:
        alice_token = await _register(client, ALICE)
        bob_token = await _register(client, BOB)
        await client.post(
            "/connections",
            json={"platform": "woocommerce", "name": "Alice Store", "credentials": {}},
            headers=_auth(alice_token),
        )

        bob_list = await client.get("/connections", headers=_auth(bob_token))
        assert bob_list.json() == []

    async def test_sync_triggers_a_task_for_an_existing_connection(
        self, client: AsyncClient
    ) -> None:
        token = await _register(client, ALICE)
        create = await client.post(
            "/connections",
            json={"platform": "woocommerce", "name": "My Store", "credentials": {}},
            headers=_auth(token),
        )
        connection_id = create.json()["id"]

        result = await client.post(f"/connections/{connection_id}/sync", headers=_auth(token))

        assert result.status_code == 200, result.text
        assert result.json()["task_id"]

    async def test_sync_unknown_connection_404s(self, client: AsyncClient) -> None:
        token = await _register(client, ALICE)
        result = await client.post(
            "/connections/00000000-0000-0000-0000-000000000000/sync", headers=_auth(token)
        )
        assert result.status_code == 404


class TestProductsRoutes:
    async def _connection(self, client: AsyncClient, token: str) -> str:
        response = await client.post(
            "/connections",
            json={"platform": "woocommerce", "name": "My Store", "credentials": {}},
            headers=_auth(token),
        )
        return response.json()["id"]

    async def test_create_and_list_products(self, client: AsyncClient) -> None:
        token = await _register(client, ALICE)
        connection_id = await self._connection(client, token)

        create = await client.post(
            "/products",
            json={
                "connection_id": connection_id,
                "sku": "SKU-1",
                "name": "Running Shoe",
                "cost": "60.00",
                "price_amount": "99.99",
                "stock_quantity": 10,
            },
            headers=_auth(token),
        )
        assert create.status_code == 201, create.text
        product = create.json()
        assert product["sku"] == "SKU-1"
        [offer] = product["offers"]
        assert offer["price_amount"] == "99.99"
        assert offer["stock_quantity"] == 10

        listed = await client.get("/products", headers=_auth(token))
        assert len(listed.json()) == 1

    async def test_duplicate_sku_conflicts(self, client: AsyncClient) -> None:
        token = await _register(client, ALICE)
        connection_id = await self._connection(client, token)
        payload = {
            "connection_id": connection_id,
            "sku": "SKU-DUP",
            "name": "Thing",
            "price_amount": "10.00",
        }
        await client.post("/products", json=payload, headers=_auth(token))

        second = await client.post("/products", json=payload, headers=_auth(token))
        assert second.status_code == 409

    async def test_create_product_rejects_unknown_connection(self, client: AsyncClient) -> None:
        token = await _register(client, ALICE)
        response = await client.post(
            "/products",
            json={
                "connection_id": "00000000-0000-0000-0000-000000000000",
                "sku": "SKU-1",
                "name": "Thing",
                "price_amount": "10.00",
            },
            headers=_auth(token),
        )
        assert response.status_code == 404

    async def test_tenant_isolation(self, client: AsyncClient) -> None:
        alice_token = await _register(client, ALICE)
        bob_token = await _register(client, BOB)
        connection_id = await self._connection(client, alice_token)
        await client.post(
            "/products",
            json={
                "connection_id": connection_id,
                "sku": "SKU-1",
                "name": "Thing",
                "price_amount": "10.00",
            },
            headers=_auth(alice_token),
        )

        bob_list = await client.get("/products", headers=_auth(bob_token))
        assert bob_list.json() == []

    async def test_generate_content_recommendation_triggers_a_task(
        self, client: AsyncClient
    ) -> None:
        token = await _register(client, ALICE)
        connection_id = await self._connection(client, token)
        create = await client.post(
            "/products",
            json={
                "connection_id": connection_id,
                "sku": "SKU-1",
                "name": "Thing",
                "price_amount": "10.00",
            },
            headers=_auth(token),
        )
        product_id = create.json()["id"]

        result = await client.post(
            f"/products/{product_id}/generate-content-recommendation", headers=_auth(token)
        )

        assert result.status_code == 200, result.text
        assert result.json()["task_id"]

    async def test_generate_pricing_recommendation_triggers_a_task(
        self, client: AsyncClient
    ) -> None:
        token = await _register(client, ALICE)
        connection_id = await self._connection(client, token)
        create = await client.post(
            "/products",
            json={
                "connection_id": connection_id,
                "sku": "SKU-1",
                "name": "Thing",
                "cost": "5.00",
                "price_amount": "10.00",
            },
            headers=_auth(token),
        )
        offer_id = create.json()["offers"][0]["id"]

        result = await client.post(
            f"/offers/{offer_id}/generate-pricing-recommendation", headers=_auth(token)
        )

        assert result.status_code == 200, result.text
        assert result.json()["task_id"]

    async def test_generate_pricing_recommendation_for_unknown_offer_404s(
        self, client: AsyncClient
    ) -> None:
        token = await _register(client, ALICE)
        result = await client.post(
            "/offers/00000000-0000-0000-0000-000000000000/generate-pricing-recommendation",
            headers=_auth(token),
        )
        assert result.status_code == 404

    async def test_generate_listing_publish_recommendation_triggers_a_task(
        self, client: AsyncClient
    ) -> None:
        token = await _register(client, ALICE)
        connection_id = await self._connection(client, token)
        create = await client.post(
            "/products",
            json={
                "connection_id": connection_id,
                "sku": "SKU-1",
                "name": "Thing",
                "price_amount": "10.00",
            },
            headers=_auth(token),
        )
        offer_id = create.json()["offers"][0]["id"]

        result = await client.post(
            f"/offers/{offer_id}/generate-listing-publish-recommendation", headers=_auth(token)
        )

        assert result.status_code == 200, result.text
        assert result.json()["task_id"]

    async def test_generate_listing_publish_recommendation_for_unknown_offer_404s(
        self, client: AsyncClient
    ) -> None:
        token = await _register(client, ALICE)
        result = await client.post(
            "/offers/00000000-0000-0000-0000-000000000000/generate-listing-publish-recommendation",
            headers=_auth(token),
        )
        assert result.status_code == 404

    async def _product(self, client: AsyncClient, token: str) -> str:
        connection_id = await self._connection(client, token)
        create = await client.post(
            "/products",
            json={
                "connection_id": connection_id,
                "sku": "COMP-SKU",
                "name": "Thing",
                "price_amount": "10.00",
            },
            headers=_auth(token),
        )
        return create.json()["id"]

    async def test_create_and_list_competitor_prices(self, client: AsyncClient) -> None:
        token = await _register(client, ALICE)
        product_id = await self._product(client, token)

        create = await client.post(
            f"/products/{product_id}/competitor-prices",
            json={"competitor_name": "Rival Store", "price": "89.99", "url": "https://rival.example.com"},
            headers=_auth(token),
        )

        assert create.status_code == 201, create.text
        body = create.json()
        assert body["competitor_name"] == "Rival Store"
        assert body["price"] == "89.99"
        assert body["source"] == "manual"
        assert body["url"] == "https://rival.example.com"

        listed = await client.get(
            f"/products/{product_id}/competitor-prices", headers=_auth(token)
        )
        assert listed.status_code == 200
        assert len(listed.json()) == 1

    async def test_competitor_price_must_be_positive(self, client: AsyncClient) -> None:
        token = await _register(client, ALICE)
        product_id = await self._product(client, token)

        result = await client.post(
            f"/products/{product_id}/competitor-prices",
            json={"competitor_name": "Rival Store", "price": "-5.00"},
            headers=_auth(token),
        )

        assert result.status_code == 422

    async def test_competitor_prices_for_unknown_product_404s(self, client: AsyncClient) -> None:
        token = await _register(client, ALICE)

        create = await client.post(
            "/products/00000000-0000-0000-0000-000000000000/competitor-prices",
            json={"competitor_name": "Rival Store", "price": "10.00"},
            headers=_auth(token),
        )
        listed = await client.get(
            "/products/00000000-0000-0000-0000-000000000000/competitor-prices",
            headers=_auth(token),
        )

        assert create.status_code == 404
        assert listed.status_code == 404

    async def test_competitor_prices_are_tenant_isolated(self, client: AsyncClient) -> None:
        alice_token = await _register(client, ALICE)
        product_id = await self._product(client, alice_token)
        await client.post(
            f"/products/{product_id}/competitor-prices",
            json={"competitor_name": "Rival Store", "price": "10.00"},
            headers=_auth(alice_token),
        )

        bob_token = await _register(client, BOB)
        bob_list = await client.get(
            f"/products/{product_id}/competitor-prices", headers=_auth(bob_token)
        )

        assert bob_list.status_code == 404


class TestRecommendationsRoutes:
    async def _setup_product_and_recommendation(
        self, client: AsyncClient, db_session: AsyncSession, token: str, tenant_id
    ):
        connection = await client.post(
            "/connections",
            json={"platform": "woocommerce", "name": "My Store", "credentials": {}},
            headers=_auth(token),
        )
        connection_id = connection.json()["id"]
        product = await client.post(
            "/products",
            json={
                "connection_id": connection_id,
                "sku": "SKU-1",
                "name": "Thing",
                "price_amount": "100.00",
            },
            headers=_auth(token),
        )
        offer_id = product.json()["offers"][0]["id"]

        recommendation = await propose_recommendation(
            db_session,
            tenant_id=uuid.UUID(tenant_id),
            type=RecommendationType.PRICE_CHANGE,
            risk_level=RiskLevel.HIGH,
            entity_type="offer",
            entity_id=uuid.UUID(offer_id),
            title="Lower price",
            tool_name="update_price",
            tool_arguments={"offer_id": offer_id, "new_amount": "80.00"},
        )
        await submit_for_approval(db_session, recommendation)
        return recommendation.id, offer_id

    async def test_list_recommendations_filters_by_status(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        token = await _register(client, ALICE)
        me = await client.get("/auth/me", headers=_auth(token))
        tenant_id = me.json()["tenant"]["id"]

        await self._setup_product_and_recommendation(client, db_session, token, tenant_id)

        pending = await client.get(
            "/recommendations", params={"status": "pending_approval"}, headers=_auth(token)
        )
        assert pending.status_code == 200
        assert len(pending.json()) == 1

        approved = await client.get(
            "/recommendations", params={"status": "approved"}, headers=_auth(token)
        )
        assert approved.json() == []

    async def test_approve_executes_the_tool_and_returns_success(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        token = await _register(client, ALICE)
        me = await client.get("/auth/me", headers=_auth(token))
        tenant_id = me.json()["tenant"]["id"]
        recommendation_id, _offer_id = await self._setup_product_and_recommendation(
            client, db_session, token, tenant_id
        )

        result = await client.post(
            f"/recommendations/{recommendation_id}/approve", json={}, headers=_auth(token)
        )

        assert result.status_code == 200, result.text
        assert result.json()["status"] == "success"

        products = await client.get("/products", headers=_auth(token))
        assert products.json()[0]["offers"][0]["price_amount"] == "80.00"

    async def test_reject_leaves_the_price_untouched(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        token = await _register(client, ALICE)
        me = await client.get("/auth/me", headers=_auth(token))
        tenant_id = me.json()["tenant"]["id"]
        recommendation_id, _offer_id = await self._setup_product_and_recommendation(
            client, db_session, token, tenant_id
        )

        result = await client.post(
            f"/recommendations/{recommendation_id}/reject",
            json={"decision_reason": "not needed"},
            headers=_auth(token),
        )

        assert result.status_code == 200, result.text
        assert result.json()["status"] == "rejected"

        products = await client.get("/products", headers=_auth(token))
        assert products.json()[0]["offers"][0]["price_amount"] == "100.00"

    async def test_approve_unknown_recommendation_404s(self, client: AsyncClient) -> None:
        token = await _register(client, ALICE)
        result = await client.post(
            "/recommendations/00000000-0000-0000-0000-000000000000/approve",
            json={},
            headers=_auth(token),
        )
        assert result.status_code == 404

    async def test_approve_twice_conflicts(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        token = await _register(client, ALICE)
        me = await client.get("/auth/me", headers=_auth(token))
        tenant_id = me.json()["tenant"]["id"]
        recommendation_id, _offer_id = await self._setup_product_and_recommendation(
            client, db_session, token, tenant_id
        )

        await client.post(
            f"/recommendations/{recommendation_id}/approve", json={}, headers=_auth(token)
        )
        second = await client.post(
            f"/recommendations/{recommendation_id}/approve", json={}, headers=_auth(token)
        )

        assert second.status_code == 409

    async def test_tenant_isolation(self, client: AsyncClient, db_session: AsyncSession) -> None:
        alice_token = await _register(client, ALICE)
        me = await client.get("/auth/me", headers=_auth(alice_token))
        tenant_id = me.json()["tenant"]["id"]
        recommendation_id, _offer_id = await self._setup_product_and_recommendation(
            client, db_session, alice_token, tenant_id
        )
        bob_token = await _register(client, BOB)

        bob_list = await client.get("/recommendations", headers=_auth(bob_token))
        assert bob_list.json() == []

        bob_approve = await client.post(
            f"/recommendations/{recommendation_id}/approve", json={}, headers=_auth(bob_token)
        )
        assert bob_approve.status_code == 404

    async def _setup_listing_publish_recommendation(
        self, client: AsyncClient, db_session: AsyncSession, token: str, tenant_id
    ):
        connection = await client.post(
            "/connections",
            json={"platform": "allegro", "name": "My Allegro", "credentials": {}},
            headers=_auth(token),
        )
        connection_id = connection.json()["id"]
        product = await client.post(
            "/products",
            json={
                "connection_id": connection_id,
                "sku": "SKU-1",
                "name": "Thing",
                "price_amount": "100.00",
            },
            headers=_auth(token),
        )
        offer_id = product.json()["offers"][0]["id"]

        # /products creates a purely local offer (no marketplace presence
        # yet) - a listing_publish recommendation only ever targets an
        # offer that already exists as a draft on the marketplace, so
        # give it the external_id a real sync would have set.
        offer = await db_session.get(Offer, uuid.UUID(offer_id))
        offer.external_id = "ext-1"
        await db_session.commit()

        recommendation = await propose_recommendation(
            db_session,
            tenant_id=uuid.UUID(tenant_id),
            type=RecommendationType.LISTING_PUBLISH,
            risk_level=RiskLevel.HIGH,
            entity_type="offer",
            entity_id=uuid.UUID(offer_id),
            title="Publish SKU-1",
            tool_name="request_listing_publish",
            tool_arguments={"offer_id": offer_id},
        )
        await submit_for_approval(db_session, recommendation)
        return recommendation.id, offer_id

    async def test_approving_a_listing_publish_recommendation_enqueues_the_publish_task(
        self, client: AsyncClient, db_session: AsyncSession, monkeypatch
    ) -> None:
        sent_tasks = []

        class _FakeAsyncResult:
            id = "fake-task-id"

        class _FakeCeleryClient:
            def send_task(self, name, args):
                sent_tasks.append((name, args))
                return _FakeAsyncResult()

        monkeypatch.setattr(
            "app.api.routes.recommendations.get_celery_client", lambda: _FakeCeleryClient()
        )

        token = await _register(client, ALICE)
        me = await client.get("/auth/me", headers=_auth(token))
        tenant_id = me.json()["tenant"]["id"]
        recommendation_id, offer_id = await self._setup_listing_publish_recommendation(
            client, db_session, token, tenant_id
        )

        result = await client.post(
            f"/recommendations/{recommendation_id}/approve", json={}, headers=_auth(token)
        )

        assert result.status_code == 200, result.text
        assert result.json()["status"] == "success"
        assert sent_tasks == [("worker.publish_listing_to_marketplace", [tenant_id, offer_id])]

        offer = await db_session.scalar(select(Offer).where(Offer.id == uuid.UUID(offer_id)))
        assert offer.status is OfferStatus.PENDING

    async def test_approving_a_price_change_does_not_enqueue_the_publish_task(
        self, client: AsyncClient, db_session: AsyncSession, monkeypatch
    ) -> None:
        sent_tasks = []

        class _FakeAsyncResult:
            id = "fake-task-id"

        class _FakeCeleryClient:
            def send_task(self, name, args):
                sent_tasks.append((name, args))
                return _FakeAsyncResult()

        monkeypatch.setattr(
            "app.api.routes.recommendations.get_celery_client", lambda: _FakeCeleryClient()
        )

        token = await _register(client, ALICE)
        me = await client.get("/auth/me", headers=_auth(token))
        tenant_id = me.json()["tenant"]["id"]
        recommendation_id, _offer_id = await self._setup_product_and_recommendation(
            client, db_session, token, tenant_id
        )

        result = await client.post(
            f"/recommendations/{recommendation_id}/approve", json={}, headers=_auth(token)
        )

        assert result.status_code == 200, result.text
        assert sent_tasks == []


class TestCatalogRoutes:
    async def test_trigger_audit_returns_a_task_id(self, client: AsyncClient) -> None:
        token = await _register(client, ALICE)

        result = await client.post("/catalog/audit", headers=_auth(token))

        assert result.status_code == 200, result.text
        assert result.json()["task_id"]

    async def test_list_audits_returns_completed_runs(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        token = await _register(client, ALICE)
        me = await client.get("/auth/me", headers=_auth(token))
        tenant_id = uuid.UUID(me.json()["tenant"]["id"])

        job = AIJob(
            tenant_id=tenant_id,
            agent_type="catalog",
            status=AIJobStatus.SUCCEEDED,
            started_at=datetime.now(UTC),
            finished_at=datetime.now(UTC),
            output_payload={
                "products_scanned": 3,
                "recommendations_proposed": 1,
                "issues": [
                    {
                        "type": "missing_price",
                        "severity": "high",
                        "entity_type": "offer",
                        "entity_id": str(uuid.uuid4()),
                        "sku": "SKU-1",
                        "message": "SKU-1 has an offer with no price set",
                    }
                ],
            },
        )
        db_session.add(job)
        await db_session.commit()

        result = await client.get("/catalog/audits", headers=_auth(token))

        assert result.status_code == 200, result.text
        [audit] = result.json()
        assert audit["status"] == "succeeded"
        assert audit["products_scanned"] == 3
        assert audit["recommendations_proposed"] == 1
        assert len(audit["issues"]) == 1
        assert audit["issues"][0]["type"] == "missing_price"

    async def test_list_audits_is_empty_with_no_runs_yet(self, client: AsyncClient) -> None:
        token = await _register(client, ALICE)

        result = await client.get("/catalog/audits", headers=_auth(token))

        assert result.status_code == 200
        assert result.json() == []

    async def test_tenant_isolation(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        alice_token = await _register(client, ALICE)
        me = await client.get("/auth/me", headers=_auth(alice_token))
        alice_tenant_id = uuid.UUID(me.json()["tenant"]["id"])

        db_session.add(
            AIJob(tenant_id=alice_tenant_id, agent_type="catalog", status=AIJobStatus.SUCCEEDED)
        )
        await db_session.commit()

        bob_token = await _register(client, BOB)
        bob_list = await client.get("/catalog/audits", headers=_auth(bob_token))

        assert bob_list.json() == []


class TestAnalyticsRoutes:
    async def test_dashboard_is_zeroed_for_a_fresh_tenant(self, client: AsyncClient) -> None:
        token = await _register(client, ALICE)

        result = await client.get("/analytics/dashboard", headers=_auth(token))

        assert result.status_code == 200, result.text
        body = result.json()
        assert body["total_products"] == 0
        assert body["total_offers"] == 0
        assert body["total_catalog_value"] == "0"
        assert body["average_margin_rate"] is None
        assert body["recommendations_by_status"] == {}

    async def test_dashboard_reflects_a_real_product(self, client: AsyncClient) -> None:
        token = await _register(client, ALICE)
        connection = await client.post(
            "/connections",
            json={"platform": "woocommerce", "name": "My Store", "credentials": {}},
            headers=_auth(token),
        )
        await client.post(
            "/products",
            json={
                "connection_id": connection.json()["id"],
                "sku": "SKU-1",
                "name": "Thing",
                "cost": "50.00",
                "price_amount": "100.00",
                "stock_quantity": 4,
            },
            headers=_auth(token),
        )

        result = await client.get("/analytics/dashboard", headers=_auth(token))

        body = result.json()
        assert body["total_products"] == 1
        assert body["total_offers"] == 1
        assert body["total_catalog_value"] == "400.00"
        assert body["average_margin_rate"] == "0.5"

    async def test_trigger_narrative_returns_a_task_id(self, client: AsyncClient) -> None:
        token = await _register(client, ALICE)

        result = await client.post("/analytics/narrative", headers=_auth(token))

        assert result.status_code == 200, result.text
        assert result.json()["task_id"]

    async def test_list_narratives_returns_completed_runs(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        token = await _register(client, ALICE)
        me = await client.get("/auth/me", headers=_auth(token))
        tenant_id = uuid.UUID(me.json()["tenant"]["id"])

        job = AIJob(
            tenant_id=tenant_id,
            agent_type="analytics",
            status=AIJobStatus.SUCCEEDED,
            started_at=datetime.now(UTC),
            finished_at=datetime.now(UTC),
            output_payload={
                "metrics": {
                    "total_products": 3,
                    "products_by_status": {"active": 3},
                    "total_offers": 3,
                    "offers_missing_price": 0,
                    "out_of_stock_offers": 0,
                    "total_catalog_value": "150.00",
                    "average_margin_rate": "0.4",
                    "recommendations_by_status": {},
                    "recommendations_by_type": {},
                    "latest_catalog_issue_count": None,
                },
                "narrative": {
                    "summary": "Store is healthy.",
                    "highlights": ["Everything looks fine"],
                },
            },
        )
        db_session.add(job)
        await db_session.commit()

        result = await client.get("/analytics/narratives", headers=_auth(token))

        assert result.status_code == 200, result.text
        [report] = result.json()
        assert report["status"] == "succeeded"
        assert report["metrics"]["total_products"] == 3
        assert report["narrative"]["summary"] == "Store is healthy."

    async def test_list_narratives_is_empty_with_no_runs_yet(self, client: AsyncClient) -> None:
        token = await _register(client, ALICE)

        result = await client.get("/analytics/narratives", headers=_auth(token))

        assert result.status_code == 200
        assert result.json() == []

    async def test_tenant_isolation(self, client: AsyncClient, db_session: AsyncSession) -> None:
        alice_token = await _register(client, ALICE)
        me = await client.get("/auth/me", headers=_auth(alice_token))
        alice_tenant_id = uuid.UUID(me.json()["tenant"]["id"])

        db_session.add(
            AIJob(tenant_id=alice_tenant_id, agent_type="analytics", status=AIJobStatus.SUCCEEDED)
        )
        await db_session.commit()

        bob_token = await _register(client, BOB)
        bob_list = await client.get("/analytics/narratives", headers=_auth(bob_token))

        assert bob_list.json() == []
