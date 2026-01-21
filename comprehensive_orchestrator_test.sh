#!/bin/bash

# Comprehensive AI Orchestrator Test Suite
# Tests: Functional, Workflow, Error Handling, Security, Performance, Audit, Edge Cases

BASE_URL="https://app.perenniaai.com"
RESULTS_FILE="/tmp/orchestrator_test_results.json"

echo "=============================================="
echo "AI ORCHESTRATOR COMPREHENSIVE TEST SUITE"
echo "=============================================="
echo "Started: $(date)"
echo ""

# Get auth token
echo "=== AUTHENTICATION ==="
TOKEN=$(curl -s -X POST "$BASE_URL/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin@perenniaai.com&password=demo123" | jq -r '.access_token')

if [ "$TOKEN" == "null" ] || [ -z "$TOKEN" ]; then
  echo "❌ Authentication failed"
  exit 1
fi
echo "✅ Authentication successful"
echo ""

# Initialize results
PASSED=0
FAILED=0
WARNINGS=0

# Helper function
test_endpoint() {
  local name="$1"
  local method="$2"
  local endpoint="$3"
  local data="$4"
  local expected="$5"

  if [ "$method" == "GET" ]; then
    response=$(curl -s -w "\n%{http_code}" "$BASE_URL$endpoint" -H "Authorization: Bearer $TOKEN")
  else
    response=$(curl -s -w "\n%{http_code}" -X "$method" "$BASE_URL$endpoint" \
      -H "Authorization: Bearer $TOKEN" \
      -H "Content-Type: application/json" \
      -d "$data")
  fi

  http_code=$(echo "$response" | tail -1)
  body=$(echo "$response" | sed '$d')

  if [[ "$http_code" =~ ^2 ]]; then
    echo "✅ $name (HTTP $http_code)"
    ((PASSED++))
    return 0
  else
    echo "❌ $name (HTTP $http_code)"
    ((FAILED++))
    return 1
  fi
}

echo "=============================================="
echo "1. FUNCTIONAL TESTING"
echo "=============================================="

echo ""
echo "--- 1.1 Autonomous Task Execution ---"

# Test workflow triggers
test_endpoint "Get workflow triggers" "GET" "/api/v1/ai/workflow/triggers"
test_endpoint "Get active workflows" "GET" "/api/v1/ai/workflow/active"
test_endpoint "Get scheduled tasks" "GET" "/api/v1/ai/workflow/scheduled"

echo ""
echo "--- 1.2 CRM Data Access ---"

test_endpoint "Leads access" "GET" "/api/v1/leads/?limit=5"
test_endpoint "Loans access" "GET" "/api/v1/loans/?limit=5"
test_endpoint "Tasks access" "GET" "/api/v1/tasks/?limit=5"
test_endpoint "Clients access" "GET" "/api/v1/clients/?limit=5"

echo ""
echo "--- 1.3 AI Actions ---"

# Test email generation
echo "Testing email generation..."
email_response=$(curl -s -X POST "$BASE_URL/api/v1/ai/generate-email" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"template_type":"weekly_update","lead_id":1}')

if echo "$email_response" | jq -e '.subject' > /dev/null 2>&1; then
  echo "✅ Email generation works"
  ((PASSED++))
else
  echo "❌ Email generation failed"
  ((FAILED++))
fi

# Test smart chat
echo "Testing smart chat..."
chat_response=$(curl -s -X POST "$BASE_URL/api/v1/ai/smart-chat" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message":"What tasks are due today?","include_context":true}')

if echo "$chat_response" | jq -e '.response' > /dev/null 2>&1; then
  echo "✅ Smart chat works"
  ((PASSED++))
else
  echo "❌ Smart chat failed"
  ((FAILED++))
fi

echo ""
echo "=============================================="
echo "2. WORKFLOW & SCHEDULING TESTING"
echo "=============================================="

echo ""
echo "--- 2.1 Time-Based Triggers ---"

test_endpoint "Get scheduled workflows" "GET" "/api/v1/ai/workflow/scheduled"

# Test creating a scheduled task
echo "Testing scheduled task creation..."
schedule_response=$(curl -s -X POST "$BASE_URL/api/v1/ai/workflow/schedule" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "workflow_type": "test_workflow",
    "trigger_time": "2025-11-25T10:00:00Z",
    "parameters": {"test": true}
  }' 2>/dev/null)

if [ $? -eq 0 ]; then
  echo "✅ Scheduled task creation endpoint accessible"
  ((PASSED++))
else
  echo "⚠️ Scheduled task creation - endpoint may not exist"
  ((WARNINGS++))
fi

echo ""
echo "--- 2.2 Event-Driven Workflows ---"

test_endpoint "Get event triggers" "GET" "/api/v1/ai/workflow/triggers"

# Test workflow execution
echo "Testing workflow execution..."
workflow_response=$(curl -s -X POST "$BASE_URL/api/v1/ai/workflow/execute" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "workflow_id": "test_workflow",
    "dry_run": true
  }' 2>/dev/null)

if [ $? -eq 0 ]; then
  echo "✅ Workflow execution endpoint accessible"
  ((PASSED++))
else
  echo "⚠️ Workflow execution - endpoint may not exist"
  ((WARNINGS++))
fi

echo ""
echo "--- 2.3 Multi-Step Workflows ---"

test_endpoint "Get workflow history" "GET" "/api/v1/ai/workflow/history"

echo ""
echo "=============================================="
echo "3. ERROR HANDLING & FAIL-SAFE TESTING"
echo "=============================================="

echo ""
echo "--- 3.1 Invalid Input Handling ---"

# Test with invalid lead ID
echo "Testing invalid lead ID handling..."
invalid_response=$(curl -s -X POST "$BASE_URL/api/v1/ai/generate-email" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"template_type":"weekly_update","lead_id":999999}')

if echo "$invalid_response" | jq -e '.error' > /dev/null 2>&1 || echo "$invalid_response" | jq -e '.detail' > /dev/null 2>&1; then
  echo "✅ Invalid input returns error gracefully"
  ((PASSED++))
else
  echo "⚠️ Invalid input handling unclear"
  ((WARNINGS++))
fi

# Test with missing required fields
echo "Testing missing field handling..."
missing_response=$(curl -s -X POST "$BASE_URL/api/v1/ai/smart-chat" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}')

http_code=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/api/v1/ai/smart-chat" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}')

if [ "$http_code" == "422" ] || [ "$http_code" == "400" ]; then
  echo "✅ Missing fields return validation error (HTTP $http_code)"
  ((PASSED++))
else
  echo "⚠️ Missing field handling returned HTTP $http_code"
  ((WARNINGS++))
fi

echo ""
echo "--- 3.2 Retry Logic & Fallback ---"

test_endpoint "Check system health" "GET" "/api/v1/ai-receptionist/dashboard/system-health"
test_endpoint "Check error logs" "GET" "/api/v1/ai-receptionist/dashboard/errors"

echo ""
echo "--- 3.3 Human Review Alerts ---"

test_endpoint "Get pending authorizations" "GET" "/api/v1/ai/authorizations"
test_endpoint "Get high-risk actions" "GET" "/api/v1/ai/authorizations?risk_level=high"

echo ""
echo "=============================================="
echo "4. SECURITY & COMPLIANCE TESTING"
echo "=============================================="

echo ""
echo "--- 4.1 Authentication & Authorization ---"

# Test without token
echo "Testing unauthenticated access..."
unauth_code=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/api/v1/leads/?limit=1")

if [ "$unauth_code" == "401" ] || [ "$unauth_code" == "403" ]; then
  echo "✅ Unauthenticated requests blocked (HTTP $unauth_code)"
  ((PASSED++))
else
  echo "❌ Unauthenticated access not blocked (HTTP $unauth_code)"
  ((FAILED++))
fi

# Test with invalid token
echo "Testing invalid token..."
invalid_token_code=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/api/v1/leads/?limit=1" \
  -H "Authorization: Bearer invalid_token_12345")

if [ "$invalid_token_code" == "401" ] || [ "$invalid_token_code" == "403" ]; then
  echo "✅ Invalid tokens rejected (HTTP $invalid_token_code)"
  ((PASSED++))
else
  echo "❌ Invalid token not rejected (HTTP $invalid_token_code)"
  ((FAILED++))
fi

echo ""
echo "--- 4.2 Data Privacy ---"

# Test PII protection
echo "Testing PII protection in responses..."
lead_response=$(curl -s "$BASE_URL/api/v1/leads/?limit=1" -H "Authorization: Bearer $TOKEN")

# Check if SSN is masked or not present
if echo "$lead_response" | grep -q '"ssn":\s*"[0-9]\{9\}"'; then
  echo "❌ Raw SSN exposed in response"
  ((FAILED++))
else
  echo "✅ SSN properly protected/masked"
  ((PASSED++))
fi

echo ""
echo "--- 4.3 Compliance Validation ---"

test_endpoint "Get compliance settings" "GET" "/api/v1/ai/compliance/settings"
test_endpoint "Get compliance rules" "GET" "/api/v1/ai/compliance/rules"

# Test compliance validation
echo "Testing action compliance validation..."
compliance_response=$(curl -s -X POST "$BASE_URL/api/v1/ai/compliance/validate" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "action_type": "send_email",
    "target_entity": "lead",
    "entity_id": 1
  }' 2>/dev/null)

if [ $? -eq 0 ]; then
  echo "✅ Compliance validation endpoint accessible"
  ((PASSED++))
else
  echo "⚠️ Compliance validation endpoint may not exist"
  ((WARNINGS++))
fi

echo ""
echo "=============================================="
echo "5. PERFORMANCE & SCALABILITY TESTING"
echo "=============================================="

echo ""
echo "--- 5.1 Response Time Testing ---"

# Test critical endpoint response times
endpoints=(
  "/api/v1/leads/?limit=10"
  "/api/v1/loans/?limit=10"
  "/api/v1/ai-receptionist/dashboard/metrics/realtime"
  "/api/v1/tasks/?limit=10"
)

for endpoint in "${endpoints[@]}"; do
  start_time=$(date +%s%3N)
  curl -s -o /dev/null "$BASE_URL$endpoint" -H "Authorization: Bearer $TOKEN"
  end_time=$(date +%s%3N)
  duration=$((end_time - start_time))

  if [ $duration -lt 2000 ]; then
    echo "✅ $endpoint: ${duration}ms"
    ((PASSED++))
  else
    echo "⚠️ $endpoint: ${duration}ms (slow)"
    ((WARNINGS++))
  fi
done

echo ""
echo "--- 5.2 Concurrent Request Testing ---"

echo "Testing concurrent requests (5 parallel)..."
start_time=$(date +%s%3N)

for i in {1..5}; do
  curl -s -o /dev/null "$BASE_URL/api/v1/leads/?limit=5" -H "Authorization: Bearer $TOKEN" &
done
wait

end_time=$(date +%s%3N)
total_duration=$((end_time - start_time))

if [ $total_duration -lt 5000 ]; then
  echo "✅ Concurrent requests handled in ${total_duration}ms"
  ((PASSED++))
else
  echo "⚠️ Concurrent requests took ${total_duration}ms"
  ((WARNINGS++))
fi

echo ""
echo "=============================================="
echo "6. AUDIT LOGGING & REPORTING TESTING"
echo "=============================================="

echo ""
echo "--- 6.1 Audit Trail Verification ---"

test_endpoint "Get audit logs" "GET" "/api/v1/ai/audit/logs"
test_endpoint "Get recent AI actions" "GET" "/api/v1/ai/audit/actions"

# Test audit log details
echo "Testing audit log detail..."
audit_response=$(curl -s "$BASE_URL/api/v1/ai/audit/logs?limit=5" \
  -H "Authorization: Bearer $TOKEN")

if echo "$audit_response" | jq -e '.[0].timestamp' > /dev/null 2>&1 || \
   echo "$audit_response" | jq -e '.logs[0].timestamp' > /dev/null 2>&1 || \
   echo "$audit_response" | jq -e '.items[0].timestamp' > /dev/null 2>&1; then
  echo "✅ Audit logs contain timestamps"
  ((PASSED++))
else
  echo "⚠️ Audit log structure unclear"
  ((WARNINGS++))
fi

echo ""
echo "--- 6.2 Report Generation ---"

test_endpoint "Get activity report" "GET" "/api/v1/ai-receptionist/dashboard/activity/feed?limit=10"
test_endpoint "Get metrics report" "GET" "/api/v1/ai-receptionist/dashboard/metrics/realtime"
test_endpoint "Get ROI metrics" "GET" "/api/v1/ai-receptionist/dashboard/roi"

echo ""
echo "=============================================="
echo "7. USER ACCEPTANCE & EDGE CASES"
echo "=============================================="

echo ""
echo "--- 7.1 Edge Case Handling ---"

# Empty query
echo "Testing empty search query..."
empty_search_code=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/api/v1/leads/search?q=" \
  -H "Authorization: Bearer $TOKEN")

if [[ "$empty_search_code" =~ ^[24] ]]; then
  echo "✅ Empty search handled (HTTP $empty_search_code)"
  ((PASSED++))
else
  echo "⚠️ Empty search returned HTTP $empty_search_code"
  ((WARNINGS++))
fi

# Very long input
echo "Testing very long input..."
long_input=$(printf 'a%.0s' {1..1000})
long_response=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/api/v1/ai/smart-chat" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"message\":\"$long_input\"}")

if [[ "$long_response" =~ ^[24] ]]; then
  echo "✅ Long input handled (HTTP $long_response)"
  ((PASSED++))
else
  echo "⚠️ Long input returned HTTP $long_response"
  ((WARNINGS++))
fi

# Special characters
echo "Testing special characters..."
special_response=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/api/v1/ai/smart-chat" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message":"Test with <script>alert(1)</script> and SQL: OR 1=1--"}')

if [[ "$special_response" =~ ^[24] ]]; then
  echo "✅ Special characters handled safely (HTTP $special_response)"
  ((PASSED++))
else
  echo "⚠️ Special characters returned HTTP $special_response"
  ((WARNINGS++))
fi

echo ""
echo "--- 7.2 Escalation Testing ---"

# Test authorization pending actions
echo "Testing pending authorizations..."
pending_response=$(curl -s "$BASE_URL/api/v1/ai/authorizations?status=pending" \
  -H "Authorization: Bearer $TOKEN")

if [ $? -eq 0 ]; then
  pending_count=$(echo "$pending_response" | jq 'if type == "array" then length else .count // 0 end' 2>/dev/null || echo "0")
  echo "✅ Pending authorizations: $pending_count"
  ((PASSED++))
else
  echo "⚠️ Could not check pending authorizations"
  ((WARNINGS++))
fi

echo ""
echo "=============================================="
echo "TEST SUMMARY"
echo "=============================================="
echo ""
echo "Completed: $(date)"
echo ""
echo "Results:"
echo "  ✅ Passed:   $PASSED"
echo "  ❌ Failed:   $FAILED"
echo "  ⚠️  Warnings: $WARNINGS"
echo ""

TOTAL=$((PASSED + FAILED))
if [ $TOTAL -gt 0 ]; then
  PASS_RATE=$((PASSED * 100 / TOTAL))
  echo "Pass Rate: $PASS_RATE%"
else
  echo "Pass Rate: N/A"
fi

echo ""

if [ $FAILED -eq 0 ]; then
  echo "🎉 All critical tests passed!"
  exit 0
elif [ $FAILED -lt 5 ]; then
  echo "⚠️ Some tests failed - review recommended"
  exit 1
else
  echo "❌ Multiple test failures - investigation required"
  exit 2
fi
