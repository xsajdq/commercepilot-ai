# packages/pricing (`cp_pricing`)

Phase 9's deterministic pricing engine - plain code, no dependencies on
`cp_domain`, `cp_shared`, or anything async. Per CONTRIBUTING.md #10
("deterministic business calculations must not be delegated to an LLM"),
this is the entire math layer; the AI recommendation on top
(`cp_ai.agents.pricing_agent`) only decides *whether* to propose what
this engine computed, never re-derives the numbers itself.

## `cp_pricing.compute_price_bounds(inputs: PricingInputs) -> PricingResult`

`PricingInputs`: `cost` (required - `UNKNOWN`/`None` costs are the
caller's problem to filter out before calling this, per CONTRIBUTING.md #9),
`vat_rate`/`marketplace_fee_rate`/`payment_fee_rate` (fractions of gross
price, e.g. `0.23` not `23`), `shipping_cost` (absolute, assumes the
common "free shipping to the buyer" model - it's the seller's own cost,
eaten out of margin like any other cost), `target_margin_rate`/
`minimum_margin_rate`, and optionally `competitor_prices`,
`current_stock`, `sales_velocity`.

`PricingResult`: `minimum_price` (protects `minimum_margin_rate`),
`recommended_price` (aimed at `target_margin_rate`, but never priced
above the most expensive visible competitor), `maximum_price` (the
highest visible competitor price, or `None` without competitor data),
`expected_margin` (what `recommended_price` actually delivers),
`reason` (a deterministically-built explanation string - not an LLM
call), and `confidence` (0.1-1.0, reduced for each piece of missing
context: no competitor data, no stock/velocity data, or having to clamp
away from the target price because of competition).

Raises `PricingInfeasibleError` when even `minimum_margin_rate` is
unreachable at *any* price - VAT and the two percentage-based fees
alone already consume too much of revenue. That's a real signal ("this
SKU can't be profitable under these fees"), not a bug to work around;
callers should treat it as `UNKNOWN`/unactionable rather than force a
number.

## Where the AI layer picks this up

`cp_ai.agents.pricing_agent.build_pricing_proposal` (Phase 9, in
`packages/ai`) is the thin layer that turns this engine's output into a
`cp_policies` recommendation: it pulls `Product.cost`/`vat_rate`, calls
`compute_price_bounds`, and - only if there's an actual change worth
proposing - packages it as the exact `update_price` tool call (Phase 7)
a human will later approve (Phase 8). `apps/worker`'s
`generate_price_recommendation` Celery task is what actually runs it
against a real offer and submits the result for approval.

`competitor_prices` sat unused from Phase 9 until Phase 14 - the engine
always accepted it, but nothing ever populated it until
`cp_domain.CompetitorPrice` existed for the Celery task to query. This
package itself needed no changes at all for that to start mattering: it
was built to consume competitor data from day one, and now it actually
does.

Run this package's own tests (pure math, no DB, no other services):

```bash
cd packages/pricing
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest
```
