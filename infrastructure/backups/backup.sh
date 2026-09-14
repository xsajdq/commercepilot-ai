#!/usr/bin/env bash
set -euo pipefail

# Phase 21: daily/weekly PostgreSQL backup, local retention pruning, and
# an optional offsite copy to any S3-compatible object storage (Hetzner
# Object Storage included) - implements the plan this directory's own
# README documented since Phase 0.
#
# Required environment:
#   DATABASE_URL            - e.g. postgresql://user:pass@host:5432/dbname
# Optional (offsite upload skipped entirely, not an error, if unset):
#   BACKUP_S3_BUCKET        - e.g. s3://commercepilot-backups
#   BACKUP_S3_ENDPOINT_URL  - e.g. https://fsn1.your-objectstorage.com
# Optional retention overrides:
#   BACKUP_DIR                    (default /var/backups/commercepilot)
#   BACKUP_RETENTION_DAILY_DAYS   (default 14)
#   BACKUP_RETENTION_WEEKLY_WEEKS (default 8)

: "${DATABASE_URL:?DATABASE_URL must be set}"

BACKUP_DIR="${BACKUP_DIR:-/var/backups/commercepilot}"
RETENTION_DAILY_DAYS="${BACKUP_RETENTION_DAILY_DAYS:-14}"
RETENTION_WEEKLY_WEEKS="${BACKUP_RETENTION_WEEKLY_WEEKS:-8}"

mkdir -p "$BACKUP_DIR/daily" "$BACKUP_DIR/weekly"

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
day_of_week="$(date -u +%u)" # 1 = Monday, 7 = Sunday

daily_file="$BACKUP_DIR/daily/commercepilot-${timestamp}.dump"

echo "Dumping database to ${daily_file}..."
pg_dump --format=custom --file="$daily_file" --dbname="$DATABASE_URL"

# Weekly full backup: Sunday's daily dump doubles as this week's weekly
# copy rather than running pg_dump a second time for the same data.
if [ "$day_of_week" = "7" ]; then
  weekly_file="$BACKUP_DIR/weekly/commercepilot-${timestamp}.dump"
  cp "$daily_file" "$weekly_file"
  echo "Copied Sunday's dump into weekly retention: ${weekly_file}"
fi

echo "Pruning local backups older than retention window..."
find "$BACKUP_DIR/daily" -name '*.dump' -mtime "+${RETENTION_DAILY_DAYS}" -print -delete
find "$BACKUP_DIR/weekly" -name '*.dump' -mtime "+$((RETENTION_WEEKLY_WEEKS * 7))" -print -delete

# A backup that never leaves this server isn't a backup by this
# project's own rule (infrastructure/backups/README.md) - but this
# script still runs standalone (no upload) for local/dev use and for
# the restore-drill verification below, which needs no object storage
# account at all.
if [ -n "${BACKUP_S3_BUCKET:-}" ]; then
  endpoint_args=()
  if [ -n "${BACKUP_S3_ENDPOINT_URL:-}" ]; then
    endpoint_args=(--endpoint-url "$BACKUP_S3_ENDPOINT_URL")
  fi
  echo "Uploading to ${BACKUP_S3_BUCKET}..."
  aws s3 cp "${endpoint_args[@]}" "$daily_file" "${BACKUP_S3_BUCKET}/daily/$(basename "$daily_file")"
else
  echo "BACKUP_S3_BUCKET not set - skipping offsite upload (local-only backup)."
fi

echo "Backup complete: ${daily_file}"
