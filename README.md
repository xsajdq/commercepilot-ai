# CommercePilot

AI e-commerce manager: monitors, analyzes, and proposes actions across a
store and its marketplaces, routing anything risky through human approval
before it touches a real store. Working name — see `CLAUDE.md` for the
full mission, architecture principles, and the mandatory
`AI → Tool → Validation → Policy → Risk → Approval → Execution →
Verification → Audit Log` control flow every mutation follows.

Built in phases; see `docs/architecture/roadmap.md` for what's done and
what's next. This repo is currently at the end of **Phase 18**
(PrestaShop connector): registration, login, tenant-scoped JWT sessions,
role-based membership, the full e-commerce domain model, real
WooCommerce + Allegro + Shoper + PrestaShop connectors, a sync engine, the AI tool system +
approval engine (`Recommendation -> PendingApproval -> Approved/Rejected
-> Executing -> Success/Failed`), a deterministic pricing engine, and
six working agents (pricing, product content, listing publication,
catalog health, analytics, competition) are all live - plus a minimal
web UI (connections, products with competitor-price tracking, catalog,
recommendations/approvals, a live analytics dashboard) wired to a real
HTTP API on top of all of it, so the whole pipeline is clickable end to
end, not just testable from the CLI. The listing agent was the first
AI-approved action to reach a real marketplace (via a typed connector,
CLAUDE.md #2) rather than only our own database; the catalog and
analytics agents are the two real uses of the Phase-2-scaffolded `AIJob`
table; the competition agent closed a gap that had existed since
Phase 9 - the pricing engine always accepted competitor prices, nothing
had ever actually supplied them. Phase 15 populated Celery Beat's
`beat_schedule` (empty since Phase 0): a daily 01:00 UTC sync of every
connection and a 02:00 UTC fan-out of the catalog/analytics/pricing/
listing agents across every tenant, each dispatcher task doing nothing
but enumerate real rows and enqueue the same tasks the manual UI buttons
already call - no new agent, model, or route needed. Phase 16 was a
frontend-only pass: `AppShell` moved from a single horizontal top nav to
a dark, brand-violet left sidebar (`lucide-react` icons, an off-canvas
drawer on mobile), every page was swept onto a real design system
(a custom `brand` color scale, `Plus Jakarta Sans` via `next/font/google`,
shared `.card`/`.btn-primary`/`.input` tokens) instead of unstyled
Tailwind gray/black defaults, and the landing/login/register pages got a
matching dark gradient treatment - no backend changes, same data and
behavior underneath. Phase 17 added `ShoperConnector`, a third real
platform integration (alongside WooCommerce and Allegro) for the Polish
e-commerce platform Shoper - the connector manages its own bearer-token
auth internally (a caller supplies client ID/secret, same as
WooCommerce's consumer key/secret), and its README documents exactly
which parts of Shoper's API shape are confirmed vs. best-effort inferred
(the official docs site was unreachable from this environment). Phase 18
added `PrestaShopConnector`, the fourth real integration - unlike
Shoper, PrestaShop's Webservice API could be confirmed against its own
official docs and published Postman collection: it outputs JSON but
cannot parse JSON input (every write is real XML), and stock quantity
lives in its own separate `stock_availables` resource rather than on
the product itself.

## Repository layout

```
apps/
  api/        FastAPI backend (owns the DB engine, auth, HTTP routes)
  web/        Next.js frontend
  worker/     Celery worker + beat scheduler
packages/
  shared/     cp_shared - the shared SQLAlchemy Base + mixins
  domain/     cp_domain - the e-commerce domain model (products, orders, ...)
  connectors/ cp_connectors - CommerceConnector interface + WooCommerce/Allegro/Shoper/PrestaShop
  sync/       cp_sync - the sync engine (retry/backoff, idempotent upsert)
  pricing/    cp_pricing - deterministic pricing engine (no AI, no deps)
  analytics/  cp_analytics - deterministic dashboard metrics (no AI, no deps)
  ai/         cp_ai - tool system, AIProvider, all five agents
  policies/   cp_policies - the approval engine
infrastructure/
  docker/ hetzner/ traefik/ backups/
migrations/   Alembic migrations (auth tables + domain model)
alembic.ini   Run `alembic upgrade head` from the repo root
tests/
  unit/ integration/ e2e/
docs/
  architecture/ agents/ connectors/ api/ security/
```

`packages/shared` and `packages/domain` are installed as editable local
Python packages (see `apps/api/requirements.txt`) rather than living
inside `apps/api`, so other packages can depend on the domain model
without depending on the FastAPI app itself. `packages/connectors` is
fully standalone (no dependency on the domain model or apps/api at all -
see its own README) and tested on its own; run its tests with:

```bash
cd packages/connectors
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest
```

## Local development

Prerequisites: Docker + Docker Compose.

```bash
cp .env.example .env   # edit as needed
docker compose up --build
```

This starts Traefik, the Next.js frontend, the FastAPI backend, a Celery
worker, a Celery beat scheduler, Postgres, and Redis.

- Frontend: http://localhost:3000 (or http://commercepilot.localhost via
  Traefik) - `/register`, `/login`, `/dashboard`, `/connections`,
  `/products`, `/catalog`, `/recommendations`
- API: http://localhost:8000/docs (or http://api.commercepilot.localhost)
- API health: http://localhost:8000/health and `/health/ready` (checks
  Postgres + Redis connectivity)
- Traefik dashboard: http://localhost:8080

The `api` container runs `alembic upgrade head` on startup, so a fresh
`docker compose up` migrates the database automatically.

### Running each app outside Docker

```bash
# API - needs a local Postgres (commercepilot_test db) and Redis; see
# .env.example for the expected connection strings
cd apps/api
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
pytest

# Migrations (from the repo root, same venv)
alembic upgrade head

# Worker
cd apps/worker
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
celery -A worker.celery_app worker --loglevel=INFO

# Web
cd apps/web
npm install
npm run dev    # also: npm run build / npm run lint / npm run typecheck
```

## Contributing

Read `CLAUDE.md` first — it lists the non-negotiable architecture rules
(tenant isolation, no arbitrary AI-executed HTTP/SQL, deterministic
pricing math, mandatory audit logging, etc.) that every change must
respect.
