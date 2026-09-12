# Roadmap

Development proceeds in phases. Each phase should be independently
testable and merged before the next begins — never one giant change.

- [x] **Phase 0 — Project bootstrap**: monorepo skeleton, Docker Compose
      stack (Traefik, Next.js, FastAPI, Celery worker + beat, Postgres,
      Redis), env handling, health checks, CI.
- [x] **Phase 1 — Authentication + multi-tenancy**: users, tenants,
      memberships, roles, sessions, JWT + refresh tokens, tenant
      middleware. Gate: a user in Tenant A cannot access Tenant B's data.
- [ ] **Phase 2 — Domain model**: Product, Variant, Brand, Category, Offer,
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

No product/order domain model or connectors exist yet — that starts at
Phase 2.
