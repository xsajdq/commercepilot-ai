import asyncio
import uuid
from decimal import Decimal

from cp_domain.ai_job import AIJob, AIJobStatus
from cp_domain.product import ProductStatus
from cp_domain.recommendation import Recommendation, RecommendationStatus, RecommendationType
from sqlalchemy import func, select

from tests.conftest import make_connection, make_offer_with_price, make_product, make_tenant
from worker.db import async_session_factory
from worker.tasks.catalog import run_catalog_audit


def _get_job(job_id: str) -> AIJob:
    async def _run() -> AIJob:
        async with async_session_factory() as db:
            return await db.get(AIJob, uuid.UUID(job_id))

    return asyncio.run(_run())


def _count_recommendations() -> int:
    async def _run() -> int:
        async with async_session_factory() as db:
            return await db.scalar(select(func.count()).select_from(Recommendation))

    return asyncio.run(_run())


class TestRunCatalogAudit:
    def test_scans_zero_products_for_a_fresh_tenant(self) -> None:
        tenant_id = make_tenant()

        result = run_catalog_audit.run(str(tenant_id))

        assert result["products_scanned"] == 0
        assert result["issues_found"] == 0
        assert result["recommendations_proposed"] == 0

        job = _get_job(result["job_id"])
        assert job.status is AIJobStatus.SUCCEEDED
        assert job.agent_type == "catalog"
        assert job.output_payload == {
            "products_scanned": 0,
            "recommendations_proposed": 0,
            "issues": [],
        }
        assert job.started_at is not None
        assert job.finished_at is not None

    def test_records_issues_found_across_products(self) -> None:
        tenant_id = make_tenant()
        connection_id = make_connection(tenant_id, {"access_token": "tok"})
        make_offer_with_price(
            tenant_id, connection_id, sku="SKU-1", description=None, price_amount=None
        )

        result = run_catalog_audit.run(str(tenant_id))

        assert result["products_scanned"] == 1
        assert result["issues_found"] >= 2  # missing_description + missing_price (+ missing_ean)

        job = _get_job(result["job_id"])
        issue_types = {i["type"] for i in job.output_payload["issues"]}
        assert "missing_description" in issue_types
        assert "missing_price" in issue_types

    def test_proposes_a_recommendation_for_an_orphan_active_product(self) -> None:
        tenant_id = make_tenant()
        make_product(tenant_id, sku="ORPHAN-1", status=ProductStatus.ACTIVE)

        result = run_catalog_audit.run(str(tenant_id))

        assert result["recommendations_proposed"] == 1

        async def _find():
            async with async_session_factory() as db:
                return await db.scalar(
                    select(Recommendation).where(
                        Recommendation.tenant_id == tenant_id,
                        Recommendation.type == RecommendationType.CATALOG_FIX,
                    )
                )

        recommendation = asyncio.run(_find())
        assert recommendation is not None
        assert recommendation.status is RecommendationStatus.PENDING_APPROVAL
        assert recommendation.payload["tool_name"] == "update_product_status"
        assert recommendation.payload["tool_arguments"] == {
            "sku": "ORPHAN-1",
            "new_status": "archived",
        }

    def test_does_not_propose_for_a_draft_orphan_product(self) -> None:
        tenant_id = make_tenant()
        make_product(tenant_id, sku="DRAFT-1", status=ProductStatus.DRAFT)

        result = run_catalog_audit.run(str(tenant_id))

        assert result["recommendations_proposed"] == 0
        assert _count_recommendations() == 0

    def test_second_run_does_not_duplicate_a_pending_recommendation(self) -> None:
        tenant_id = make_tenant()
        make_product(tenant_id, sku="ORPHAN-1", status=ProductStatus.ACTIVE)

        first = run_catalog_audit.run(str(tenant_id))
        second = run_catalog_audit.run(str(tenant_id))

        assert first["recommendations_proposed"] == 1
        assert second["recommendations_proposed"] == 0
        assert _count_recommendations() == 1

    def test_only_scans_the_calling_tenants_products(self) -> None:
        tenant_a = make_tenant("Tenant A")
        tenant_b = make_tenant("Tenant B")
        make_product(tenant_a, sku="A-1")
        make_product(tenant_b, sku="B-1")
        make_product(tenant_b, sku="B-2")

        result = run_catalog_audit.run(str(tenant_b))

        assert result["products_scanned"] == 2

    def test_price_below_cost_is_flagged(self) -> None:
        tenant_id = make_tenant()
        connection_id = make_connection(tenant_id, {"access_token": "tok"})
        make_offer_with_price(
            tenant_id,
            connection_id,
            sku="LOSS-1",
            description="Fine",
            cost=Decimal("50.00"),
            price_amount=Decimal("30.00"),
        )

        result = run_catalog_audit.run(str(tenant_id))

        job = _get_job(result["job_id"])
        issue_types = {i["type"] for i in job.output_payload["issues"]}
        assert "price_below_cost" in issue_types
