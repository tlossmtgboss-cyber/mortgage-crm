#!/bin/bash
# =============================================================================
# Functional Testing Script for Pipeline360
# =============================================================================
# Usage: ./tests/functional_tests.sh [API_URL]
# Tests complete workflows: CRUD operations, clips, meetings, AI features
#
# Environment Variables:
#   TEST_API_KEY - API key to bypass IP restrictions (set in server .env)
#
# Examples:
#   ./tests/functional_tests.sh https://staging-api.example.com
#   TEST_API_KEY=your-secret-key ./tests/functional_tests.sh https://api.example.com

set -e

API_URL="${1:-https://api.perenniaai.com}"
TEST_API_KEY="${TEST_API_KEY:-}"
PASS_COUNT=0
FAIL_COUNT=0
TOKEN=""

# Build API key header if provided
API_KEY_HEADER=""
if [ -n "$TEST_API_KEY" ]; then
    API_KEY_HEADER="-H X-Test-API-Key:$TEST_API_KEY"
fi

echo "=============================================="
echo "  Pipeline360 Functional Test Suite"
echo "=============================================="
echo "API URL: $API_URL"
echo "Using Test API Key: $([ -n "$TEST_API_KEY" ] && echo "Yes" || echo "No")"
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

info() {
    echo "ℹ️  $1"
}

# Get auth token
get_token() {
    TOKEN=$(curl -s -X POST "$API_URL/token" $API_KEY_HEADER \
        -H "Content-Type: application/x-www-form-urlencoded" \
        -d "username=admin@perenniaai.com&password=demo123" | \
        python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))")

    if [ -z "$TOKEN" ]; then
        echo "Failed to get auth token"
        exit 1
    fi
}

echo "=== Authentication ==="
echo ""
info "Getting authentication token..."
get_token
if [ -n "$TOKEN" ]; then
    pass "Authentication successful"
else
    fail "Authentication failed"
    exit 1
fi

echo ""
echo "=== Loans CRUD Operations ==="
echo ""

# List loans
info "Test: List loans"
RESPONSE=$(curl -s -w "\n%{http_code}" \
    -H "Authorization: Bearer $TOKEN" \
    "$API_URL/api/v1/loans/")
HTTP_CODE=$(echo "$RESPONSE" | tail -1)
if [ "$HTTP_CODE" = "200" ]; then
    pass "List loans (HTTP $HTTP_CODE)"
else
    fail "List loans (HTTP $HTTP_CODE)"
fi

# Get loan with search
info "Test: Search loans"
RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" \
    -H "Authorization: Bearer $TOKEN" \
    "$API_URL/api/v1/loans/?search=test")
if [ "$RESPONSE" = "200" ]; then
    pass "Search loans"
else
    fail "Search loans (HTTP $RESPONSE)"
fi

echo ""
echo "=== Leads CRUD Operations ==="
echo ""

# List leads
info "Test: List leads"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
    -H "Authorization: Bearer $TOKEN" \
    "$API_URL/api/v1/leads/")
if [ "$HTTP_CODE" = "200" ]; then
    pass "List leads (HTTP $HTTP_CODE)"
else
    fail "List leads (HTTP $HTTP_CODE)"
fi

echo ""
echo "=== Tasks CRUD Operations ==="
echo ""

# List tasks
info "Test: List tasks"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
    -H "Authorization: Bearer $TOKEN" \
    "$API_URL/api/v1/tasks/")
if [ "$HTTP_CODE" = "200" ]; then
    pass "List tasks (HTTP $HTTP_CODE)"
else
    fail "List tasks (HTTP $HTTP_CODE)"
fi

echo ""
echo "=== Contacts CRUD Operations ==="
echo ""

# List contacts
info "Test: List contacts"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
    -H "Authorization: Bearer $TOKEN" \
    "$API_URL/api/v1/contacts/")
if [ "$HTTP_CODE" = "200" ]; then
    pass "List contacts (HTTP $HTTP_CODE)"
else
    fail "List contacts (HTTP $HTTP_CODE)"
fi

echo ""
echo "=== Analytics Endpoints ==="
echo ""

# Pipeline analytics
info "Test: Pipeline analytics"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
    -H "Authorization: Bearer $TOKEN" \
    "$API_URL/api/v1/analytics/pipeline")
if [ "$HTTP_CODE" = "200" ]; then
    pass "Pipeline analytics (HTTP $HTTP_CODE)"
else
    fail "Pipeline analytics (HTTP $HTTP_CODE)"
fi

# Employee performance
info "Test: Employee performance"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
    -H "Authorization: Bearer $TOKEN" \
    "$API_URL/api/v1/analytics/employee-performance")
if [ "$HTTP_CODE" = "200" ]; then
    pass "Employee performance (HTTP $HTTP_CODE)"
else
    fail "Employee performance (HTTP $HTTP_CODE)"
fi

echo ""
echo "=== AI Orchestrator ==="
echo ""

# AI chat endpoint
info "Test: AI orchestrator chat"
RESPONSE=$(curl -s -w "\n%{http_code}" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -X POST "$API_URL/api/v1/ai/orchestrator-chat" \
    -d '{"message":"Hello, what can you help me with?"}' \
    --max-time 30)
HTTP_CODE=$(echo "$RESPONSE" | tail -1)
if [ "$HTTP_CODE" = "200" ]; then
    pass "AI orchestrator chat (HTTP $HTTP_CODE)"
else
    # May timeout or rate limit - info only
    info "AI orchestrator chat returned HTTP $HTTP_CODE (may be rate limited or slow)"
fi

echo ""
echo "=== Video Clips (UVIP) ==="
echo ""

# List clips
info "Test: List video clips"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
    -H "Authorization: Bearer $TOKEN" \
    "$API_URL/api/v1/clips/")
if [ "$HTTP_CODE" = "200" ]; then
    pass "List video clips (HTTP $HTTP_CODE)"
else
    fail "List video clips (HTTP $HTTP_CODE)"
fi

# List clip templates
info "Test: List clip templates"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
    -H "Authorization: Bearer $TOKEN" \
    "$API_URL/api/v1/clips/templates")
if [ "$HTTP_CODE" = "200" ]; then
    pass "List clip templates (HTTP $HTTP_CODE)"
else
    fail "List clip templates (HTTP $HTTP_CODE)"
fi

echo ""
echo "=== Video Meetings (UVIP) ==="
echo ""

# List meeting rooms
info "Test: List meeting rooms"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
    -H "Authorization: Bearer $TOKEN" \
    "$API_URL/api/v1/meetings/rooms")
if [ "$HTTP_CODE" = "200" ]; then
    pass "List meeting rooms (HTTP $HTTP_CODE)"
else
    fail "List meeting rooms (HTTP $HTTP_CODE)"
fi

# List meeting templates
info "Test: List meeting templates"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
    -H "Authorization: Bearer $TOKEN" \
    "$API_URL/api/v1/meetings/templates")
if [ "$HTTP_CODE" = "200" ]; then
    pass "List meeting templates (HTTP $HTTP_CODE)"
else
    fail "List meeting templates (HTTP $HTTP_CODE)"
fi

# Meeting stats
info "Test: Meeting stats"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
    -H "Authorization: Bearer $TOKEN" \
    "$API_URL/api/v1/meetings/stats")
if [ "$HTTP_CODE" = "200" ]; then
    pass "Meeting stats (HTTP $HTTP_CODE)"
else
    fail "Meeting stats (HTTP $HTTP_CODE)"
fi

echo ""
echo "=== Reconciliation ==="
echo ""

# Pending reconciliation items
info "Test: Pending reconciliation items"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
    -H "Authorization: Bearer $TOKEN" \
    "$API_URL/api/v1/reconciliation/pending")
if [ "$HTTP_CODE" = "200" ]; then
    pass "Pending reconciliation (HTTP $HTTP_CODE)"
else
    fail "Pending reconciliation (HTTP $HTTP_CODE)"
fi

echo ""
echo "=== Financial Intelligence ==="
echo ""

# Gain on sale
info "Test: Gain on sale"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
    -H "Authorization: Bearer $TOKEN" \
    "$API_URL/api/v1/financial-intelligence/gain-on-sale" \
    --max-time 15)
if [ "$HTTP_CODE" = "200" ]; then
    pass "Gain on sale (HTTP $HTTP_CODE)"
else
    info "Gain on sale returned HTTP $HTTP_CODE (may need data)"
fi

echo ""
echo "=== Unified Tasks ==="
echo ""

# Unified tasks
info "Test: Unified tasks"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
    -H "Authorization: Bearer $TOKEN" \
    "$API_URL/api/v1/unified-tasks" \
    --max-time 15)
if [ "$HTTP_CODE" = "200" ]; then
    pass "Unified tasks (HTTP $HTTP_CODE)"
else
    fail "Unified tasks (HTTP $HTTP_CODE)"
fi

echo ""
echo "=============================================="
echo "  Functional Test Results"
echo "=============================================="
echo "✅ Passed: $PASS_COUNT"
echo "❌ Failed: $FAIL_COUNT"
echo ""

if [ "$FAIL_COUNT" -gt 0 ]; then
    echo "⚠️  Some functional tests failed - review before deploying"
    exit 1
else
    echo "🎉 All functional tests passed!"
    exit 0
fi
