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
- [ ] **Phase 3 — Connector framework**: `CommerceConnector` interface +
      mock connector, tested without any real store.
- [ ] **Phase 4 — WooCommerce connector**.
- [ ] **Phase 5 — Allegro connector**.
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
packages/domain` - see `apps/api/requirements.txt`); this keeps
`packages/connectors` (Phase 3+) able to depend on the domain model
without depending on `apps/api`, per CLAUDE.md's layering.

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

No connectors or AI agents exist yet — that starts at Phase 3.
