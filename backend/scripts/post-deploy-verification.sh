#!/usr/bin/env bash
# 10-testing/post-deploy-verification.sh
#
# Automated version of the post-deploy checklist from REMEDIATION.md.
# Runs after production deploy. Each check exits non-zero on failure —
# run the whole script with `set -e` removed to collect all failures.

set -uo pipefail

: "${API_BASE_URL:?set API_BASE_URL to production API, e.g. https://api.perennia.ai}"
: "${FRONTEND_URL:?set FRONTEND_URL to production web, e.g. https://app.perennia.ai}"
: "${TEST_USER_EMAIL:?set TEST_USER_EMAIL}"
: "${TEST_USER_PASSWORD:?set TEST_USER_PASSWORD}"

FAILED=0
check() {
  local name=$1
  shift
  printf "  %-50s" "$name"
  if "$@" >/tmp/verify-out 2>&1; then
    echo "✓"
  else
    echo "✗"
    sed 's/^/      /' /tmp/verify-out
    FAILED=$((FAILED + 1))
  fi
}

echo "==> Post-deploy verification against ${API_BASE_URL}"
echo ""

# 1. Secrets — repo is clean
echo "Secrets hygiene"
check "gitleaks scan finds no secrets" \
  bash -c 'gitleaks detect --source . --no-banner --exit-code=1 2>&1 | grep -v "leaks found: 0" && exit 1 || exit 0'

# 2. Encryption
echo ""
echo "Encryption"
check "PII encryption validated at startup (health reports ok)" \
  bash -c 'curl -fsS "${API_BASE_URL}/health/ready" | jq -e ".status == \"ok\""'

# 3. Auth
echo ""
echo "Auth"

COOKIE_JAR=$(mktemp)
trap "rm -f ${COOKIE_JAR}" EXIT

check "login returns 200 and sets cookies" \
  bash -c '
    curl -fsS -c "'"${COOKIE_JAR}"'" \
      -H "Content-Type: application/json" \
      -d "{\"email\":\"'"${TEST_USER_EMAIL}"'\",\"password\":\"'"${TEST_USER_PASSWORD}"'\"}" \
      "'"${API_BASE_URL}"'/auth/login" >/dev/null
    grep -q "perennia_access" "'"${COOKIE_JAR}"'"
  '

check "access cookie is HttpOnly + Secure" \
  bash -c '
    awk "/perennia_access/ { if (\$0 ~ /HttpOnly/ && \$0 ~ /Secure/) exit 0 } END { exit 1 }" "'"${COOKIE_JAR}"'"
  '

check "CSRF cookie is NOT HttpOnly" \
  bash -c '
    awk "/perennia_csrf/ { if (\$0 !~ /HttpOnly/) exit 0 } END { exit 1 }" "'"${COOKIE_JAR}"'"
  '

check "fake Bearer token does not bypass CSRF on mutating requests" \
  bash -c '
    STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
      -X POST "'"${API_BASE_URL}"'/loans" \
      -H "Authorization: Bearer fake-token-should-not-work" \
      -H "Content-Type: application/json" \
      -d "{}")
    [ "$STATUS" = "401" ] || [ "$STATUS" = "403" ]
  '

check "refresh endpoint rotates token" \
  bash -c '
    OLD_REFRESH=$(grep perennia_refresh "'"${COOKIE_JAR}"'" | awk "{print \$7}")
    curl -fsS -b "'"${COOKIE_JAR}"'" -c "'"${COOKIE_JAR}"'" \
      -X POST "'"${API_BASE_URL}"'/auth/refresh" >/dev/null
    NEW_REFRESH=$(grep perennia_refresh "'"${COOKIE_JAR}"'" | awk "{print \$7}")
    [ "$OLD_REFRESH" != "$NEW_REFRESH" ]
  '

# 4. Rate limiting
echo ""
echo "Rate limiting"
check "10 failed logins returns 429" \
  bash -c '
    for i in $(seq 1 10); do
      curl -s -o /dev/null -X POST -H "Content-Type: application/json" \
        -d "{\"email\":\"attacker@example.com\",\"password\":\"wrong\"}" \
        "'"${API_BASE_URL}"'/auth/login" >/dev/null
    done
    STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
      -X POST -H "Content-Type: application/json" \
      -d "{\"email\":\"attacker@example.com\",\"password\":\"wrong\"}" \
      "'"${API_BASE_URL}"'/auth/login")
    [ "$STATUS" = "429" ]
  '

# 5. Audit logs
echo ""
echo "Audit logs"
check "USER_LOGIN event persisted in audit_events" \
  bash -c '
    # This assumes you have a DB-read test user or admin endpoint
    curl -fsS -b "'"${COOKIE_JAR}"'" \
      -H "X-CSRF-Token: $(awk "/perennia_csrf/{print \$7}" "'"${COOKIE_JAR}"'")" \
      "'"${API_BASE_URL}"'/admin/audit/events?event_type=USER_LOGIN&limit=1" \
      | jq -e ".items | length > 0"
  '

# 6. Frontend
echo ""
echo "Frontend"
check "initial HTML under 200KB" \
  bash -c '
    SIZE=$(curl -fsS -o /dev/null -w "%{size_download}" "'"${FRONTEND_URL}"'")
    [ "$SIZE" -lt 204800 ]
  '

check "no localStorage JWT references in index.html" \
  bash -c '
    ! curl -fsS "'"${FRONTEND_URL}"'" | grep -qE "localStorage\.(set|get|remove)Item.*(token|jwt)"
  '

# 7. Dependencies
echo ""
echo "Dependencies"
check "no critical npm vulnerabilities" \
  bash -c '
    cd frontend 2>/dev/null || cd ../frontend
    npm audit --audit-level=critical 2>/dev/null | grep -q "found 0 vulnerabilities"
  '

# 8. Migrations
echo ""
echo "Migrations"
check "alembic current returns a revision" \
  bash -c '
    cd backend 2>/dev/null || cd ../backend
    alembic current 2>/dev/null | grep -qE "[a-f0-9]{12}"
  '

# 9. DB
echo ""
echo "Database"
check "/health/ready returns 200 with DB + Redis healthy" \
  bash -c '
    RESPONSE=$(curl -fsS "'"${API_BASE_URL}"'/health/ready")
    echo "$RESPONSE" | jq -e ".status == \"ok\""
    echo "$RESPONSE" | jq -e ".checks.database.ok == true"
    echo "$RESPONSE" | jq -e ".checks.redis.ok == true"
  '

echo ""
if [ "$FAILED" -gt 0 ]; then
  echo "==> ${FAILED} check(s) failed."
  exit 1
fi

echo "==> All post-deploy verifications passed."
