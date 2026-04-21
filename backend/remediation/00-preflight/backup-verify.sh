#!/usr/bin/env bash
# 00-preflight/backup-verify.sh
# Verifies that a DB backup exists AND is restorable before starting remediation.
# Do not trust Railway's snapshot UI alone — actually restore it.

set -euo pipefail

: "${PROD_DATABASE_URL:?set PROD_DATABASE_URL to the live DB connection string}"
: "${BACKUP_DUMP_PATH:=/tmp/perennia-preflight-$(date +%Y%m%d-%H%M%S).dump}"
: "${SCRATCH_DATABASE_URL:?set SCRATCH_DATABASE_URL to a throwaway postgres you can blow away}"

echo "==> Dumping production DB to ${BACKUP_DUMP_PATH}"
pg_dump --format=custom --no-owner --no-acl \
  --file="${BACKUP_DUMP_PATH}" \
  "${PROD_DATABASE_URL}"

DUMP_SIZE=$(stat -c%s "${BACKUP_DUMP_PATH}")
if [ "${DUMP_SIZE}" -lt 1000000 ]; then
  echo "!! Dump is under 1MB. Production DB should not be this small. Aborting."
  exit 1
fi
echo "    dump size: $(numfmt --to=iec ${DUMP_SIZE})"

echo "==> Dropping scratch DB tables"
psql "${SCRATCH_DATABASE_URL}" -c "DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;"

echo "==> Restoring into scratch DB"
pg_restore --no-owner --no-acl --dbname="${SCRATCH_DATABASE_URL}" "${BACKUP_DUMP_PATH}"

echo "==> Sanity-checking restored data"
USERS=$(psql "${SCRATCH_DATABASE_URL}" -t -c "SELECT count(*) FROM users;" | xargs)
LOANS=$(psql "${SCRATCH_DATABASE_URL}" -t -c "SELECT count(*) FROM loans;" | xargs)

if [ "${USERS}" = "0" ] || [ "${LOANS}" = "0" ]; then
  echo "!! Restored DB has no users or loans. Backup is unusable. Aborting."
  exit 1
fi

echo "==> Backup verified"
echo "    users: ${USERS}"
echo "    loans: ${LOANS}"
echo "    dump:  ${BACKUP_DUMP_PATH}"
echo ""
echo "Keep ${BACKUP_DUMP_PATH} until post-deploy verification passes."
