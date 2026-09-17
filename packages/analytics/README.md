# packages/analytics (`cp_analytics`)

Phase 13's deterministic dashboard-metrics engine - plain code, no
dependencies on `cp_domain`, `cp_shared`, or anything async, same
philosophy as `packages/pricing`: a count, a sum, or an average is a
calculation, not a creative judgement, so it stays code (CONTRIBUTING.md #10's
"math is code" spirit, extended here from pricing to reporting). The AI
narrative on top (`cp_ai.agents.analytics_agent`) only ever narrates the
exact numbers this package computes - it never gets to restate or
re-derive them.

## `cp_analytics.compute_dashboard_metrics(*, products, ...) -> DashboardMetrics`

Takes plain, `cp_domain`-free inputs - `ProductMetricsInput` (a
`status` string and a list of `OfferMetricsInput`, each just
`price_amount`/`cost`/`stock_quantity`) - the caller (an app, not this
package) is responsible for extracting these from real `cp_domain` rows,
exactly like `cp_pricing.PricingInputs` keeps that package
dependency-free too.

Returns `DashboardMetrics`: product counts by status, total/missing-price
offer counts, out-of-stock count, `total_catalog_value` (sum of
`price * stock` - only where *both* are known on that offer, never
guessed), `average_margin_rate` (mean of `(price - cost) / price` across
offers where both are known and price is positive - `None`, not `0`,
when no offer qualifies, since `0` would misleadingly read as "no
margin" rather than "no data"), and pass-through recommendation/catalog-
issue counts the caller already has (this function doesn't query
anything itself).

## Where the AI layer picks this up

`cp_ai.agents.analytics_agent.build_dashboard_narrative` (Phase 13, in
`packages/ai`) turns a `DashboardMetrics` into a short natural-language
summary via `AIProvider.generate_structured` - unlike the product
agent's content generation, there's no CONTRIBUTING.md #18 hallucination guard
needed here, because every number it's given is our own deterministic
computation, not untrusted external content an attacker could steer.
`apps/worker`'s `generate_dashboard_narrative` Celery task computes the
metrics, generates the narrative, and stores both together as an
`AIJob`. `apps/api`'s `GET /analytics/dashboard` computes the same
metrics live and synchronously (a fast DB aggregate, not a slow
external call - CONTRIBUTING.md #13 doesn't apply), so the numbers are always
fresh even before anyone asks for a narrative.

Run this package's own tests (pure math, no DB, no other services):

```bash
cd packages/analytics
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest
```
