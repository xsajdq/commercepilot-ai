import asyncio
import uuid
from decimal import Decimal

from cp_ai.providers import FakeAIProvider, TokenUsage
from cp_domain.ai_job import AIJob, AIJobStatus
from cp_domain.recommendation import Recommendation, RecommendationStatus, RecommendationType
from sqlalchemy import func, select

from tests.conftest import make_ai_job, make_product, make_tenant
from worker.db import async_session_factory
from worker.tasks.product_content import generate_product_content_recommendation


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


_FAKE_RESPONSE = {
    "title": "Amazing Widget",
    "description": "The best widget you will ever own.",
    "bullet_points": ["Durable", "Lightweight", "Affordable"],
    "specifications": {"color": "should be overridden"},
}


class TestGenerateProductContentRecommendation:
    def test_proposes_a_recommendation_from_the_generated_content(self, monkeypatch) -> None:
        tenant_id = make_tenant()
        product_id = make_product(tenant_id, sku="SKU-1")
        monkeypatch.setattr(
            "worker.tasks.product_content._get_provider",
            lambda: FakeAIProvider(_FAKE_RESPONSE),
        )

        result = generate_product_content_recommendation.run(str(tenant_id), str(product_id))

        assert result["proposed"] is True
        recommendation = _get_recommendation(result["recommendation_id"])
        assert recommendation.status is RecommendationStatus.PENDING_APPROVAL
        assert recommendation.type is RecommendationType.CONTENT_UPDATE
        assert recommendation.entity_type == "product"
        assert recommendation.entity_id == product_id
        assert recommendation.payload["tool_name"] == "update_product_content"
        assert recommendation.payload["tool_arguments"]["sku"] == "SKU-1"
        assert recommendation.payload["tool_arguments"]["new_name"] == "Amazing Widget"

    def test_specifications_with_no_source_data_are_forced_to_unknown(self, monkeypatch) -> None:
        tenant_id = make_tenant()
        product_id = make_product(tenant_id, sku="SKU-1")  # no ean/weight/dimensions
        monkeypatch.setattr(
            "worker.tasks.product_content._get_provider",
            lambda: FakeAIProvider(_FAKE_RESPONSE),
        )

        result = generate_product_content_recommendation.run(str(tenant_id), str(product_id))

        recommendation = _get_recommendation(result["recommendation_id"])
        specs = recommendation.payload["tool_arguments"]["new_extra_attributes"]["specifications"]
        assert specs["ean"] == "UNKNOWN"
        assert specs["weight_kg"] == "UNKNOWN"
        # "color" isn't one of the spec fields the agent asked about, so
        # the model's (irrelevant) value for it is simply passed through.
        assert specs["color"] == "should be overridden"

    def test_second_run_does_not_duplicate_a_pending_recommendation(self, monkeypatch) -> None:
        tenant_id = make_tenant()
        product_id = make_product(tenant_id, sku="SKU-1")
        monkeypatch.setattr(
            "worker.tasks.product_content._get_provider",
            lambda: FakeAIProvider(_FAKE_RESPONSE),
        )

        first = generate_product_content_recommendation.run(str(tenant_id), str(product_id))
        second = generate_product_content_recommendation.run(str(tenant_id), str(product_id))

        assert first["proposed"] is True
        assert second["proposed"] is False
        assert "pending" in second["reason"]
        assert _count_recommendations() == 1

    def test_missing_product_is_reported_without_raising(self, monkeypatch) -> None:
        tenant_id = make_tenant()
        monkeypatch.setattr(
            "worker.tasks.product_content._get_provider",
            lambda: FakeAIProvider(_FAKE_RESPONSE),
        )

        result = generate_product_content_recommendation.run(str(tenant_id), str(uuid.uuid4()))

        assert result == {"proposed": False, "reason": "product not found"}

    def test_records_real_token_usage_and_cost_on_the_job(self, monkeypatch) -> None:
        tenant_id = make_tenant()
        product_id = make_product(tenant_id, sku="SKU-1")
        monkeypatch.setattr(
            "worker.tasks.product_content._get_provider",
            lambda: FakeAIProvider(
                _FAKE_RESPONSE, usage=TokenUsage(input_tokens=800, output_tokens=200)
            ),
        )
        monkeypatch.setattr(
            "worker.tasks.product_content.get_anthropic_model", lambda: "claude-sonnet-5"
        )

        result = generate_product_content_recommendation.run(str(tenant_id), str(product_id))

        async def _get_job() -> AIJob:
            async with async_session_factory() as db:
                return await db.get(AIJob, uuid.UUID(result["job_id"]))

        job = asyncio.run(_get_job())
        assert job.status is AIJobStatus.SUCCEEDED
        assert job.agent_type == "product_content"
        assert job.tokens_used == 1000
        assert job.cost_estimate is not None
        assert job.cost_estimate > 0

    def test_blocked_when_the_tenant_is_over_the_free_plan_budget(self, monkeypatch) -> None:
        tenant_id = make_tenant()
        product_id = make_product(tenant_id, sku="SKU-1")
        make_ai_job(tenant_id, cost_estimate=Decimal("1.00"))
        provider = FakeAIProvider(_FAKE_RESPONSE)
        monkeypatch.setattr("worker.tasks.product_content._get_provider", lambda: provider)

        result = generate_product_content_recommendation.run(str(tenant_id), str(product_id))

        assert result["proposed"] is False
        assert "budget exceeded" in result["reason"]
        assert provider.calls == []
        assert _count_recommendations() == 0
