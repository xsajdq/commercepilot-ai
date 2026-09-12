# CommercePilot

AI e-commerce manager: monitors, analyzes, and proposes actions across a
store and its marketplaces, routing anything risky through human approval
before it touches a real store. Working name — see `CLAUDE.md` for the
full mission, architecture principles, and the mandatory
`AI → Tool → Validation → Policy → Risk → Approval → Execution →
Verification → Audit Log` control flow every mutation follows.

Built in phases; see `docs/architecture/roadmap.md` for what's done and
what's next. This repo is currently at the end of **Phase 1**
(authentication + multi-tenancy): registration, login, tenant-scoped
JWT sessions, and role-based membership are live. No product/order domain
model or connectors exist yet.

## Repository layout

```
apps/
  api/        FastAPI backend
  web/        Next.js frontend
  worker/     Celery worker + beat scheduler
packages/
  domain/ connectors/ ai/ pricing/ policies/ shared/
infrastructure/
  docker/ hetzner/ traefik/ backups/
migrations/   Alembic migrations (users/tenants/memberships/refresh_tokens)
alembic.ini   Run `alembic upgrade head` from the repo root
tests/
  unit/ integration/ e2e/
docs/
  architecture/ agents/ connectors/ api/ security/
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
  Traefik) - `/register`, `/login`, `/dashboard`
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
