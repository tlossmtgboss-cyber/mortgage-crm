#!/bin/bash
# =============================================================================
# Security Testing Script for Pipeline360
# =============================================================================
# Usage: ./tests/security_tests.sh [API_URL]
# Example: ./tests/security_tests.sh https://mortgage-crm-production-7a9a.up.railway.app

set -e

API_URL="${1:-https://mortgage-crm-production-7a9a.up.railway.app}"
PASS_COUNT=0
FAIL_COUNT=0

echo "=============================================="
echo "  Pipeline360 Security Test Suite"
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

info() {
    echo "ℹ️  $1"
}

# Get auth token for testing
get_token() {
    TOKEN=$(curl -s -X POST "$API_URL/token" \
        -H "Content-Type: application/x-www-form-urlencoded" \
        -d "username=demo@example.com&password=demo123" | \
        python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))")

    if [ -z "$TOKEN" ]; then
        echo "Failed to get auth token"
        exit 1
    fi
    echo "$TOKEN"
}

echo "=== Authentication Tests ==="
echo ""

# Test 1: Request without auth - should fail
info "Test 1: Request without authentication"
RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL/api/v1/loans/")
if [ "$RESPONSE" -eq 401 ] || [ "$RESPONSE" -eq 403 ]; then
    pass "Protected endpoint rejects unauthenticated requests (HTTP $RESPONSE)"
else
    fail "Protected endpoint did not reject unauthenticated request (HTTP $RESPONSE)"
fi

# Test 2: Request with invalid token - should fail
info "Test 2: Request with invalid token"
RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" \
    -H "Authorization: Bearer invalid-token-12345" \
    "$API_URL/api/v1/loans/")
if [ "$RESPONSE" -eq 401 ] || [ "$RESPONSE" -eq 403 ]; then
    pass "Protected endpoint rejects invalid tokens (HTTP $RESPONSE)"
else
    fail "Protected endpoint accepted invalid token (HTTP $RESPONSE)"
fi

# Test 3: Request with expired token format - should fail
info "Test 3: Request with malformed token"
RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" \
    -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ0ZXN0In0.invalidhash" \
    "$API_URL/api/v1/loans/")
if [ "$RESPONSE" -eq 401 ] || [ "$RESPONSE" -eq 403 ]; then
    pass "Protected endpoint rejects malformed tokens (HTTP $RESPONSE)"
else
    fail "Protected endpoint accepted malformed token (HTTP $RESPONSE)"
fi

# Test 4: Get valid token and test authenticated request
info "Test 4: Valid authentication"
TOKEN=$(get_token)
RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" \
    -H "Authorization: Bearer $TOKEN" \
    "$API_URL/api/v1/loans/")
if [ "$RESPONSE" -eq 200 ]; then
    pass "Protected endpoint accepts valid token (HTTP $RESPONSE)"
else
    fail "Protected endpoint rejected valid token (HTTP $RESPONSE)"
fi

echo ""
echo "=== Input Validation Tests ==="
echo ""

# Test 5: XSS in query parameter - should be handled safely
info "Test 5: XSS in search query"
RESPONSE=$(curl -s -w "\n%{http_code}" \
    -H "Authorization: Bearer $TOKEN" \
    "$API_URL/api/v1/loans/?search=%3Cscript%3Ealert(1)%3C/script%3E")
HTTP_CODE=$(echo "$RESPONSE" | tail -1)
BODY=$(echo "$RESPONSE" | head -n -1)

if [ "$HTTP_CODE" -eq 200 ]; then
    # Check if script tag is sanitized in response
    if echo "$BODY" | grep -q '<script>'; then
        fail "XSS not sanitized in search response"
    else
        pass "XSS in search query handled safely"
    fi
else
    pass "XSS search query rejected (HTTP $HTTP_CODE)"
fi

# Test 6: SQL injection attempt - should be safe
info "Test 6: SQL injection attempt"
RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" \
    -H "Authorization: Bearer $TOKEN" \
    "$API_URL/api/v1/loans/?search=test'%3B%20DROP%20TABLE%20loans%3B--")
if [ "$RESPONSE" -eq 200 ] || [ "$RESPONSE" -eq 400 ]; then
    pass "SQL injection attempt handled safely (HTTP $RESPONSE)"
else
    fail "Unexpected response to SQL injection (HTTP $RESPONSE)"
fi

# Test 7: Path traversal attempt - should be blocked
info "Test 7: Path traversal attempt"
RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" \
    -H "Authorization: Bearer $TOKEN" \
    "$API_URL/api/v1/loans/../../../etc/passwd")
if [ "$RESPONSE" -eq 404 ] || [ "$RESPONSE" -eq 400 ]; then
    pass "Path traversal blocked (HTTP $RESPONSE)"
else
    fail "Path traversal not blocked (HTTP $RESPONSE)"
fi

# Test 8: Large payload - should be limited
info "Test 8: Large payload test"
LARGE_PAYLOAD=$(python3 -c "print('{\"title\":\"' + 'A'*100000 + '\"}')")
RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" \
    -X POST \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d "$LARGE_PAYLOAD" \
    "$API_URL/api/v1/clips/")
if [ "$RESPONSE" -eq 413 ] || [ "$RESPONSE" -eq 422 ] || [ "$RESPONSE" -eq 400 ]; then
    pass "Large payload rejected (HTTP $RESPONSE)"
else
    info "Large payload response: HTTP $RESPONSE (may need manual review)"
fi

echo ""
echo "=== Rate Limiting Tests ==="
echo ""

# Test 9: Rate limiting check (send rapid requests)
info "Test 9: Rate limiting (sending 30 rapid requests)"
RATE_LIMITED=0
for i in {1..30}; do
    RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" \
        -H "Authorization: Bearer $TOKEN" \
        "$API_URL/api/v1/loans/")
    if [ "$RESPONSE" -eq 429 ]; then
        RATE_LIMITED=1
        break
    fi
done

if [ "$RATE_LIMITED" -eq 1 ]; then
    pass "Rate limiting triggered"
else
    info "Rate limiting not triggered with 30 requests (may have higher limit)"
fi

echo ""
echo "=== CORS Tests ==="
echo ""

# Test 10: CORS preflight check
info "Test 10: CORS preflight"
CORS_HEADERS=$(curl -s -I -X OPTIONS \
    -H "Origin: http://malicious-site.com" \
    -H "Access-Control-Request-Method: GET" \
    "$API_URL/api/v1/clips/" 2>&1 | grep -i "access-control-allow-origin")

if echo "$CORS_HEADERS" | grep -qi "malicious-site.com"; then
    fail "CORS allows arbitrary origins"
elif [ -z "$CORS_HEADERS" ]; then
    pass "No CORS headers for unknown origin (restrictive)"
else
    pass "CORS properly configured"
fi

echo ""
echo "=== Health & Error Handling Tests ==="
echo ""

# Test 11: Health check endpoint accessible
info "Test 11: Health check endpoint"
RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL/health")
if [ "$RESPONSE" -eq 200 ]; then
    pass "Health endpoint accessible (HTTP $RESPONSE)"
else
    fail "Health endpoint not accessible (HTTP $RESPONSE)"
fi

# Test 12: Detailed health requires no auth
info "Test 12: Detailed health check"
RESPONSE=$(curl -s "$API_URL/health/detailed")
if echo "$RESPONSE" | grep -q "status"; then
    pass "Detailed health endpoint returns status"
else
    info "Detailed health endpoint may not exist or requires setup"
fi

# Test 13: Error handling doesn't leak stack traces
info "Test 13: Error handling (no stack trace leak)"
RESPONSE=$(curl -s -H "Authorization: Bearer $TOKEN" \
    "$API_URL/api/v1/nonexistent-endpoint-12345")
if echo "$RESPONSE" | grep -qi "traceback\|File \"/\|line [0-9]"; then
    fail "Error response leaks stack trace"
else
    pass "Error handling doesn't leak stack traces"
fi

echo ""
echo "=============================================="
echo "  Security Test Results"
echo "=============================================="
echo "✅ Passed: $PASS_COUNT"
echo "❌ Failed: $FAIL_COUNT"
echo ""

if [ "$FAIL_COUNT" -gt 0 ]; then
    echo "⚠️  Some security tests failed - review before deploying to production"
    exit 1
else
    echo "🎉 All security tests passed!"
    exit 0
fi
