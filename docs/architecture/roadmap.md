# Roadmap

Development proceeds in phases. Each phase should be independently
testable and merged before the next begins — never one giant change.

- [x] **Phase 0 — Project bootstrap**: monorepo skeleton, Docker Compose
      stack (Traefik, Next.js, FastAPI, Celery worker + beat, Postgres,
      Redis), env handling, health checks, CI.
- [x] **Phase 1 — Authentication + multi-tenancy**: users, tenants,
      memberships, roles, sessions, JWT + refresh tokens, tenant
      middleware. Gate: a user in Tenant A cannot access Tenant B's data.
- [x] **Phase 2 — Domain model**: Product, Variant, Brand, Category, Offer,
      Price, Stock, Order, Review, Connection, Recommendation, Approval,
      AuditEvent, AIJob. Alembic migrations.
- [x] **Phase 3 — Connector framework**: `CommerceConnector` interface +
      mock connector, tested without any real store.
- [x] **Phase 4 — WooCommerce connector**.
- [x] **Phase 5 — Allegro connector**.
- [x] **Phase 6 — Sync engine**: pagination, retries, rate limits, backoff,
      idempotency, partial failures.
- [x] **Phase 7 — AI tool system**: ToolRegistry, ToolSchema, ToolExecutor,
      ToolPermission, ToolResult.
- [x] **Phase 8 — Approval engine**: Recommendation → PendingApproval →
      Approved/Rejected → Executing → Success workflow.
- [x] **Phase 9 — Pricing agent**: deterministic pricing engine first, AI
      recommendation layer on top.
- [x] **Phase 10 — Product agent**: structured content generation with
      `UNKNOWN` for missing specs.
- [x] **Phase 11 — Listing agent** (Allegro publication workflow).
- [x] **Phase 12 — Catalog agent** (daily catalog health audit).
- [x] **Phase 13 — Analytics agent** (dashboard first, AI narrative second).
- [ ] **Phase 14 — Competition agent** (manual competitors + API sources).
- [ ] **Phase 15 — Recommendations** (daily scheduler tying agents together).
- [ ] **Phase 16 — Dashboard polish**.
- [ ] **Phase 17 — Shoper connector**.
- [ ] **Phase 18 — PrestaShop connector**.
- [ ] **Phase 19 — IdoSell connector** (own research first, don't force the
      WooCommerce-shaped abstraction).
- [ ] **Phase 20 — Billing** (Stripe subscriptions + AI usage/cost guard).
- [ ] **Phase 21 — Production hardening** (backups, monitoring, alerts,
      rate limiting, WAF, secret rotation, load testing, DR).
- [ ] **Phase 22 — Beta** (5 pilot stores: 2 WooCommerce, 2 Allegro-heavy,
      1 complex).

Further-out planning, captured now but not actionable until the phases
it depends on are current: `docs/architecture/product-vision.md` (what
the three demo-worthy workflows are and which phases each needs),
`docs/security/README.md` (the mandatory security test categories -
tenant isolation, secret leakage, prompt injection, tool authorization,
approval bypass), and `docs/architecture/deployment.md` (deploy
pipeline, environments, monitoring). Don't start building against these
directly - check which phase is next above first.

## Status notes

Phase 0 complete: see `docker-compose.yml` for the local stack. `apps/api`
exposes `/health` and `/health/ready` (checks Postgres + Redis
connectivity); `apps/worker` runs Celery + Beat with a `worker.ping` sanity
task; `apps/web` is a minimal Next.js + Tailwind shell.

Phase 1 complete: `apps/api/app/db/models` has `User`, `Tenant`,
`Membership` (role: owner/manager/operator/viewer), and `RefreshToken`,
migrated via Alembic (`alembic.ini` + `migrations/` at the repo root,
`alembic upgrade head` verified upgrade → downgrade → upgrade). Auth lives
in `apps/api/app/auth`: `/auth/register`, `/auth/login` (auto-selects the
tenant on a single membership, otherwise returns the membership list for
the client to choose from), `/auth/refresh` (single-use, rotating refresh
tokens), `/auth/switch-tenant`, `/auth/tenants`, `/auth/me`. The tenant
middleware (`get_current_membership` in `app/auth/dependencies.py`) reads
`tenant_id` only from the signed access token issued at login/switch and
re-verifies it against the `memberships` table on every request — never
from a client-supplied header or param — so a revoked membership or a
forged claim is rejected immediately, not just at the next login. This is
covered by `apps/api/tests/test_auth.py::TestTenantIsolation`, including a
test that re-signs a valid token with a different `tenant_id` claim and
confirms it's still rejected (defense in depth beyond "the app never sends
that value"). Passwords are hashed with `bcrypt` directly (not `passlib`,
whose bcrypt backend-detection code is broken against `bcrypt>=4`).
`apps/web` has minimal `/register`, `/login`, and `/dashboard` pages
exercising the full flow client-side; verified against a live API +
Postgres + Redis with a real Chromium browser (register → dashboard →
logout → login → dashboard → cleared-session redirect). Session tokens
live in `localStorage` for now, which is a pragmatic MVP choice, not a
hardened one - moving to httpOnly cookies is Phase 21 work, not Phase 1.

Phase 2 complete: the e-commerce domain model lives in `packages/domain`
(`cp_domain`) - `Brand`, `Category`, `Product`, `Variant`, `Connection`,
`Offer`, `Price`, `Stock`, `Order`/`OrderItem`, `Review`,
`Recommendation`, `Approval`, `AuditEvent`, `AIJob` - built on a new
`packages/shared` (`cp_shared`) that holds the single SQLAlchemy `Base`
and mixins (`UUIDPrimaryKeyMixin`, `TimestampMixin`, `TenantScopedMixin`)
both it and `apps/api`'s own auth tables register on. Both are installed
as editable local packages (`pip install -e packages/shared -e
packages/domain` - see `apps/api/requirements.txt`); this keeps other
packages able to depend on the domain model without depending on
`apps/api`, per CLAUDE.md's layering.

Design notes: `Offer` is a `Variant` listed on one `Connection`
(store/marketplace account) - `Price`/`Stock` hang off the offer (one row
each, current value only; history lives in `AuditEvent`, written starting
Phase 8). `Connection.encrypted_credentials` is Fernet-encrypted
(`app/core/crypto.py`, a dedicated `ENCRYPTION_KEY` separate from
`SECRET_KEY`) - never plaintext, per CLAUDE.md. Missing manufacturer data
(`ean`, `cost`, `vat_rate`, ...) is nullable/`NULL`, never guessed.
Migration verified upgrade → downgrade → upgrade against real Postgres
(20 tables total with Phase 1's auth tables); 10 new ORM-level tests in
`apps/api/tests/test_domain_models.py` cover cascades, uniqueness
constraints (including that SKUs are unique per-tenant, not globally -
the domain-model equivalent of the tenant-isolation gate), and a check
constraint, plus 3 in `test_crypto.py` for the encryption round-trip.

Phase 3 complete: `packages/connectors` (`cp_connectors`) has the
`CommerceConnector` `Protocol` (`get_products`, `get_product`,
`create_product`, `update_product`, `update_price`, `update_stock`,
`get_categories`, `upload_image`) plus its own DTOs (`ConnectorProduct`,
`ConnectorCategory`, `PriceUpdate`, `StockUpdate`, `UploadedImage`) and
exception hierarchy. Deliberately has no dependency on `cp_domain` or
`cp_shared` - a connector talks to an external API, not our database;
the sync engine (Phase 6) will map between `ConnectorProduct` and
`cp_domain.Product`/`Variant`. `MockConnector` is an in-memory fake
implementing the interface (12 tests in
`packages/connectors/tests/test_mock_connector.py`, run standalone with
no DB/services needed) - proving the interface end to end before any
real platform exists, per CLAUDE.md #16 (an agent must never know or
care which platform, or even whether a real one, it's talking to).

Phase 4 complete: `cp_connectors.WooCommerceConnector` implements
`CommerceConnector` against WooCommerce's REST API v3
(`/wp-json/wc/v3`), via `httpx.AsyncClient` with Consumer Key/Secret auth
(HTTPS only - see the package README for what's deliberately
out of scope: OAuth1.0a for plain HTTP, variable-product variations,
multi-category products). Errors map to the Phase 3 exception hierarchy
(401/403 → `ConnectorAuthError`, 404 → `ConnectorNotFoundError`, 429 →
`ConnectorRateLimitError` with `Retry-After`, else `ConnectorError`) -
retry/backoff orchestration is explicitly left to the Phase 6 sync
engine, not built into the connector itself. Tested (11 new tests) with
`FakeWooCommerceAPI`, an in-memory stand-in for the WooCommerce REST API
driven through `httpx.MockTransport` - still no real store, no new
HTTP-mocking dependency.

Phase 5 complete: `CommerceConnector` gained two methods -
`get_category_parameters` and `publish_offer` - needed because Allegro's
offer model is genuinely different from WooCommerce's: an offer belongs
to a category with its own mandatory attributes, and goes live only
through a distinct publish step rather than being live the moment it's
created. Platforms without either concept (WooCommerce, `MockConnector`)
implement them as empty-list / best-effort no-op rather than omitting
them, so a caller can call both regardless of platform.
`cp_connectors.allegro_oauth` implements the real OAuth2 Authorization
Code flow (`build_authorization_url`, `exchange_code_for_token`,
`refresh_access_token` - Allegro tokens are short-lived, ~12h) - it's
mechanics only, since there's no "connect your Allegro account" HTTP
endpoint yet to trigger the redirect. `cp_connectors.AllegroConnector`
uses an already-issued Bearer token against `api.allegro.pl`: creates
land as drafts (`publication.status=INACTIVE`) until `publish_offer`,
`ConnectorProduct.parameters` carries category parameter values, and
`upload_image` does Allegro's required host-then-reference two-step.
Known simplifications (documented in the package README): no
delivery/shipping template modeling, `get_categories` returns only the
top level, offer descriptions don't round-trip (Allegro's rich-text
"sections" format isn't modeled). Tested (26 new tests, bringing
`packages/connectors` to 49) against `FakeAllegroAPI` and a fake OAuth
token endpoint, both via `httpx.MockTransport`, plus new coverage for
the two Protocol additions on `MockConnector` and `WooCommerceConnector`
- no real Allegro account or sandbox credentials needed anywhere.

Phase 6 complete: new `packages/sync` (`cp_sync`) is the sync engine -
`retry_with_backoff` (hand-rolled exponential backoff with jitter,
honoring `ConnectorRateLimitError.retry_after_seconds`, never retrying
permanent `ConnectorAuthError`/`ConnectorNotFoundError`), a
`connector_factory.build_connector` dispatching `Connection.platform` to
a concrete connector from decrypted credentials, and
`products.sync_products` - the orchestration function pulling every
product from a connector and upserting it into `cp_domain.Product` →
`Variant` → `Offer` → `Price`/`Stock`, matched by each table's existing
unique natural key so re-running a sync never creates duplicates. A page
fetch that exhausts its retries stops the sync early with
`SyncResult.fatal_error` set, without losing products already committed
from earlier pages. Partial failures are isolated **per item via a
SAVEPOINT** (`db.begin_nested()`) rather than a full session rollback -
the latter was tried first and reliably corrupted the async session for
the *next* item (`MissingGreenlet` on its very next query), which is
exactly the "partial failures must not abort a whole sync" case Phase 6
scoped in. `apps/worker` gained its own DB layer (`worker/db.py`, a
`NullPool` engine - a pooled one breaks across the fresh event loop each
Celery task invocation gets via `asyncio.run`) and the
`worker.sync_connection` Celery task, which loads a `Connection`
scoped to the caller's `tenant_id`, decrypts its credentials
(`cp_shared.crypto`), builds the connector, and runs `sync_products`.
Credentials are decrypted only inside the worker process, in memory, for
the duration of one sync - never logged, never persisted plaintext.
Tested: `packages/sync`'s own 11 tests (retry + connector factory, no DB
needed), 9 new DB-integration tests in `apps/api/tests/test_sync_products.py`
(idempotency, cross-connection SKU sharing, pagination, transient-error
retry, exhausted-retry fatal error without losing prior data, the
partial-failure fix) bringing `apps/api` to 42, and 3 new
`apps/worker/tests/test_sync_task.py` tests against a real Postgres
(worker's test suite is new this phase, with its own
`requirements-dev.txt`/`ruff.toml`/CI job).

Phase 7 complete: new `packages/ai` (`cp_ai`) is the tool system every
future agent must go through - `ToolContext` (a tool call's `tenant_id`/
actor identity, always injected by the caller, never accepted as a tool
argument: `ToolRegistry.register` refuses any `args_model` that declares
a `tenant_id` field at all, so there's no argument even a
prompt-injected model could smuggle one through - CLAUDE.md #7, #18),
`ToolResult` (success/data/error, plus entity/before/after for
mutations), `ToolSchema` (name, description, Pydantic `args_model`,
`ToolPermission`, handler), `ToolPermission` (`risk_level` +
`mutates`, tracked separately since a high-risk read needs approval but
audits nothing, while a low-risk write is auditable but never blocks),
`ToolRegistry`, and `ToolExecutor` - which runs
Validate → Risk/Approval-gate → Execute → Audit for one `ToolCall`.
Anything above `LOW` risk short-circuits to `ToolResult.pending_approval`
before the handler ever runs, since the real approval workflow is Phase
8's job; a successful or failed run of a `mutates=True` tool always
gets a real `AuditEvent` row either way. Two builtin tools prove this
against real `cp_domain` data: `get_product` (`LOW`, read-only, runs
immediately) and `update_price` (`HIGH`, mutates our own `Price` row
only - never pushes to a marketplace, since that's the Phase 9 pricing
agent's job on top of a deterministic pricing engine, not a generic
tool's to decide) - calling it through the executor always comes back
`requires_approval` with nothing touched. Tested: `packages/ai`'s own 14
tests (registry + executor mechanics against a mocked `AsyncSession`, no
DB needed, new CI job) and 9 new DB-integration tests in
`apps/api/tests/test_ai_tools.py` (tenant isolation on `get_product`, the
approval gate leaving the price untouched, a real `AuditEvent` persisted
for a low-risk mutation) bringing `apps/api` to 51.

While building this phase, a `docker compose up --build` from a clean
Windows/WSL2 machine surfaced two latent bugs neither `docker compose
build` nor any test suite here had caught, now fixed: `apps/api`'s and
`apps/worker`'s Dockerfiles ran `pip install -r requirements.txt` from
the repo root, but pip resolves a requirements file's relative
`-e ../../packages/...` paths against pip's own working directory, not
the file's location, so from `/repo` they pointed above the repo
entirely (`cd` into the app directory before `pip install` fixed it);
and SQLAlchemy's own dependency metadata only pulls in `greenlet`
(required for every `AsyncSession` call) for `python_version < 3.13` -
on 3.13, this project's pinned version, it's silently skipped, so every
DB call crashed at runtime with `ValueError: the greenlet library is
required`. Local dev venvs here had been created with a lower Python by
accident, masking both issues - `greenlet` is now pinned explicitly in
both apps, and this session's own verification was redone against real
Python 3.13 venvs to make sure it wasn't hiding anything else.

Phase 8 complete: new `packages/policies` (`cp_policies`) is the
approval engine - `propose_recommendation` records an AI-proposed
action `PROPOSED`, storing the exact `tool_name`/`tool_arguments` a
blocked `ToolExecutor.execute()` call was made with in `payload` (the
AI gets one shot at what it's asking for, not a second one after a
human has already read and approved the first); `submit_for_approval`
moves it into the human queue (`PENDING_APPROVAL` + a `PENDING`
`Approval` row - this is where a real Policy Engine would run further
checks before a human ever sees it, Phase 8 keeps it a pass-through);
`approve` resolves the stored tool in a `ToolRegistry`, re-validates
its arguments, and calls the handler *directly* - never through
`ToolExecutor.execute()` again, which would just re-hit the same risk
gate forever - always landing on a terminal `SUCCESS`/`FAILED` and
writing a real `AuditEvent` (`approval_id` set) for a mutating tool
either way; `reject` marks it `REJECTED` and calls nothing, audits
nothing. Both `approve` and `reject` scope every lookup by `tenant_id`
and raise rather than silently no-op across a tenant boundary or on a
recommendation that isn't actually pending - a decision is made exactly
once. No HTTP routes yet: this is the engine only, proven end-to-end by
driving `cp_ai`'s real `update_price` tool through the full
propose → submit → approve loop and watching the `Price` row and a real
`AuditEvent` land correctly - an approval queue UI/API is later work
once there's a caller (an agent, Phase 9+) actually proposing things.
Known simplification, documented in the package README: approving isn't
protected against a concurrent double-approval race (no row locking) -
fine for now with no UI and a single approver, worth revisiting once
multiple people can act on the same queue. Tested: `packages/policies`'
own 10 tests (state-machine guards against a mocked `AsyncSession`, no
DB needed, new CI job) and 6 new DB-integration tests in
`apps/api/tests/test_approval_engine.py` (the full happy path, the
reject path leaving the price untouched, tenant isolation, and the
double-decision/not-proposed guards), bringing `apps/api` to 57.

Phase 9 complete: new `packages/pricing` (`cp_pricing`) is the
deterministic pricing engine CLAUDE.md #10 requires ("math is code") -
zero dependencies, not even on `cp_domain`. `compute_price_bounds`
takes cost/VAT/marketplace-fee/payment-fee/shipping (all rates as
fractions, not percentages) plus target/minimum margin and optional
competitor prices/stock/velocity, and returns a `minimum_price`
(protects the margin floor), a `recommended_price` (aimed at the target
margin, but never priced above the priciest visible competitor), the
margin that recommendation actually delivers, a deterministically-built
`reason` string, and a `confidence` score reduced for each piece of
missing context. Raises `PricingInfeasibleError` rather than returning a
number when even the margin floor is mathematically unreachable at any
price (fees alone consume too much of revenue) - a real signal, not a
bug to paper over.

`cp_ai.agents.pricing_agent.build_pricing_proposal` is the "AI
recommendation layer on top" the phase name promises: it reads a
product's cost/VAT, calls the engine above, and - only when there's an
actual, reachable change worth proposing - packages it as the exact
`update_price` tool call (Phase 7) a human will approve, with its
`risk_level` read directly off `update_price_tool()`'s own permission
rather than duplicated. It never mutates anything itself. `apps/worker`
gained the `worker.generate_price_recommendation` Celery task that
actually runs this against a real `Offer`/`Price`/`Product` and, if it
gets a proposal back, feeds it straight into Phase 8's
`propose_recommendation` + `submit_for_approval` - the full chain from
deterministic math to a human's approval queue, with an idempotency
check (CLAUDE.md #11) so a repeated run never stacks duplicate pending
recommendations for the same offer.

Tested: `packages/pricing`'s own 17 tests (pure math, no DB, new CI
job), 5 new tests in `packages/ai` for the pricing agent's decision
logic (no DB), and 5 new DB-integration tests in `apps/worker`
(proposes when a change is warranted, skips when already at the
recommended price, skips a missing/costless offer, and never
double-proposes on a second run), bringing `apps/worker` to 8.

AI agents exist now, but only this one, and only as a deterministic
decision-maker wearing an "AI-proposed" hat - no real LLM call happens
anywhere in this phase. Prompts and the `AIProvider` abstraction
(Anthropic/OpenAI, interchangeable per CLAUDE.md #17) still don't exist
- nothing has needed to generate text yet. That starts at Phase 10's
product agent.

Phase 10 complete: `cp_ai.providers.AIProvider` is the abstraction
CLAUDE.md #17 requires - one method, `generate_structured(*,
system_prompt, user_prompt, schema, schema_name) -> dict` - so an agent
never depends on a vendor SDK directly. `AnthropicProvider` is the first
concrete implementation, using Anthropic's tool-use mechanism to force
structured output (`schema` becomes a single tool's `input_schema`,
`tool_choice` forces exactly that tool), pinned to `anthropic==0.39.0`
specifically because it's built on plain `httpx` - a newer major version
turned out to depend on a different, unfamiliar HTTP stack, and pinning
to a well-understood version made it possible to test the same way as
the WooCommerce/Allegro connectors (`httpx.MockTransport`, no real API
key or network call). `FakeAIProvider` is this package's `MockConnector`
- a canned, call-recording double for testing an agent's own logic.

`cp_ai.agents.product_agent.build_product_content_proposal` is the
product agent: generates a title/description/bullet points via the
provider, and for every specification field the product has no real
source data for, **forces the literal string `"UNKNOWN"` into the
result after the call returns** - overwriting whatever the model said,
even a plausible-looking invented value. That overwrite matters because
`product.description` feeds the prompt as context and is untrusted
external content per CLAUDE.md #18 - potentially synced from a listing
an attacker controls, possibly trying to steer the model into inventing
a spec. The system prompt asks it not to; the code does not trust that
it complied. A new builtin tool, `update_product_content` (`MEDIUM`
risk, mutates `name`/`description`/`extra_attributes` only - never
`cost`/`vat_rate`/`ean`), is what the agent's proposal targets; `MEDIUM`
rather than `HIGH` is the first builtin tool to show risk levels aren't
just LOW-or-HIGH. `apps/worker` gained
`generate_product_content_recommendation`, mirroring the pricing task
exactly: idempotency-checked, proposes through Phase 8's
`propose_recommendation` + `submit_for_approval`, never mutates
anything itself.

Fixed along the way: `apps/api/requirements-dev.txt` and
`packages/policies/requirements-dev.txt` were missing
`-e ../../packages/pricing` - a real gap from Phase 9 that a reused,
already-built local venv had silently masked (pip only needs to resolve
`cp_ai`'s declared `cp-pricing` dependency at *install* time, not import
time, so nothing failed until a venv was rebuilt from scratch). Caught
by rebuilding every touched package's venv from scratch this phase
before calling it done - now standard practice here after Phase 6/9
each surfaced their own version of "it worked locally because the venv
was stale."

Tested: `packages/ai`'s own 27 tests total (8 new: 3 for
`AnthropicProvider` against `httpx.MockTransport`, 5 for the product
agent's decision logic including the hallucination-override case, no DB
needed for any of them), 3 new DB-integration tests in `apps/api` for
`update_product_content` (the `MEDIUM`-risk approval gate, the handler's
own logic, tenant isolation) bringing it to 60, and 4 new DB-integration
tests in `apps/worker` for the Celery task (proposes, forces `UNKNOWN`
end-to-end, never double-proposes, reports a missing product cleanly)
bringing it to 12.

## Interlude: a clickable UI on top of Phases 1-10

Out of phase order, on request: everything through Phase 10 was real but
only reachable from tests and Celery tasks - no HTTP surface beyond auth,
no way to see any of it in a browser. This interlude wires up the first
real HTTP API and a minimal web UI on top, so the whole pipeline is
clickable, not just testable:

- `apps/api` gained `connections` (list/create/trigger a sync),
  `products` (list/manually create/trigger a pricing or content
  recommendation), and `recommendations` (list/approve/reject) routes,
  plus a `Celery` client (`app/core/celery_client.py`) that enqueues
  tasks by name - apps/api still never imports apps/worker's code, only
  `send_task`s into the same Redis broker. Approving/rejecting calls
  `cp_policies` directly and synchronously (not via Celery): the
  resulting DB write is fast and local, unlike an actual sync or an LLM
  call, so CLAUDE.md #13's "no long-running jobs in a request handler"
  doesn't apply to it. `cp_ai`, `cp_pricing`, and `cp_policies` moved
  from apps/api's test-only dependencies to its real ones.
- `apps/web` gained a shared `AppShell` (nav + session guard) and three
  pages - Connections, Products, Recommendations - plus a real Dashboard
  replacing the Phase 1 placeholder. Products can be added manually
  (SKU/cost/price) for testing without a live store; each product/offer
  has buttons to queue the pricing or content agent, and approving a
  recommendation shows the change land for real.

**A real, previously-undiscovered production bug came out of actually
running this stack in a browser, not from any test:** every apps/worker
task that flushes a `TenantScopedMixin` row (`sync_connection`,
`generate_price_recommendation`, `generate_product_content_recommendation`)
crashed with `NoReferencedTableError: ... could not find table 'tenants'`
the moment it ran for real. SQLAlchemy resolves a `ForeignKey`'s target
table once per mapper, the first time any row of that type is flushed in
a process, to work out flush ordering - and apps/worker's own code never
defines or imports anything mapped to `tenants`/`users` (that's apps/api's
job, and apps/worker must never import apps/api's code). Every test
suite in `apps/worker` had passed because its `conftest.py` *did* define
local `_Tenant`/`_User` mirror classes - but only to build the test
schema, never imported by any production module, so the real worker
process never had them. Fixed by moving those mirror classes into
`worker/db.py` itself (`_TenantRef`/`_UserRef`) as real, permanent
worker code - not a test fixture - with tests now importing them from
there instead of redefining their own copies. This had been silently
broken since Phase 6.

No new automated tests for `apps/web` (this project has never had a JS
test runner; `npm run lint`/`typecheck`/`build` are its only automated
gates) - verified instead by actually running the full stack locally and
driving it with Playwright end to end: register → add a connection → add
a product → generate a pricing recommendation → approve it → watch the
price actually change and a real `AuditEvent` land. 18 new DB-integration
tests in `apps/api/tests/test_api_routes.py` cover the new routes
directly (tenant isolation, 404s/409s, the full propose → approve/reject
loop), bringing `apps/api` to 78.

Phase 11 complete: the listing agent, and the first tool whose approval
is meant to reach a real marketplace rather than only our own DB.

`RecommendationType` gained `LISTING_PUBLISH` (a new Alembic migration,
`ALTER TYPE ... ADD VALUE` with a recreate-the-enum downgrade - Postgres
has no `DROP VALUE`). `cp_ai` gained a new builtin tool,
`request_listing_publish` (HIGH risk, mutates `Offer.status`: `DRAFT` ->
`PENDING`), and `cp_ai.agents.listing_agent.build_listing_publish_proposal`
- a deterministic readiness gate, not an `AIProvider` call: "is this
listing ready to go live" is a checklist (has a marketplace `external_id`
already, is still `DRAFT`, has a name/description/price) rather than a
creative judgement, so like the pricing agent (Phase 9) this one's whole
"intelligence" is the checklist itself. Category-specific mandatory
parameters (Allegro's per-category attributes) aren't checked - category/
brand mapping across platforms still isn't modeled (`cp_sync`'s own
README), a known simplification rather than a guess.

The interesting design problem this phase actually had to solve:
`cp_policies.approve()` runs a tool's handler synchronously, in-process,
inside apps/api's `/recommendations/{id}/approve` HTTP handler - fine for
every earlier tool (`update_price`, `update_product_content`), which only
ever touch our own DB, but wrong for a tool whose whole point is a real
network call to a marketplace (CLAUDE.md #11 - retry-safe; #12/#13 -
never inline in an HTTP handler). So `request_listing_publish`'s handler
stays DB-only (`DRAFT` -> `PENDING`) and the actual connector call is a
new Celery task, `worker.publish_listing_to_marketplace` - enqueued not
by the tool itself (no Celery dependency in `cp_ai`, on purpose) but by
the approve route, which already knows a decision was just made and now
also checks whether it was a `LISTING_PUBLISH` type before enqueueing.
That task decrypts the connection's credentials, builds the real
connector (`cp_sync.connector_factory`, same as sync), and calls
`publish_offer` - the offer becomes `ACTIVE` on success. A `ConnectorError`
(the platform explicitly rejected the request - bad auth, not found)
marks the offer `ERROR` and writes a `FAILURE` `AuditEvent`; anything
else (a network-level failure) is left to propagate so Celery's own
retry/failure tracking handles it rather than permanently marking a
possibly-still-retryable offer as broken - confirmed for real, not just
in a test: running this against the actual `AllegroConnector` with fake
credentials in this sandboxed environment hit an outbound-network proxy
block (`httpx.ProxyError`, not a `ConnectorError`), and the offer
correctly stayed `PENDING` rather than flipping to `ERROR`.

Fixed along the way: `cp_sync.products._upsert_product` never actually
set `Offer.status` from what a connector reported (`ConnectorProduct.status`
was fetched but silently dropped) - every synced offer sat at the column
default forever, which would have made the listing agent's `DRAFT` check
meaningless against real data. `cp_sync` now maps each platform's own
status vocabulary (WooCommerce: `publish`/`draft`/`pending`/`private`;
Allegro: `active`/`inactive`) to `OfferStatus`, leaving anything
unrecognized alone rather than guessing - this is exactly the kind of
gap Phase 6's own docstring already flagged ("category/brand resolution
... isn't modeled yet") but for status specifically, not category.

Tested: `packages/ai` gained 6 tests for the listing agent's readiness
checklist (bringing it to 33) and DB-integration coverage for the new
tool in `apps/api/tests/test_ai_tools.py`; `apps/worker` gained 9 tests
across both new tasks in `worker/tasks/listing.py` (proposes when ready,
skips when not, idempotent on a repeat run; publishes and activates via
`MockConnector`, marks `ERROR` on a `ConnectorError`, no-ops when the
offer isn't `PENDING`), bringing it to 21; `apps/api` gained 4 tests for
the new `/offers/{id}/generate-listing-publish-recommendation` route and
the approve-route's type-conditional enqueue (verified by monkeypatching
`get_celery_client`, and that a `PRICE_CHANGE` approval does *not*
trigger it), bringing it to 92; and 5 new tests for the `cp_sync` status
mapping fix in `apps/api/tests/test_sync_products.py`. Verified end to
end against the real running stack exactly as described above, not just
against `MockConnector` in pytest.

Phase 12 complete: the catalog agent, and the first real use of `AIJob`
(`packages/domain/cp_domain/ai_job.py`) - scaffolded back in Phase 2,
never actually used by anything until now.

`cp_ai.agents.catalog_agent.audit_products` is a deterministic
checklist over a tenant's products (no `AIProvider` call, same reasoning
as the pricing and listing agents): missing description, missing EAN,
missing price, priced below cost, missing stock record, out of stock,
and an `ACTIVE` product with no offers on any connection at all
("orphaned" - active but not actually listed anywhere). Per
`docs/architecture/product-vision.md`'s own framing ("18,421 products →
analysis → 127 problems → 43 recommendations → 17 require approval"),
**not every problem becomes a `Recommendation`** - a missing price or
EAN has no safe fix to propose (CLAUDE.md #9: never guess), and a wrong
price is the pricing agent's own job, not this one's to re-derive. Only
the orphaned-product case maps to something unambiguous and safe: a new
builtin tool, `update_product_status` (`MEDIUM` risk, mutates
`Product.status`), backs a `CATALOG_FIX` recommendation to archive it -
the first real use of `RecommendationType.CATALOG_FIX`, itself sitting
unused in the enum since Phase 2. Every other issue type is still
surfaced (in the `AIJob`'s `output_payload`, and in the `/catalog` UI)
purely as a finding for a human to read, not something the approval
pipeline ever sees.

`apps/worker` gained `worker.run_catalog_audit(tenant_id)` - unlike
every other agent's task, this one operates on a tenant's *entire*
catalog rather than one product/offer, and is the first task to create
and update an `AIJob` row (`QUEUED` implicitly skipped straight to
`RUNNING` on creation, then `SUCCEEDED`/`FAILED`, with `output_payload`
holding the full structured issue list plus counts). A real exception
during the scan marks the job `FAILED` with `error_message` set, then
re-raises so Celery's own failure tracking still sees it - the job row
exists for human/UI observability, not to swallow bugs. No daily
schedule triggers this yet - `beat_schedule` is still empty, reserved
for Phase 15 ("Recommendations - daily scheduler tying agents
together") exactly as already noted after Phase 9.

`apps/api` gained `POST /catalog/audit` (enqueue) and
`GET /catalog/audits` (the tenant's past runs, most recent first,
`output_payload` flattened into a typed response). `apps/web` gained a
`/catalog` page (a "Run audit" button, a list of past runs with their
issues) and a fourth Dashboard stat card ("Catalog issues", from the
most recent run).

Verified against the real running stack, not just `MockConnector`/
pytest: registered a tenant, ran an audit with zero products, added a
connection + a manually-created product (missing description/EAN/stock
by construction) and re-ran it - 3 issues correctly surfaced in the UI
and the Dashboard's new stat card. Separately, inserted a genuinely
orphaned `ACTIVE` product directly (no variant/offer at all) and drove
the full loop through the real HTTP API: audit found it → proposed
`CATALOG_FIX` → approved it → `Product.status` actually flipped to
`ARCHIVED` in Postgres → a real `AuditEvent` row landed
(`update_product_status`, `before: {"status": "active"}`,
`after: {"status": "archived"}`).

Tested: `packages/ai` gained 18 tests for the catalog agent (audit
checklist + proposal-building, no DB, bringing it to 51) and 3 for the
new tool's handler in `apps/api/tests/test_ai_tools.py` (bringing it to
20); `apps/worker` gained 7 DB-integration tests for the new task
(zero-products, issues recorded on the `AIJob`, the orphan-product
proposal, idempotency, tenant isolation, price-below-cost - bringing it
to 28); `apps/api` gained 4 for the new `/catalog` routes (task
triggering, listing past runs shaped correctly, tenant isolation -
bringing it to 99).

Between Phase 12 and Phase 13, a real bug was reported against a live
WooCommerce store: syncing only ever produced 1 product locally no
matter how many the store actually had. Root cause: WooCommerce (like
other platforms) allows a product with no SKU at all - common in real,
especially older or imported, catalogs - and `cp_sync.products
._upsert_product` matches `Product`/`Variant` by `(tenant_id, sku)`, so
every skuless product fell back to `sku=""` and collapsed onto the very
first one synced, each later one silently overwriting the last.
Reproduced directly before fixing (3 `MockConnector` products with
`sku=""` left exactly 1 `Product` row), then fixed with
`_effective_sku()` - a connector-scoped synthetic sku
(`noSKU-<connection>-<external_id>`) for these, keeping each one
distinct without inventing a real spec value (CLAUDE.md #9 is about
customer-facing data, not this package's own internal matching key). 4
new tests in `apps/api/tests/test_sync_products.py`.

Phase 13 complete: the analytics agent, in two deliberately separate
layers per its own name - "dashboard first, AI narrative second."

**Dashboard (deterministic):** new `packages/analytics` (`cp_analytics`)
mirrors `cp_pricing`'s philosophy exactly - zero dependencies, not even
on `cp_domain`, taking plain inputs (`ProductMetricsInput`/
`OfferMetricsInput`) the caller extracts from real rows.
`compute_dashboard_metrics` is pure aggregation: product counts by
status, total/missing-price offer counts, out-of-stock count,
`total_catalog_value` (sum of `price * stock`, only where both are
known), `average_margin_rate` (mean of `(price - cost) / price` across
offers where both are known - `None`, not `0`, when nothing qualifies,
since `0` would misleadingly read as "no margin" rather than "no
data"), plus pass-through recommendation/catalog-issue counts. `apps/api`
gained `GET /analytics/dashboard` - live, synchronous, computed fresh on
every request from a handful of fast SELECTs (CLAUDE.md #13 doesn't
apply to a quick aggregate query, only to genuinely long-running work).

**AI narrative (the layer on top):** `cp_ai.agents.analytics_agent
.build_dashboard_narrative` turns a `DashboardMetrics` into a short
prose summary via `AIProvider.generate_structured`. Unlike the product
agent (Phase 10), it needs no CLAUDE.md #18 hallucination-override step
- every number it's given is our own deterministic computation, not
untrusted external content an attacker could steer; there's nothing
here for a model to be tricked into inventing *from*. Read-only
throughout: no tool call, no `Recommendation`, just narration.
`apps/worker` gained `worker.generate_dashboard_narrative`, the second
real use of `AIJob` (after Phase 12's catalog agent, `agent_type=
"analytics"`) - it computes the same metrics `GET /analytics/dashboard`
would, generates the narrative, and stores both together in
`output_payload`. `apps/api` gained `POST /analytics/narrative`
(enqueue - this is the part that makes a slow external LLM call, so
unlike the dashboard read it does need Celery) and
`GET /analytics/narratives` (past runs, most recent first).

Verified against the real running stack: registered a tenant, hit
`GET /analytics/dashboard` with zero products (all zeros, `null`
margin), added a connection + a product (cost 40, price 100, stock 10)
and re-checked it - `total_catalog_value: "1000.00"`,
`average_margin_rate: "0.6"`, both correct. Triggered the narrative
task with no `ANTHROPIC_API_KEY` configured in this sandboxed
environment (expected here - real credentials aren't available) and
confirmed it fails exactly as designed: the `AIJob` lands `FAILED` with
`error_message: "'ANTHROPIC_API_KEY'"`, the worker doesn't crash, and
the frontend's Dashboard page degrades gracefully (shows "no insight
generated yet" rather than erroring) since `narrative` is `null` on a
failed job. The Dashboard page itself now drives its stat cards from
one `GET /analytics/dashboard` call instead of three separate list
endpoints, plus two new cards (catalog value, average margin) and an
"AI insight" panel with a "Generate insight" button.

Tested: `packages/analytics`'s own 9 tests (pure math, no DB, new CI
job - `analytics`, plus added to the centralized `packages` lint job);
`packages/ai` gained 3 tests for the narrative agent (bringing it to
54); `apps/worker` gained 4 DB-integration tests for the new task
(fresh-tenant zeros, real product data reflected, tenant isolation, a
provider failure correctly marking the job `FAILED` and still raising -
bringing it to 32); `apps/api` gained 6 for the new `/analytics` routes
(live dashboard math against a real product, task triggering, listing
past runs, tenant isolation - bringing it to 109). All packages'
venvs rebuilt from scratch and all still pass.
