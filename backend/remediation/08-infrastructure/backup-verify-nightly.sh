#!/usr/bin/env bash
# 08-infrastructure/backup-verify-nightly.sh
#
# Nightly restore drill. Runs via Railway Cron or GitHub Actions scheduled workflow.
# If it fails, Slack webhook fires and SOC 2 evidence is captured.
#
# Required env vars:
#   PROD_DATABASE_URL           — read-only role with pg_dump privileges preferred
#   SCRATCH_DATABASE_URL        — throwaway DB on the same region
#   SLACK_WEBHOOK_URL           — for alerts
#   BACKUP_EVIDENCE_BUCKET      — S3 bucket for dump retention (encrypted)

set -euo pipefail

TIMESTAMP=$(date -u +%Y%m%dT%H%M%SZ)
DUMP="/tmp/perennia-backup-${TIMESTAMP}.dump"
LOG="/tmp/perennia-backup-${TIMESTAMP}.log"

log() { echo "[$(date -u +%H:%M:%S)] $*" | tee -a "${LOG}"; }

post_slack() {
  local status=$1 message=$2
  local color
  case "$status" in
    ok)    color="good" ;;
    warn)  color="warning" ;;
    fail)  color="danger" ;;
  esac
  curl -s -X POST -H "Content-type: application/json" \
    --data "$(jq -n --arg c "$color" --arg m "$message" \
      '{attachments:[{color:$c,title:"Perennia backup verify",text:$m,ts:now}]}')" \
    "${SLACK_WEBHOOK_URL}" >/dev/null || true
}

fail() {
  log "FAIL: $*"
  post_slack fail "Backup verification FAILED: $*. Log: ${LOG}"
  exit 1
}

log "Starting nightly backup verification"

# 1. Dump production
log "Dumping production DB"
if ! pg_dump \
    --format=custom \
    --no-owner \
    --no-acl \
    --jobs=4 \
    --file="${DUMP}" \
    "${PROD_DATABASE_URL}" 2>>"${LOG}"; then
  fail "pg_dump failed"
fi

DUMP_SIZE=$(stat -c%s "${DUMP}" 2>/dev/null || stat -f%z "${DUMP}")
log "Dump size: $(numfmt --to=iec ${DUMP_SIZE} 2>/dev/null || echo ${DUMP_SIZE} bytes)"

# Sanity: reject suspiciously small dumps
if [ "${DUMP_SIZE}" -lt 1000000 ]; then
  fail "Dump is under 1MB — suspicious"
fi

# 2. Restore into scratch
log "Restoring into scratch DB"
psql "${SCRATCH_DATABASE_URL}" -c "DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;" \
  >>"${LOG}" 2>&1 || fail "scratch schema reset failed"

if ! pg_restore \
    --no-owner \
    --no-acl \
    --jobs=4 \
    --dbname="${SCRATCH_DATABASE_URL}" \
    "${DUMP}" 2>>"${LOG}"; then
  fail "pg_restore failed"
fi

# 3. Sanity queries — restored DB must have expected data
USERS=$(psql "${SCRATCH_DATABASE_URL}" -t -c "SELECT count(*) FROM users;" 2>/dev/null | xargs)
LOANS=$(psql "${SCRATCH_DATABASE_URL}" -t -c "SELECT count(*) FROM loans;" 2>/dev/null | xargs)
AUDIT_LATEST=$(psql "${SCRATCH_DATABASE_URL}" -t -c \
  "SELECT extract(epoch from (now() - max(occurred_at))) FROM audit_events;" 2>/dev/null | xargs)

log "users=${USERS} loans=${LOANS} audit_lag_sec=${AUDIT_LATEST}"

[ "${USERS:-0}" -gt 0 ] || fail "restored DB has zero users"
[ "${LOANS:-0}" -gt 0 ] || fail "restored DB has zero loans"

# Audit events should be at most a few hours stale (dump was just taken).
# If the newest audit event is >24h old, nobody has used the system — warn, don't fail.
if [ -n "${AUDIT_LATEST}" ] && (( $(echo "${AUDIT_LATEST} > 86400" | bc -l) )); then
  log "WARN: newest audit event is $(echo "${AUDIT_LATEST}/3600" | bc)h old"
  post_slack warn "Backup restored OK but audit activity is stale (${AUDIT_LATEST}s)"
fi

# 4. Archive dump to S3 with encryption (SOC 2 retention evidence)
if [ -n "${BACKUP_EVIDENCE_BUCKET:-}" ]; then
  log "Archiving dump to S3"
  aws s3 cp \
    "${DUMP}" \
    "s3://${BACKUP_EVIDENCE_BUCKET}/daily/${TIMESTAMP}.dump" \
    --sse AES256 \
    --storage-class STANDARD_IA \
    >>"${LOG}" 2>&1 || log "WARN: S3 archive failed (not fatal)"
fi

# 5. Teardown
rm -f "${DUMP}"
log "Verification passed"
post_slack ok "Backup verification passed. users=${USERS} loans=${LOANS}"
