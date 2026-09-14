# Disaster recovery runbook (Phase 21)

Written ahead of there being a real production deployment (there isn't
one yet - see `docs/architecture/deployment.md`), so the steps below
are the plan a real incident would follow, not a drill already run
against a live Hetzner box. What *has* been run for real: the backup
and restore mechanics themselves (`infrastructure/backups/README.md`'s
"Restore drills" section) against a real Postgres instance in this
repo's dev environment - the part of this runbook that's genuinely
untested is the surrounding infrastructure (a real Hetzner server,
Cloudflare DNS, a real Hetzner Object Storage bucket), because none of
it exists yet.

## Scenarios

### 1. The application containers crash or misbehave (not data loss)

The lowest-severity case - `docker compose restart <service>` (or
`docker compose up -d --build` after a bad deploy) on the Hetzner box.
No data recovery needed; Postgres/Redis data volumes are untouched by
an app-container restart. Check `docs/architecture/deployment.md`'s
monitoring dashboard first to confirm which service actually failed
before restarting everything blindly.

### 2. The Postgres data volume is corrupted or lost

1. Provision (or reuse, if the container/host itself is fine and only
   the volume is bad) a Postgres instance.
2. Restore the most recent backup:
   `infrastructure/backups/restore.sh <latest-backup> <target-database-url>`
   - the latest backup lives in Hetzner Object Storage (once that
   bucket exists), not just the local `/var/backups/commercepilot`
   directory a compromised/lost server could have taken down with it.
3. Run `alembic upgrade head` against the restored database - a backup
   taken before the latest deploy could be missing a migration or two.
4. Point `DATABASE_URL` at the restored instance and restart the app
   containers.
5. **Expected data loss**: everything since the last successful daily
   backup (up to ~24h, per the retention plan) - there is no
   continuous replication or point-in-time recovery in this plan yet;
   see "What's not covered" below.

### 3. The entire Hetzner server is lost (hardware failure, account
   issue, compromised host)

1. Provision a new Hetzner server (or a different provider entirely,
   since nothing here is Hetzner-specific beyond the compose files and
   `infrastructure/hetzner/README.md`'s own notes).
2. Re-run whatever provisioning exists at the time (cloud-init, Docker
   install - `infrastructure/hetzner/README.md` notes these are not
   written yet either) and `docker compose up -d` the stack fresh.
3. Follow scenario 2 above to restore Postgres from the offsite backup.
4. Redis holds only the Celery broker/result backend and rate-limit
   counters - nothing that needs restoring; an empty Redis on a fresh
   server is a correct starting state (in-flight tasks are lost, which
   is an acceptable, already-idempotent-by-design gap - see CLAUDE.md
   #11, every connector sync/agent task is safe to simply re-run).
5. Re-point DNS (Cloudflare) at the new server's IP if it changed.

### 4. A bad deploy silently corrupts data (not a crash - a logic bug
   writing wrong values)

The hardest case: backups won't help until the bug's introduction date
is known, because every backup taken after that point already contains
the bad data. Steps:

1. Stop the bad deploy immediately (roll back the app containers to the
   previous image - this alone does not fix already-written bad rows).
2. Identify the time window the bug was live, using
   `git log`/deploy history plus Sentry (Phase 21 - `configure_sentry`
   in both apps) for when the first bad event fired.
3. Restore a backup from *before* that window into a scratch database
   (never directly over production), and manually diff or
   selectively copy back only the affected rows/tables - a blanket
   restore of an old backup over current production would also lose
   every legitimate change made since.
4. Add a regression test for the bug before considering it resolved
   (CLAUDE.md's "definition of done").

## What's not covered yet (honestly, not hidden)

- **Point-in-time recovery / continuous WAL archiving** - the current
  plan is daily `pg_dump` snapshots, which caps acceptable data loss at
  roughly 24 hours. `pg_basebackup` + WAL archiving would shrink that
  window but is real additional infrastructure this repo doesn't run
  yet; `infrastructure/backups/README.md` already flags this as
  something to revisit once data volume/criticality justifies it.
- **Multi-region/multi-server failover** - a single Hetzner server is
  this project's explicit MVP target (`infrastructure/hetzner/README.md`);
  there is no standby server to fail over to.
- **A tested runbook against a real server** - everything above is the
  plan, verified only where a real Postgres instance already exists
  (this repo's own dev environment, for the backup/restore mechanics
  themselves). Re-verify scenario 2 for real against the actual Hetzner
  deployment once it exists, and update this document with what
  actually happened, the same way `infrastructure/backups/README.md`
  now records its own real drill result instead of a hypothetical one.
