# packages/ai (`cp_ai`)

Phase 7's tool system - the only way an AI agent is ever allowed to
touch anything - plus the agents built on top of it, starting with
Phase 9's pricing agent (deterministic, no real LLM call) and Phase 10's
product agent (the first to actually call one, through the `AIProvider`
abstraction).

## `cp_ai.tools`

The control flow from CONTRIBUTING.md, minus the Policy Engine and the real
Approval workflow (both Phase 8):

```
AI -> Tool -> Validation -> [Policy] -> Risk -> Approval
    -> Execution -> Audit Log
```

- **`ToolContext`** - a tool call's `tenant_id` and actor identity.
  Always constructed by the caller from the authenticated session/AI
  job, never from a tool argument - a tool's `args_model` is refused at
  registration time if it declares a `tenant_id` field at all
  (`UnsafeToolSchemaError`), so there's no argument for even a
  prompt-injected model to smuggle one through (CONTRIBUTING.md #7, #18).
- **`ToolResult`** - `success`/`data`/`error`, plus `entity_type`/
  `entity_id`/`before`/`after` for mutations, which feed straight into
  the `AuditEvent` the executor writes. `ToolResult.pending_approval(...)`
  is what a gated tool call returns instead of running.
- **`ToolSchema`** - one AI-callable tool: name, description, a Pydantic
  `args_model` (also its JSON schema, via `.input_schema()`, for
  handing to an `AIProvider`'s tool-use API), a `ToolPermission`, and the
  `handler` that does the work.
- **`ToolPermission`** - `risk_level` (`LOW`/`MEDIUM`/`HIGH`) and
  `mutates`. `requires_approval` is `True` for anything above `LOW`
  (CONTRIBUTING.md #4). Tracked separately from `mutates` because they answer
  different questions: risk decides whether a human has to sign off
  first; `mutates` decides whether a successful run gets an audit log
  (CONTRIBUTING.md #5) - a high-risk read needs approval but audits nothing,
  a low-risk write is auditable but never blocks.
- **`ToolRegistry`** - registers/looks up tools by name, and produces
  `tool_definitions()` in the name/description/input_schema shape most
  tool-use APIs expect.
- **`ToolExecutor`** - runs the chain above for one `ToolCall`: resolve
  the tool, validate arguments, short-circuit to
  `ToolResult.pending_approval(...)` for anything above `LOW` risk
  (Phase 8 is what turns this into a real `Recommendation`/`Approval`
  row and resumes execution once a human approves it - until then this
  is a hard stop, no handler call, no mutation), otherwise call the
  handler and write an `AuditEvent` if the tool mutates, whether the
  handler succeeded or not. A handler's own exception is caught and
  turned into a failed `ToolResult` - a single bad tool call must never
  crash the caller.

## `cp_ai.tools.builtin`

Concrete tools proving the framework works end to end against real
`cp_domain` data (`register_builtin_tools(registry)` registers all of
them):

- **`get_product`** (`LOW` risk, read-only) - looks up one of the
  caller's products by SKU. Runs immediately, never audited (it's not a
  mutation).
- **`update_price`** (`HIGH` risk, mutates) - changes an offer's price
  in *our own* domain model only. It deliberately does not push the
  change to the marketplace: per CONTRIBUTING.md #2 ("every external mutation
  must go through a typed connector") and #10 ("deterministic business
  calculations... must not be delegated to an LLM"), pushing a real
  price change is the pricing agent's job (Phase 9), built on the
  deterministic pricing engine - not something a generic tool does on an
  AI's say-so. Its only purpose here is to prove the approval gate:
  `ToolExecutor` never lets `update_price_handler` run without Phase 8's
  approval workflow, so calling it through the executor always comes
  back as `requires_approval` with the price untouched.
- **`update_product_content`** (`MEDIUM` risk, mutates) - changes a
  product's name, description, and free-form `extra_attributes` bag
  (bullet points, specifications). `MEDIUM`, not `HIGH`: wrong listing
  copy is a real but lesser mistake than a wrong price, and this is the
  first builtin tool to show risk levels aren't just LOW-or-HIGH. Never
  touches `cost`/`vat_rate`/`ean` - those are real manufacturer data, not
  copy an agent gets to rewrite.
- **`request_listing_publish`** (`HIGH` risk, mutates) - Phase 11's
  tool, and the first one whose approval is meant to reach a real
  marketplace. Its own handler still only touches our own DB
  (`Offer.status`: `DRAFT` -> `PENDING`) - deliberately, since
  `cp_policies.approve()` calls a tool's handler synchronously inside an
  HTTP request handler, and a real network call there would violate
  CONTRIBUTING.md #12/#13. The actual `publish_offer` connector call happens
  in `apps/worker`'s `publish_listing_to_marketplace` Celery task,
  enqueued by apps/api's approve route only after this tool's handler
  has already succeeded - see the roadmap's Phase 11 writeup for the
  full reasoning.
- **`update_product_status`** (`MEDIUM` risk, mutates) - Phase 12's
  tool, changing a product's catalog status (draft/active/archived).
  Backs the catalog agent's one actionable fix: an `ACTIVE` product with
  no offers on any connection gets proposed for archiving. Same risk
  tier as `update_product_content` - a wrong archive is annoying but
  reversible and non-financial.

## `cp_ai.providers`

Phase 10's `AIProvider` abstraction (CONTRIBUTING.md #17: replaceable, never a
vendor SDK hardcoded into business logic):

- **`AIProvider`** - one method, `generate_structured(*, system_prompt,
  user_prompt, schema, schema_name) -> dict`. How a concrete provider
  achieves structured/constrained output (tool-use, function calling,
  `response_format`, ...) is its own concern; callers only see the
  resulting dict, validated by them against their own Pydantic model.
- **`AnthropicProvider`** - the first concrete provider, using
  Anthropic's tool-use mechanism: `schema` becomes a single tool's
  `input_schema` with `tool_choice` forcing exactly that tool, so the
  model's only possible response is a call to it, never free-form text
  to parse. Tested via `httpx.MockTransport` against `anthropic==0.39.0`
  (pinned to a version built on plain `httpx`, not a newer major version
  the SDK has since moved to a different HTTP stack for - no real API
  key or network call needed in tests, same reasoning as the
  WooCommerce/Allegro connectors).
- **`FakeAIProvider`** - the `MockConnector` of this package: returns a
  canned response regardless of the prompt and records every call, for
  testing an agent's own decision logic without a real provider. Lets a
  test hand it a deliberately adversarial/hallucinated response to prove
  an agent enforces CONTRIBUTING.md #9 in code, not merely by asking nicely -
  see the product agent below.

## `cp_ai.agents.pricing_agent`

## `cp_ai.agents.pricing_agent`

Phase 9's pricing agent: `build_pricing_proposal(*, product, price,
offer_id, ...)` decides *whether* a price is worth proposing a change
for and, if so, builds the proposal - it never mutates anything itself.
It pulls `product.cost`/`vat_rate` (converting the stored percentage to
a fraction), calls `cp_pricing.compute_price_bounds` (the actual math -
CONTRIBUTING.md #10, this package never re-derives it), and - only when the
computed `recommended_price` differs from the current one and the
margin targets are actually reachable - returns a `PricingProposal`
carrying the exact `update_price` tool call (`tool_name`/
`tool_arguments`) a human will later approve, with its `risk_level`
read directly off `update_price_tool()`'s own permission so the two can
never silently drift apart. Returns `None` (nothing to propose) when
`cost` is `UNKNOWN`, the margin is unreachable
(`PricingInfeasibleError`), or the price is already right.

`apps/worker`'s `generate_price_recommendation` Celery task is what
actually runs this against a real `Offer`/`Price`/`Product` and, if it
gets a proposal back, hands it to `cp_policies.propose_recommendation` +
`submit_for_approval` - closing the loop from deterministic math all the
way to a human's approval queue.

## `cp_ai.agents.product_agent`

Phase 10's product agent: `build_product_content_proposal(*, provider,
product, ...)` generates a title/description/bullet points via
`AIProvider.generate_structured` and, only for specification fields the
product actually has source data for (`ean`, `weight_kg`,
`dimensions_cm`, plus anything already in `extra_attributes`), lets the
model's value through. For every other spec field, the literal string
`"UNKNOWN"` is written into the result **in this function, after the
call returns** - overwriting whatever the model said, even if it
returned a plausible-looking value.

That overwrite is the load-bearing part. `product.description` is fed
into the prompt as context, and it's untrusted external content per
CONTRIBUTING.md #18 - potentially synced from a marketplace listing an
attacker controls, and possibly containing text trying to steer the
model into inventing a spec value it has no basis for. The system prompt
asks the model not to; this function does not trust that it complied.
`packages/ai/tests/test_product_agent.py` proves this directly: a
`FakeAIProvider` is handed a response that *does* invent a value for an
unknown field (simulating a model that either hallucinated or was
successfully steered), and the assertion is that the final proposal
still shows `"UNKNOWN"` there - the guarantee holds structurally, not
because the fake happened to behave.

`apps/worker`'s `generate_product_content_recommendation` Celery task
runs this against a real `Product` (via `AnthropicProvider` in
production) and, like the pricing agent, hands the result to
`cp_policies.propose_recommendation` + `submit_for_approval`.

## `cp_ai.agents.listing_agent`

Phase 11's listing agent: `build_listing_publish_proposal(*, offer,
product, price)` decides whether a draft marketplace listing is ready to
go live - like the pricing agent, no `AIProvider` call happens here,
since "is this ready" is a checklist against data already on hand, not a
creative judgement. Returns `None` unless all of: the offer already
exists on the marketplace (`external_id` set - creating it there in the
first place is a sync/push concern, not this agent's), it's still
`DRAFT`, the product has a real name and description (the product
agent's job, Phase 10), and it has been priced. Otherwise returns a
`ListingPublishProposal` carrying the exact `request_listing_publish`
tool call, with `risk_level` read off that tool's own permission the
same way the pricing agent does for `update_price`.

`apps/worker`'s `generate_listing_publish_recommendation` Celery task
runs this against a real `Offer`/`Product`/`Price` and hands a proposal
to `cp_policies.propose_recommendation` + `submit_for_approval`, exactly
like the other two agents. What's different about this one is what
happens *after* approval - see `request_listing_publish` above and the
roadmap's Phase 11 writeup: this is the first agent whose approved
action is meant to reach a real marketplace, not just our own DB.

## `cp_ai.agents.catalog_agent`

Phase 12's catalog agent, and unlike every earlier agent it doesn't
operate on one product/offer - `audit_products(products)` scans a
tenant's *entire* catalog and returns a `CatalogAuditReport`: a deterministic
checklist (no `AIProvider` call, same reasoning as pricing/listing) for
missing description, missing EAN, missing price, priced below cost,
missing stock record, out of stock, and an `ACTIVE` product with no
offers on any connection ("orphaned"). Every finding is a `CatalogIssue`
- a plain fact, not a proposal.

`build_catalog_fix_proposals(report)` is the separate, deliberately
narrow step that decides which of those findings get turned into an
actual `Recommendation`: today, only `ORPHAN_PRODUCT` (via
`update_product_status`, archiving it). Every other issue type has no
safe automated fix - a missing price/EAN can't be invented (CONTRIBUTING.md
#9) and a wrong price is the pricing agent's own job, not this one's to
re-derive - so it stays a plain finding, matching
`docs/architecture/product-vision.md`'s own framing that not every
"problem" becomes a "recommendation."

`apps/worker`'s `run_catalog_audit` Celery task runs both functions
against a real tenant's products (eager-loaded via `selectinload`) and
is the first task in this codebase to actually use the `AIJob` table
(`packages/domain/cp_domain/ai_job.py` - scaffolded in Phase 2, unused
until now): one row per run, `output_payload` holding the full
structured issue list, `QUEUED`/`RUNNING`/`SUCCEEDED`/`FAILED` tracking
the run itself independently of any recommendations it proposed.

## `cp_ai.agents.analytics_agent`

Phase 13's analytics agent, split into two deliberately separate layers
per its own roadmap name - "dashboard first, AI narrative second." The
dashboard half, `cp_analytics.compute_dashboard_metrics` (a new sibling
package, `packages/analytics`, with the exact same zero-dependency
philosophy as `cp_pricing`), is pure aggregation: product/offer counts,
total catalog value, average margin rate. This module is the second
half - `build_dashboard_narrative(*, provider, metrics)` turns a
`DashboardMetrics` into a short prose `summary` plus `highlights` via
`AIProvider.generate_structured`.

Unlike the product agent (Phase 10), there's no CONTRIBUTING.md #18
hallucination-override step here: every number handed to the model is
our own deterministic computation, never untrusted external content
(a product description, a review, ...) an attacker could steer - there's
nothing here for the model to be tricked into inventing *from*. Also
unlike every proposal-building agent in this file, this one is entirely
read-only: no tool call, no `Recommendation` - it exists purely to
narrate, not to act.

`apps/worker`'s `generate_dashboard_narrative` Celery task computes the
same metrics `apps/api`'s `GET /analytics/dashboard` computes live and
synchronously, generates the narrative, and stores both together as an
`AIJob` (`agent_type="analytics"` - the second real use of that table,
alongside Phase 12's catalog agent).

Run this package's own tests (registry + executor mechanics and both
agents' decision logic against a mocked `AsyncSession`/`FakeAIProvider`,
plus the `AnthropicProvider` against `httpx.MockTransport` - no real DB,
API key, or network call needed for any of it):

```bash
cd packages/ai
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest
```

DB-integration coverage (tenant isolation, both tools' approval gates
leaving their entities untouched, and real `AuditEvent` rows) lives in
`apps/api/tests/test_ai_tools.py`, reusing that app's Postgres test
fixtures - same reasoning as `packages/sync`.
