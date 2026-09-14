from cp_analytics import DashboardMetrics
from pydantic import BaseModel

from cp_ai.providers.base import AIProvider, TokenUsage

_SYSTEM_PROMPT = (
    "You are an e-commerce analyst writing a short daily summary for a store owner. "
    "Use ONLY the metrics given below - never invent a number, trend, or fact that "
    "isn't present in them. Write a 2-4 sentence `summary` and 2-4 short "
    "`highlights` bullet points calling out what most needs attention."
)


class DashboardNarrative(BaseModel):
    summary: str
    highlights: list[str]


def _metrics_prompt(metrics: DashboardMetrics) -> str:
    return (
        f"Total products: {metrics.total_products}, by status: {metrics.products_by_status}\n"
        f"Total offers: {metrics.total_offers}, missing price: {metrics.offers_missing_price}, "
        f"out of stock: {metrics.out_of_stock_offers}\n"
        f"Total catalog value: {metrics.total_catalog_value}\n"
        f"Average margin rate: {metrics.average_margin_rate}\n"
        f"Recommendations by status: {metrics.recommendations_by_status}\n"
        f"Recommendations by type: {metrics.recommendations_by_type}\n"
        f"Issues found in the latest catalog audit: {metrics.latest_catalog_issue_count}"
    )


async def build_dashboard_narrative(
    *, provider: AIProvider, metrics: DashboardMetrics
) -> tuple[DashboardNarrative, TokenUsage | None]:
    """Phase 13's "AI narrative" half - turns `cp_analytics`'s
    deterministic `DashboardMetrics` into a short prose summary via
    `AIProvider.generate_structured`. Returns the narrative alongside the
    real token usage for that call (Phase 20: the caller records this on
    the `AIJob` for the cost guard - this function knows nothing about
    billing itself).

    Unlike the product agent (Phase 10), this has no CLAUDE.md #18
    hallucination-override step: every number handed to the model here
    is our own deterministic computation, not untrusted external content
    (a product description, a review, ...) an attacker could steer -
    there's nothing here for the model to be tricked into inventing
    *from*. The prompt still explicitly forbids inventing beyond what's
    given, but that's an ordinary quality instruction, not a security
    boundary this function has to enforce itself the way
    `build_product_content_proposal` enforces `"UNKNOWN"`.

    Read-only: never proposes a `Recommendation`, never targets a tool
    call - this exists purely to narrate, not to act.
    """
    output = await provider.generate_structured(
        system_prompt=_SYSTEM_PROMPT,
        user_prompt=_metrics_prompt(metrics),
        schema=DashboardNarrative.model_json_schema(),
        schema_name="dashboard_narrative",
    )
    return DashboardNarrative.model_validate(output.data), output.usage
