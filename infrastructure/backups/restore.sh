#!/usr/bin/env bash
set -euo pipefail

# Restores a pg_dump custom-format backup (produced by backup.sh) into a
# target database - used both for real disaster recovery and for the
# monthly restore drill infrastructure/backups/README.md requires ("a
# backup that has never been restored is not a backup you can rely on").
#
# Usage: restore.sh <backup-file> <target-database-url>
#
# The target database must already exist; this never targets a
# DATABASE_URL read from the environment implicitly - the caller must
# name the target explicitly, so a drill run against a scratch database
# can never be accidentally pointed at production by a stale env var.

if [ "$#" -ne 2 ]; then
  echo "Usage: $0 <backup-file> <target-database-url>" >&2
  exit 1
fi

backup_file="$1"
target_url="$2"

if [ ! -f "$backup_file" ]; then
  echo "Backup file not found: $backup_file" >&2
  exit 1
fi

echo "Restoring ${backup_file} into ${target_url}..."
pg_restore --clean --if-exists --no-owner --dbname="$target_url" "$backup_file"
echo "Restore complete."
