# CommercePilot

AI e-commerce manager for multi-store, multi-marketplace sellers. It
watches your catalog, pricing, and listings, proposes changes, and routes
anything risky through human approval before it ever touches a real
store — never a direct, unchecked write.

```
AI → Tool → Validation → Policy → Risk → Approval
   → Execution → Verification → Audit Log
```

Every mutation follows that chain. No exceptions for "obviously safe"
actions.

## What it does

- **Connects** to WooCommerce, Allegro, Shoper, PrestaShop, and IdoSell
  stores through typed, retry-safe connectors.
- **Syncs** products, offers, stock, and orders on a schedule.
- **Analyzes** catalog health, margins, and competitor pricing.
- **Proposes** pricing changes, product content, and listing publication —
  AI reasons and recommends, deterministic code does the math.
- **Gates** every write behind validation, policy checks, and (for
  medium/high-risk actions) human approval, with a full audit trail.
- **Bills** usage through Stripe with a real per-tenant AI cost guard.

## Stack

FastAPI + SQLAlchemy + Alembic + Pydantic · Next.js + TypeScript +
Tailwind + shadcn/ui · Celery + Redis · PostgreSQL · Docker Compose +
Traefik.

## Repository layout

```
apps/          api (FastAPI) · web (Next.js) · worker (Celery)
packages/      domain · connectors · sync · pricing · analytics ·
               ai · policies · billing · shared
infrastructure/ docker · traefik · backups
migrations/    Alembic
tests/         unit · integration · e2e
docs/          architecture · agents · connectors · api · security
```

`packages/connectors` is fully standalone (no dependency on the domain
model or `apps/api`) and has its own test suite:

```bash
cd packages/connectors
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest
```

## Getting started

Prerequisites: Docker + Docker Compose.

```bash
cp .env.example .env   # fill in real values as needed
docker compose up --build
```

This brings up Traefik, the Next.js frontend, the FastAPI backend, a
Celery worker + beat scheduler, Postgres, and Redis. The API container
runs migrations on startup.

- Frontend: http://localhost:3000
- API: http://localhost:8000/docs
- Health: http://localhost:8000/health, `/health/ready`
- Traefik dashboard: http://localhost:8080

### Running services outside Docker

```bash
# API — needs local Postgres + Redis, see .env.example
cd apps/api
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
pytest

# Migrations (repo root, same venv)
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

## Project status

Built in phases, each independently testable — see
[`docs/architecture/roadmap.md`](docs/architecture/roadmap.md) for what's
shipped and what's next.

## Contributing

Read [`CONTRIBUTING.md`](CONTRIBUTING.md) first — it covers the
non-negotiable rules (tenant isolation, no arbitrary AI-executed
HTTP/SQL, deterministic pricing math, mandatory audit logging) that every
change must respect.
