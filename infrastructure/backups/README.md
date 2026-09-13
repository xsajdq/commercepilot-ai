# PostgreSQL backup strategy

Not implemented yet — tracked for Phase 21 (production hardening).

Requirement: backups must live outside this server, not merely outside the
Postgres container (a lost/compromised server must not take the backups
with it). Planned approach:

1. Daily `pg_dump` (or `pg_basebackup` for larger data) run outside the
   `postgres` container, plus a weekly full backup.
2. Upload immediately to Hetzner Object Storage (a separate service/region
   from the app server) - an offsite copy, not just off-container.
3. Retention policy (e.g. daily for 14 days, weekly for 8 weeks).
4. A restore drill at least once a month — an untested backup is not a
   backup. Track drills somewhere durable (a dated log entry, a checklist
   in the on-call runbook) so a skipped month is visible, not silent.

This directory will hold the backup script and its cron/systemd-timer unit
once implemented.
