# packages/billing (`cp_billing`)

Phase 20's deterministic billing math - plain code, zero dependencies
(not even on `cp_domain`), same "math is code" philosophy CONTRIBUTING.md #10
already established for `cp_pricing` and `cp_analytics`. Deciding
whether a tenant is over their AI budget is exactly this kind of
calculation - a comparison, not a judgement call an LLM should make
about its own spend.

## `cp_billing.plans`

`PLAN_AI_BUDGETS`: a monthly AI-spend budget in USD per plan tier
(`FREE`/`STARTER`/`PRO`, plain string constants - our own product
decision, not an external fact, so no CONTRIBUTING.md #9 concern in hardcoding
it). `ai_budget_for_plan(plan)` raises `KeyError` for an unrecognized
plan rather than silently defaulting - a new plan added without updating
this table should fail loudly.

Deliberately plain strings instead of importing `cp_domain.subscription
.PlanTier`: this package stays dependency-free the same way
`cp_pricing.PricingInputs` never imports `cp_domain.Product` either - a
caller translates `PlanTier.value` into these same string keys.

## `cp_billing.cost`

`MODEL_PRICING`: USD-per-million-tokens rate card per `(provider,
model)` pair - a maintained table, not a permanent fact, so it needs
updating whenever a vendor changes pricing (same spirit as
`packages/connectors`' documented "verify against a real store" notes,
just for pricing instead of API schemas). `compute_cost(provider, model,
input_tokens, output_tokens) -> Decimal | None` is a pure calculation
from real token counts (never estimated - see `cp_ai.providers
.TokenUsage`, which only ever carries what a provider's own API response
actually reported); an unrecognized `(provider, model)` pair returns
`None` rather than a guessed number, mirroring `cp_pricing`'s own
`None`-for-unknown convention.

## `cp_billing.guard`

`check_ai_budget(plan, spent_this_period) -> AIBudgetStatus` - a pure
comparison (`budget`, `spent`, `remaining`, `is_exceeded`) with no
knowledge of the database, Celery, or how "this period" was computed.
It doesn't refuse anything itself; `apps/worker`'s cost-guard helper
(the caller) is what actually sums a tenant's real `AIJob.cost_estimate`
rows for the current calendar month and decides whether to skip running
an agent - exactly the same split `cp_pricing.compute_price_bounds` and
its caller (`apps/worker`'s pricing task) already keep between computing
a number and acting on it.

Run this package's own tests (pure math, no DB, no other services):

```bash
cd packages/billing
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest
```
