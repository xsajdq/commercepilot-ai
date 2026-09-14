import asyncio
import uuid
from decimal import Decimal

from cp_ai.providers import FakeAIProvider
from cp_domain.ai_job import AIJob, AIJobStatus
from sqlalchemy import select

from tests.conftest import make_connection, make_offer_with_price, make_product, make_tenant
from worker.db import async_session_factory
from worker.tasks.analytics import generate_dashboard_narrative

_FAKE_RESPONSE = {
    "summary": "Your catalog looks healthy overall.",
    "highlights": ["1 offer is missing a price"],
}


def _get_job(job_id: str) -> AIJob:
    async def _run() -> AIJob:
        async with async_session_factory() as db:
            return await db.get(AIJob, uuid.UUID(job_id))

    return asyncio.run(_run())


class TestGenerateDashboardNarrative:
    def test_computes_metrics_and_narrative_for_a_fresh_tenant(self, monkeypatch) -> None:
        tenant_id = make_tenant()
        monkeypatch.setattr(
            "worker.tasks.analytics._get_provider", lambda: FakeAIProvider(_FAKE_RESPONSE)
        )

        result = generate_dashboard_narrative.run(str(tenant_id))

        assert result["summary"] == "Your catalog looks healthy overall."
        job = _get_job(result["job_id"])
        assert job.status is AIJobStatus.SUCCEEDED
        assert job.agent_type == "analytics"
        assert job.output_payload["metrics"]["total_products"] == 0
        assert job.output_payload["narrative"]["summary"] == "Your catalog looks healthy overall."
        assert job.started_at is not None
        assert job.finished_at is not None

    def test_metrics_reflect_real_products_and_offers(self, monkeypatch) -> None:
        tenant_id = make_tenant()
        monkeypatch.setattr(
            "worker.tasks.analytics._get_provider", lambda: FakeAIProvider(_FAKE_RESPONSE)
        )
        connection_id = make_connection(tenant_id, {"access_token": "tok"})
        make_offer_with_price(
            tenant_id,
            connection_id,
            sku="SKU-1",
            cost=Decimal("50"),
            price_amount=Decimal("100.00"),
        )

        result = generate_dashboard_narrative.run(str(tenant_id))

        job = _get_job(result["job_id"])
        metrics = job.output_payload["metrics"]
        assert metrics["total_products"] == 1
        assert metrics["total_offers"] == 1
        assert metrics["offers_missing_price"] == 0
        assert Decimal(metrics["average_margin_rate"]) == Decimal("0.5")

    def test_only_scans_the_calling_tenants_data(self, monkeypatch) -> None:
        tenant_a = make_tenant("Tenant A")
        tenant_b = make_tenant("Tenant B")
        make_product(tenant_a, sku="A-1")
        make_product(tenant_b, sku="B-1")
        make_product(tenant_b, sku="B-2")
        monkeypatch.setattr(
            "worker.tasks.analytics._get_provider", lambda: FakeAIProvider(_FAKE_RESPONSE)
        )

        result = generate_dashboard_narrative.run(str(tenant_b))

        job = _get_job(result["job_id"])
        assert job.output_payload["metrics"]["total_products"] == 2

    def test_provider_failure_marks_the_job_failed_and_raises(self, monkeypatch) -> None:
        tenant_id = make_tenant()

        class _BoomProvider:
            async def generate_structured(self, **kwargs):
                raise RuntimeError("provider exploded")

        monkeypatch.setattr(
            "worker.tasks.analytics._get_provider", lambda: _BoomProvider()
        )

        try:
            generate_dashboard_narrative.run(str(tenant_id))
            raised = False
        except RuntimeError:
            raised = True

        assert raised is True

        async def _find_job():
            async with async_session_factory() as db:
                return await db.scalar(
                    select(AIJob).where(
                        AIJob.tenant_id == tenant_id, AIJob.agent_type == "analytics"
                    )
                )

        job = asyncio.run(_find_job())
        assert job.status is AIJobStatus.FAILED
        assert "provider exploded" in job.error_message
