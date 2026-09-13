# Deployment plan (not implemented yet)

Captured ahead of building it - this is Phase 21 (production hardening)
and Phase 22 (beta) territory. Nothing here exists in the repo yet
(there's no deploy workflow, no staging environment, no monitoring
stack); don't start building against this until those phases are next.

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

Dashboard, once there's infrastructure to put it on (Prometheus/Grafana,
per CLAUDE.md's stack):

- API latency
- CPU / RAM / disk
- PostgreSQL and Redis health
- Celery queue length
- failed job count
- AI cost (ties into the Phase 31-equivalent cost guard from the original
  product spec, once billing/usage limits exist)
- connector error rate (WooCommerce/Allegro API failures, by type)

Alert thresholds (starting point, tune once there's real traffic to
calibrate against):

- queue length > 1000
- CPU > 90%
- disk > 80%
- failed jobs above some threshold (needs a baseline first)
- AI cost above the tenant's or the platform's budget

## Backups

See `infrastructure/backups/README.md` for the concrete plan (daily
Postgres backup, weekly full backup, offsite copy, monthly restore
drill). The rule worth repeating: a backup that has never been restored
is not a backup you can rely on.
