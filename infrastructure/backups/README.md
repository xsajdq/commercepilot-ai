# PostgreSQL backup strategy

Not implemented yet — tracked for Phase 21 (production hardening).

Requirement: backups must live outside this server, not merely outside the
Postgres container (a lost/compromised server must not take the backups
with it). Planned approach:

1. Scheduled `pg_dump` (or `pg_basebackup` for larger data) run outside the
   `postgres` container.
2. Upload immediately to Hetzner Object Storage (a separate service/region
   from the app server).
3. Retention policy (e.g. daily for 14 days, weekly for 8 weeks).
4. Periodic restore drills — an untested backup is not a backup.

This directory will hold the backup script and its cron/systemd-timer unit
once implemented.
