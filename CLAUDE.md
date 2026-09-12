# CommercePilot

## Mission

Build a production-grade multi-tenant SaaS AI E-commerce Manager: an agent
that monitors, analyzes, and proposes actions across e-commerce stores and
marketplaces, routing anything risky through human approval before it
touches a real store.

Working name only — "CommercePilot" names the repository and product while
we build; it is not final branding.

## Core principles

1. Never allow AI to directly execute arbitrary HTTP requests.
2. Every external mutation must go through a typed connector.
3. Every mutation must pass validation and policy checks.
4. Medium/high-risk actions require human approval.
5. Every mutation must create an audit log.
6. All business entities are tenant-scoped.
7. Never trust `tenant_id` from client input — the backend derives it from
   the authenticated session, always.
8. Never store API credentials in plaintext.
9. Never invent product technical specifications. Missing data is `UNKNOWN`,
   never guessed.
10. Deterministic business calculations (pricing, margin, VAT) must not be
    delegated to an LLM. AI may recommend; math is code.
11. All external API calls must be retry-safe and idempotent.
12. All background work must be asynchronous (Celery), never inline in an
    HTTP request handler.
13. Never perform long-running jobs in HTTP request handlers.
14. Tests are required for every business-critical feature.
15. Do not introduce microservices unless there is a concrete need — prefer
    a simple modular monolith (`apps/api`, `apps/worker`) over premature
    service decomposition.
16. Keep connectors isolated from domain logic — the domain model must
    never import a marketplace SDK directly.
17. AI providers must be replaceable (`AIProvider` abstraction); never
    hardcode a single vendor's SDK into business logic.

## The control flow every mutation follows

```
AI → Tool → Validation → Policy Engine → Risk Assessment → Approval
  → Execution → Verification → Audit Log
```

No shortcuts around this chain, ever — not for "obviously safe" actions,
not for admin/debug tooling, not for tests running against real stores.

## Stack

- Backend: Python 3.13 + FastAPI + SQLAlchemy 2 + Alembic + Pydantic
- Frontend: Next.js + TypeScript + Tailwind CSS + shadcn/ui
- Workers: Celery + Redis (Celery Beat for scheduling)
- Database: PostgreSQL
- HTTP client: httpx
- Auth: own JWT + refresh tokens for MVP (pluggable later)
- Payments: Stripe
- AI: provider-abstracted (`AIProvider` → Anthropic, OpenAI, ...)
- Infra: Docker Compose + Traefik + Hetzner Cloud + Cloudflare
- Observability: Sentry + Prometheus/Grafana (added during hardening)

## Repository layout

```
apps/
  api/        FastAPI backend
  web/        Next.js frontend
  worker/     Celery worker + beat scheduler
packages/
  domain/     Platform-agnostic domain model (Product, Offer, Order, ...)
  connectors/ CommerceConnector interface + per-platform implementations
  ai/         Agents, tools, prompts, AIProvider abstraction
  pricing/    Deterministic pricing engine
  policies/   Policy engine, risk assessment, approval rules
  shared/     Cross-cutting utilities shared by apps/packages
infrastructure/
  docker/     Shared Dockerfiles/compose fragments
  hetzner/    Server provisioning notes/scripts
  traefik/    Reverse proxy static/dynamic config
  backups/    Off-server PostgreSQL backup strategy
migrations/   Alembic migrations for the domain database
tests/
  unit/
  integration/
  e2e/
docs/
  architecture/ agents/ connectors/ api/ security/
```

## Development rules

Before implementing a feature:
1. Inspect existing architecture.
2. Identify affected domain modules.
3. Write/update tests.
4. Implement.
5. Run tests.
6. Run lint/type checks.
7. Update documentation.

Never rewrite unrelated code. Build in phases (see `docs/architecture/roadmap.md`)
rather than one large change — each phase should be independently testable
before the next begins.

## Security

Never log:
- access tokens
- refresh tokens
- API keys
- customer personal data
- payment information

Secrets must be encrypted at rest and never committed. `.env` is
git-ignored; only `.env.example` (placeholders) is tracked.

## AI

AI may:
- reason
- classify
- generate text
- propose actions
- call approved tools

AI may not:
- execute arbitrary SQL
- execute arbitrary shell commands
- access secrets directly
- bypass the policy engine
- bypass approval requirements

## Definition of done

No feature is considered complete until:
- tests pass
- migrations work
- error handling exists
- audit logging exists where applicable
- tenant isolation is verified
- documentation is updated
