#!/bin/bash
# =============================================================================
# Pipeline 360 UVIP Beta Launch Checklist
# =============================================================================
# Run this script to verify system readiness for beta launch
# Usage: ./scripts/beta_launch_checklist.sh [API_URL]

set -e

API_URL="${1:-https://mortgage-crm-production-7a9a.up.railway.app}"
PASS_COUNT=0
FAIL_COUNT=0
WARN_COUNT=0

echo "=============================================="
echo "  Pipeline 360 UVIP Beta Launch Checklist"
echo "=============================================="
echo "API URL: $API_URL"
echo "Time: $(date)"
echo ""

# Helper functions
pass() {
    echo "✅ PASS: $1"
    ((PASS_COUNT++))
}

fail() {
    echo "❌ FAIL: $1"
    ((FAIL_COUNT++))
}

warn() {
    echo "⚠️  WARN: $1"
    ((WARN_COUNT++))
}

info() {
    echo "ℹ️  $1"
}

# Get auth token
get_token() {
    TOKEN=$(curl -s -X POST "$API_URL/token" \
        -H "Content-Type: application/x-www-form-urlencoded" \
        -d "username=admin@perenniaai.com&password=demo123" | \
        python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null)
    echo "$TOKEN"
}

echo "=== 1. Infrastructure Checks ==="
echo ""

# Health endpoint
info "Checking health endpoint..."
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL/health" --max-time 10)
if [ "$HTTP_CODE" = "200" ]; then
    pass "Health endpoint accessible"
else
    fail "Health endpoint not responding (HTTP $HTTP_CODE)"
fi

# Auth system
info "Checking authentication..."
TOKEN=$(get_token)
if [ -n "$TOKEN" ] && [ "$TOKEN" != "null" ]; then
    pass "Authentication working"
else
    fail "Authentication not working"
    echo "   Cannot continue without authentication"
    exit 1
fi

echo ""
echo "=== 2. Core API Endpoints ==="
echo ""

# Loans
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL/api/v1/loans/" -H "Authorization: Bearer $TOKEN" --max-time 15)
[ "$HTTP_CODE" = "200" ] && pass "Loans endpoint" || fail "Loans endpoint (HTTP $HTTP_CODE)"

# Leads
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL/api/v1/leads/" -H "Authorization: Bearer $TOKEN" --max-time 15)
[ "$HTTP_CODE" = "200" ] && pass "Leads endpoint" || fail "Leads endpoint (HTTP $HTTP_CODE)"

# Tasks
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL/api/v1/tasks/" -H "Authorization: Bearer $TOKEN" --max-time 15)
[ "$HTTP_CODE" = "200" ] && pass "Tasks endpoint" || fail "Tasks endpoint (HTTP $HTTP_CODE)"

# Communications
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL/api/v1/communications/" -H "Authorization: Bearer $TOKEN" --max-time 15)
[ "$HTTP_CODE" = "200" ] && pass "Communications endpoint" || warn "Communications endpoint (HTTP $HTTP_CODE)"

echo ""
echo "=== 3. UVIP Features (Phase 1-3) ==="
echo ""

# Video Clips
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL/api/v1/clips/" -H "Authorization: Bearer $TOKEN" --max-time 15)
[ "$HTTP_CODE" = "200" ] && pass "Video Clips endpoint" || fail "Video Clips endpoint (HTTP $HTTP_CODE)"

# Clip Templates
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL/api/v1/clips/templates" -H "Authorization: Bearer $TOKEN" --max-time 15)
[ "$HTTP_CODE" = "200" ] && pass "Clip Templates endpoint" || fail "Clip Templates endpoint (HTTP $HTTP_CODE)"

# Meeting Rooms
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL/api/v1/meetings/rooms" -H "Authorization: Bearer $TOKEN" --max-time 15)
[ "$HTTP_CODE" = "200" ] && pass "Meeting Rooms endpoint" || fail "Meeting Rooms endpoint (HTTP $HTTP_CODE)"

# Meeting Stats
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL/api/v1/meetings/stats" -H "Authorization: Bearer $TOKEN" --max-time 15)
[ "$HTTP_CODE" = "200" ] && pass "Meeting Stats endpoint" || fail "Meeting Stats endpoint (HTTP $HTTP_CODE)"

echo ""
echo "=== 4. AI & Analytics ==="
echo ""

# Pipeline Analytics
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL/api/v1/analytics/pipeline" -H "Authorization: Bearer $TOKEN" --max-time 15)
[ "$HTTP_CODE" = "200" ] && pass "Pipeline Analytics" || fail "Pipeline Analytics (HTTP $HTTP_CODE)"

# AI Orchestrator
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$API_URL/api/v1/ai/orchestrator-chat" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"message":"test"}' --max-time 30)
if [ "$HTTP_CODE" = "200" ]; then
    pass "AI Orchestrator"
else
    warn "AI Orchestrator (HTTP $HTTP_CODE) - may need API keys"
fi

echo ""
echo "=== 5. Beta Program Features ==="
echo ""

# Beta Application endpoint
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$API_URL/api/v1/beta/apply" \
    -H "Content-Type: application/json" \
    -d '{"company_name":"Test","contact_name":"Test","email":"test@test.com","team_size":"1-5"}' --max-time 15)
if [ "$HTTP_CODE" = "200" ]; then
    pass "Beta Application endpoint"
else
    warn "Beta Application endpoint (HTTP $HTTP_CODE) - may need setup"
fi

# Analytics Tracking
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$API_URL/api/v1/analytics/track" \
    -H "Content-Type: application/json" \
    -d '{"event":"test_event","properties":{}}' --max-time 15)
if [ "$HTTP_CODE" = "200" ]; then
    pass "Analytics Tracking endpoint"
else
    warn "Analytics Tracking endpoint (HTTP $HTTP_CODE)"
fi

echo ""
echo "=== 6. Financial Intelligence ==="
echo ""

# Gain on Sale
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL/api/v1/financial-intelligence/gain-on-sale" -H "Authorization: Bearer $TOKEN" --max-time 15)
[ "$HTTP_CODE" = "200" ] && pass "Gain on Sale" || warn "Gain on Sale (HTTP $HTTP_CODE)"

# Cost Per Loan
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL/api/v1/financial-intelligence/cost-per-loan" -H "Authorization: Bearer $TOKEN" --max-time 15)
[ "$HTTP_CODE" = "200" ] && pass "Cost Per Loan" || warn "Cost Per Loan (HTTP $HTTP_CODE)"

echo ""
echo "=== 7. Documentation & Support ==="
echo ""

# OpenAPI Docs
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL/docs" --max-time 10)
[ "$HTTP_CODE" = "200" ] && pass "API Documentation (/docs)" || fail "API Documentation (HTTP $HTTP_CODE)"

# OpenAPI JSON
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL/openapi.json" --max-time 10)
[ "$HTTP_CODE" = "200" ] && pass "OpenAPI JSON" || fail "OpenAPI JSON (HTTP $HTTP_CODE)"

echo ""
echo "=============================================="
echo "  Beta Launch Readiness Summary"
echo "=============================================="
echo ""
echo "✅ Passed:  $PASS_COUNT"
echo "⚠️  Warnings: $WARN_COUNT"
echo "❌ Failed:  $FAIL_COUNT"
echo ""

TOTAL=$((PASS_COUNT + FAIL_COUNT))
SCORE=$((PASS_COUNT * 100 / TOTAL))

echo "Readiness Score: $SCORE%"
echo ""

if [ "$FAIL_COUNT" -eq 0 ]; then
    echo "🎉 READY FOR BETA LAUNCH!"
    echo ""
    echo "Next steps:"
    echo "1. Share beta application link"
    echo "2. Recruit first 5-10 users"
    echo "3. Schedule onboarding calls"
    echo "4. Monitor Sentry for errors"
    exit 0
elif [ "$FAIL_COUNT" -le 2 ]; then
    echo "⚠️  ALMOST READY - Fix $FAIL_COUNT critical issues"
    exit 1
else
    echo "❌ NOT READY - Fix $FAIL_COUNT critical issues before launch"
    exit 1
fi
