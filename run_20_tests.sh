#!/bin/bash

# 20 Comprehensive CRM Tests
# Tests all major endpoints and functionality

API_URL="https://app.perenniaai.com/api/v1"
PASSED=0
FAILED=0

echo "=========================================="
echo "🧪 Running 20 Comprehensive CRM Tests"
echo "=========================================="
echo ""

# Get auth token first
echo "🔐 Authenticating..."
TOKEN_RESPONSE=$(curl -s -X POST "https://app.perenniaai.com/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin@perenniaai.com&password=demo123")

TOKEN=$(echo "$TOKEN_RESPONSE" | grep -o '"access_token":"[^"]*' | cut -d'"' -f4)

if [ -z "$TOKEN" ]; then
  echo "❌ Failed to get authentication token"
  exit 1
fi

echo "✅ Authentication successful"
echo ""

# Test function
run_test() {
  local test_num=$1
  local test_name=$2
  local endpoint=$3
  local method=${4:-GET}
  local data=${5:-}

  echo "Test $test_num: $test_name"

  if [ "$method" = "GET" ]; then
    response=$(curl -s -w "\n%{http_code}" "$API_URL$endpoint" \
      -H "Authorization: Bearer $TOKEN" \
      -H "Accept: application/json")
  else
    response=$(curl -s -w "\n%{http_code}" -X "$method" "$API_URL$endpoint" \
      -H "Authorization: Bearer $TOKEN" \
      -H "Content-Type: application/json" \
      -H "Accept: application/json" \
      -d "$data")
  fi

  http_code=$(echo "$response" | tail -1)
  body=$(echo "$response" | sed '$d')

  if [ "$http_code" = "200" ] || [ "$http_code" = "201" ]; then
    echo "  ✅ PASSED (HTTP $http_code)"
    PASSED=$((PASSED + 1))
  else
    echo "  ❌ FAILED (HTTP $http_code)"
    echo "  Response: $body"
    FAILED=$((FAILED + 1))
  fi
  echo ""
}

# ==========================================
# Run 20 Tests
# ==========================================

# Test 1: Get Current User Profile
run_test 1 "Get Current User Profile" "/users/me"

# Test 2: Get Dashboard
run_test 2 "Get Dashboard" "/dashboard"

# Test 3: Get Leads List
run_test 3 "Get Leads List" "/leads/"

# Test 4: Get Tasks List
run_test 4 "Get Tasks List" "/tasks/"

# Test 5: Get Scorecard
run_test 5 "Get Scorecard" "/scorecard"

# Test 6: Get Conversations
run_test 6 "Get Conversations" "/conversations"

# Test 7: Get Notifications
run_test 7 "Get Notifications" "/notifications"

# Test 8: Get API Keys
run_test 8 "Get API Keys" "/api-keys"

# Test 9: Get Admin Users
run_test 9 "Get Admin Users" "/admin/users"

# Test 10: Get Onboarding Tasks
run_test 10 "Get Onboarding Tasks" "/onboarding/tasks"

# Test 11: Get AI Memory Stats
run_test 11 "Get AI Memory Stats" "/ai/memory-stats"

# Test 12: Get Voice Call Stats
run_test 12 "Get Voice Call Stats" "/voice/call-stats"

# Test 13: Get Voice Call History
run_test 13 "Get Voice Call History" "/voice/call-history"

# Test 14: Get AI Receptionist Config
run_test 14 "Get AI Receptionist Config" "/voice/ai-receptionist-config"

# Test 15: Get Voicemail Templates
run_test 15 "Get Voicemail Templates" "/voicemail/templates"

# Test 16: Get Voicemail History
run_test 16 "Get Voicemail History" "/voicemail/history"

# Test 17: Get Voicemail Analytics
run_test 17 "Get Voicemail Analytics" "/voicemail/analytics"

# Test 18: Get Reconciliation Pending
run_test 18 "Get Reconciliation Pending" "/reconciliation/pending"

# Test 19: Get Merge Duplicates
run_test 19 "Get Merge Duplicates" "/merge/duplicates"

# Test 20: Get Permission Requests
run_test 20 "Get Permission Requests" "/permission-requests"

# ==========================================
# Final Report
# ==========================================

echo "=========================================="
echo "📊 Test Results"
echo "=========================================="
echo "✅ Passed: $PASSED"
echo "❌ Failed: $FAILED"
echo "📈 Success Rate: $((PASSED * 100 / 20))%"
echo ""

if [ $PASSED -eq 20 ]; then
  echo "🎉 ALL 20 TESTS PASSED!"
  exit 0
else
  echo "⚠️  Some tests failed. Review output above."
  exit 1
fi
