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
- [ ] **Phase 8 — Approval engine**: Recommendation → PendingApproval →
      Approved/Rejected → Executing → Success workflow.
- [ ] **Phase 9 — Pricing agent**: deterministic pricing engine first, AI
      recommendation layer on top.
- [ ] **Phase 10 — Product agent**: structured content generation with
      `UNKNOWN` for missing specs.
- [ ] **Phase 11 — Listing agent** (Allegro publication workflow).
- [ ] **Phase 12 — Catalog agent** (daily catalog health audit).
- [ ] **Phase 13 — Analytics agent** (dashboard first, AI narrative second).
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

AI agents don't exist yet — that starts at Phase 9, once Phase 8's
approval engine gives `ToolExecutor` something real to hand
medium/high-risk calls to instead of refusing them outright.
