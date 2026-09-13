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
- [ ] **Phase 6 — Sync engine**: pagination, retries, rate limits, backoff,
      idempotency, partial failures.
- [ ] **Phase 7 — AI tool system**: ToolRegistry, ToolSchema, ToolExecutor,
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

No sync engine or AI agents exist yet — that starts at Phase 6.
