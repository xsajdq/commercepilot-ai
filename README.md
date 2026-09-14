# CommercePilot

AI e-commerce manager: monitors, analyzes, and proposes actions across a
store and its marketplaces, routing anything risky through human approval
before it touches a real store. Working name — see `CLAUDE.md` for the
full mission, architecture principles, and the mandatory
`AI → Tool → Validation → Policy → Risk → Approval → Execution →
Verification → Audit Log` control flow every mutation follows.

Built in phases; see `docs/architecture/roadmap.md` for what's done and
what's next. This repo is currently at the end of **Phase 13** (analytics
agent): registration, login, tenant-scoped JWT sessions, role-based
membership, the full e-commerce domain model, real WooCommerce + Allegro
connectors, a sync engine, the AI tool system + approval engine
(`Recommendation -> PendingApproval -> Approved/Rejected -> Executing ->
Success/Failed`), a deterministic pricing engine, and five working agents
(pricing, product content, listing publication, catalog health,
analytics) are all live - plus a minimal web UI (connections, products,
catalog, recommendations/approvals, a live analytics dashboard) wired to
a real HTTP API on top of all of it, so the whole pipeline is clickable
end to end, not just testable from the CLI. The listing agent was the
first AI-approved action to reach a real marketplace (via a typed
connector, CLAUDE.md #2) rather than only our own database; the catalog
and analytics agents are the two real uses of the Phase-2-scaffolded
`AIJob` table.

## Repository layout

```
apps/
  api/        FastAPI backend (owns the DB engine, auth, HTTP routes)
  web/        Next.js frontend
  worker/     Celery worker + beat scheduler
packages/
  shared/     cp_shared - the shared SQLAlchemy Base + mixins
  domain/     cp_domain - the e-commerce domain model (products, orders, ...)
  connectors/ cp_connectors - CommerceConnector interface + WooCommerce/Allegro
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
