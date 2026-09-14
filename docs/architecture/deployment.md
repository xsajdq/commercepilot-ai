# Deployment plan

Phase 21 (production hardening) built the *application-level* pieces
of this plan for real - structured logging, Sentry, Prometheus metrics,
rate limiting, security headers, secret rotation, and backup/restore
scripts, all listed below with what's actually implemented vs. what
still needs a real server to exist. The deploy pipeline itself (a real
Hetzner box, GitHub Actions SSH deploy, a real staging environment) is
still Phase 22 (beta) territory - none of that can be built from inside
this repo without a real server/account to point it at.

## Deploy pipeline

Keep it simple - no need for anything elaborate at this stage:

```
GitHub
   ↓
GitHub Actions: tests → build Docker images → push to a registry
   ↓
Hetzner: docker compose pull → alembic upgrade head → restart
```

A plain SSH-triggered deploy (a GitHub Actions step that SSHes into the
Hetzner box and runs the pull/migrate/restart) is enough to start; no
need for a fleet orchestrator or blue/green deploys at this scale.

## Environments

Minimum: **local**, **staging**, **production**. Non-negotiable: a
developer's machine must never be able to reach the production database -
that's a `DATABASE_URL` a developer's `.env` simply never contains, not a
convention people are trusted to follow.

Staging should use sandbox/mock connectors wherever the platform offers
one (Allegro has a real sandbox; `MockConnector` is always an option) -
the goal is exercising the full sync → recommend → approve → execute
pipeline without ever touching a real seller's live store or orders.

## Monitoring

Local Prometheus + Grafana now exist (`docker compose --profile
observability up` - see `infrastructure/observability/README.md`),
with a real dashboard covering:

- API request rate/latency/error rate by route (`apps/api/app/core/metrics.py`)
- Celery task throughput/duration/failure count by task name
  (`apps/worker/worker/observability.py`)

Not yet wired up (real, honestly-tracked gaps - each needs a metrics
exporter sidecar this repo has nowhere to run yet):

- CPU / RAM / disk (`node_exporter`)
- PostgreSQL and Redis health (`postgres_exporter`/`redis_exporter`)
- AI cost as a Grafana panel - the real number already exists
  (`cp_billing`'s cost guard, Phase 20) and is queryable via
  `GET /billing`; it just isn't graphed yet.
- connector error rate by platform

Alert thresholds (starting point, tune once there's real traffic to
calibrate against) - Prometheus/Grafana can now evaluate these, but no
Alertmanager (or anywhere to send a notification) exists yet, so
nothing pages anyone:

- queue length > 1000
- CPU > 90%
- disk > 80%
- failed jobs above some threshold (needs a baseline first)
- AI cost above the tenant's or the platform's budget

## Backups

See `infrastructure/backups/README.md` for `backup.sh`/`restore.sh` -
real scripts, verified with a real backup-and-restore drill against a
real Postgres instance (row counts and a content checksum both matched
exactly). What's still deferred: the real Hetzner Object Storage bucket
the offsite copy needs, and installing the systemd timer on an actual
server - neither can be created from inside this repo. See
`docs/architecture/disaster-recovery.md` for the runbook these scripts
serve.

## Security hardening (Phase 21)

- Structured JSON logging with secret redaction
  (`packages/shared/cp_shared/logging.py`) in both apps.
- Sentry error tracking (`app/core/sentry.py` /
  `worker/observability.py`), scrubbed through the same redaction rules
  (`cp_shared/sentry.py`) - a no-op until `SENTRY_DSN` is configured.
- Per-IP rate limiting (`apps/api/app/core/rate_limit.py`), tighter on
  `/auth/*`.
- Security response headers (`apps/api/app/core/security_headers.py`)
  plus proxy-layer hardening for a real deployment
  (`infrastructure/traefik/dynamic/security.yml`).
- `ENCRYPTION_KEY`/`SECRET_KEY` rotation support without downtime - see
  `docs/security/secret-rotation.md`.
- What the edge WAF (Cloudflare) should add on top of all of the
  above - see `docs/security/waf.md`.
