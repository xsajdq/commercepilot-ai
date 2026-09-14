# PostgreSQL backup strategy (Phase 21)

Requirement: backups must live outside this server, not merely outside
the Postgres container (a lost/compromised server must not take the
backups with it).

## What's here

- `backup.sh` - daily `pg_dump` (custom format, via `pg_restore`-
  compatible archive) with local retention pruning (14 daily, 8 weekly
  by default) and an optional upload to any S3-compatible object
  storage (Hetzner Object Storage included - it speaks the S3 API).
  The upload step is skipped, not an error, when `BACKUP_S3_BUCKET`
  isn't set, so the script also works standalone for local
  verification or before a bucket exists yet.
- `restore.sh` - restores a `backup.sh` dump into an explicitly named
  target database. Never reads a target from the environment implicitly
  - a restore (drill or real) always names its target on the command
  line, so a stale env var can't point it at a live database by
  accident.
- `commercepilot-backup.service` / `commercepilot-backup.timer` -
  systemd units to run `backup.sh` daily at 03:00 UTC once deployed to
  the Hetzner box (see `infrastructure/hetzner/README.md`). Not
  installed anywhere yet - that happens when this app is actually
  deployed there.

## Restore drills

"An untested backup is not a backup you can rely on" - do this monthly
once in production, and log the date/result somewhere durable (this
file, or an on-call runbook once one exists) so a skipped month is
visible, not silent.

Verified once for real in this repo's dev environment as part of
building this phase: `backup.sh` against the real local dev database,
restored via `restore.sh` into a fresh scratch database
(`commercepilot_restore_drill`), and compared - identical row counts
across every table checked (`tenants`, `users`, `connections`,
`products`, `ai_jobs`, `subscriptions`) and an identical checksum over
every `connections.encrypted_credentials` value, confirming the restore
preserves exact content, not just row counts.

To run the drill yourself:

```bash
# 1. Back up the source database.
DATABASE_URL="postgresql://commercepilot:commercepilot@localhost:5432/commercepilot" \
BACKUP_DIR=/tmp/backup-drill \
  ./backup.sh

# 2. Create an empty target and restore into it.
createdb -O commercepilot commercepilot_restore_drill
./restore.sh /tmp/backup-drill/daily/commercepilot-*.dump \
  "postgresql://commercepilot:commercepilot@localhost:5432/commercepilot_restore_drill"

# 3. Compare row counts (or anything else you want to verify) between
#    the source and commercepilot_restore_drill, then drop it.
dropdb commercepilot_restore_drill
```

## Retention policy

- Daily backups: 14 days (`BACKUP_RETENTION_DAILY_DAYS`).
- Weekly backups (Sunday's daily dump, kept longer): 8 weeks
  (`BACKUP_RETENTION_WEEKLY_WEEKS`).

## What's still deferred

- **Offsite upload to Hetzner Object Storage**: the script supports it
  (`BACKUP_S3_BUCKET`/`BACKUP_S3_ENDPOINT_URL`, via the `aws` CLI
  against Hetzner's S3-compatible endpoint), but there is no real
  Hetzner Object Storage bucket or account yet - that's created when
  this app is actually deployed (Phase 21/22 deploy-pipeline
  territory), not something this repo can provision itself.
- **Installing the systemd timer on a real server** - same reasoning;
  there is no server yet to install it on.
- **`pg_basebackup`** for a database large enough that logical
  `pg_dump` becomes too slow to run daily - not needed at this app's
  current data volume; revisit if/when it becomes true.
