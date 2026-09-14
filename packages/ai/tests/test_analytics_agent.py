from decimal import Decimal

from cp_analytics import DashboardMetrics

from cp_ai.agents.analytics_agent import build_dashboard_narrative
from cp_ai.providers import FakeAIProvider


def _metrics(**overrides) -> DashboardMetrics:
    defaults = dict(
        total_products=10,
        products_by_status={"active": 8, "draft": 2},
        total_offers=10,
        offers_missing_price=1,
        out_of_stock_offers=2,
        total_catalog_value=Decimal("5000.00"),
        average_margin_rate=Decimal("0.32"),
        recommendations_by_status={"pending_approval": 3},
        recommendations_by_type={"price_change": 2, "catalog_fix": 1},
        latest_catalog_issue_count=5,
    )
    defaults.update(overrides)
    return DashboardMetrics(**defaults)


class TestBuildDashboardNarrative:
    async def test_builds_a_narrative_from_the_provider_response(self) -> None:
        provider = FakeAIProvider(
            {
                "summary": "Your store is healthy overall, with a few pricing gaps.",
                "highlights": ["1 offer has no price", "2 offers are out of stock"],
            }
        )

        narrative = await build_dashboard_narrative(provider=provider, metrics=_metrics())

        assert narrative.summary == "Your store is healthy overall, with a few pricing gaps."
        assert narrative.highlights == [
            "1 offer has no price",
            "2 offers are out of stock",
        ]

    async def test_prompt_includes_the_real_computed_numbers(self) -> None:
        provider = FakeAIProvider({"summary": "s", "highlights": []})

        await build_dashboard_narrative(
            provider=provider, metrics=_metrics(total_products=42, out_of_stock_offers=7)
        )

        [call] = provider.calls
        assert "42" in call.user_prompt
        assert "7" in call.user_prompt
        assert call.schema_name == "dashboard_narrative"

    async def test_prompt_forbids_inventing_beyond_the_given_metrics(self) -> None:
        provider = FakeAIProvider({"summary": "s", "highlights": []})

        await build_dashboard_narrative(provider=provider, metrics=_metrics())

        [call] = provider.calls
        assert "never invent" in call.system_prompt.lower()
