#!/bin/bash

# Perennia AI QA Test Suite v2
# Tests all critical API endpoints with correct paths

BASE_URL="https://app.perenniaai.com"
PASS=0
FAIL=0
SKIP=0

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_pass() {
    echo -e "${GREEN}✓ PASS${NC}: $1"
    ((PASS++))
}

log_fail() {
    echo -e "${RED}✗ FAIL${NC}: $1"
    ((FAIL++))
}

log_skip() {
    echo -e "${YELLOW}○ SKIP${NC}: $1"
    ((SKIP++))
}

test_endpoint() {
    local method=$1
    local endpoint=$2
    local description=$3
    local data=$4
    local expected_status=${5:-200}

    if [ "$method" == "GET" ]; then
        response=$(curl -sL -w "\n%{http_code}" -X GET "$BASE_URL$endpoint" \
            -H "Authorization: Bearer $TOKEN" \
            -H "Content-Type: application/json" \
            --max-time 30 2>/dev/null)
    else
        response=$(curl -sL -w "\n%{http_code}" -X POST "$BASE_URL$endpoint" \
            -H "Authorization: Bearer $TOKEN" \
            -H "Content-Type: application/json" \
            -d "$data" \
            --max-time 30 2>/dev/null)
    fi

    status_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | sed '$d')

    if [ "$status_code" == "$expected_status" ] || [ "$status_code" == "200" ] || [ "$status_code" == "201" ]; then
        log_pass "$description (HTTP $status_code)"
        return 0
    else
        log_fail "$description (HTTP $status_code, expected $expected_status)"
        echo "  Response: ${body:0:200}"
        return 1
    fi
}

echo "========================================"
echo "  PIPELINE 360 QA TEST SUITE v2"
echo "  $(date)"
echo "========================================"
echo ""

# ========================================
# PRIORITY 1: AUTHENTICATION
# ========================================
echo "========================================"
echo "PRIORITY 1: AUTHENTICATION & CORE ACCESS"
echo "========================================"

# Get auth token
echo "Testing login..."
AUTH_RESPONSE=$(curl -sL -X POST "$BASE_URL/token" \
    -H "Content-Type: application/x-www-form-urlencoded" \
    -d "username=admin@perenniaai.com&password=demo123")

TOKEN=$(echo "$AUTH_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null)

if [ -n "$TOKEN" ] && [ "$TOKEN" != "" ]; then
    log_pass "User login (admin@perenniaai.com)"
    echo "  Token obtained: ${TOKEN:0:50}..."
else
    log_fail "User login - no token received"
    echo "  Response: $AUTH_RESPONSE"
    exit 1
fi

# Test token validity (with trailing slash)
test_endpoint "GET" "/api/v1/loans/?limit=1" "Token authentication valid"

echo ""

# ========================================
# PRIORITY 1: LEAD MANAGEMENT
# ========================================
echo "========================================"
echo "PRIORITY 1: LEAD MANAGEMENT"
echo "========================================"

test_endpoint "GET" "/api/v1/leads/?limit=5" "List leads"
test_endpoint "GET" "/api/v1/leads/?status=new&limit=5" "Filter leads by status"

# Create a test lead
TIMESTAMP=$(date +%s)
LEAD_DATA="{
    \"name\": \"QA TestLead\",
    \"email\": \"qa.test.${TIMESTAMP}@example.com\",
    \"phone\": \"+15551234567\",
    \"source\": \"Website\"
}"
echo "Creating test lead..."
CREATE_RESPONSE=$(curl -sL -X POST "$BASE_URL/api/v1/leads/" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d "$LEAD_DATA" --max-time 30)

LEAD_ID=$(echo "$CREATE_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('id',''))" 2>/dev/null)

if [ -n "$LEAD_ID" ] && [ "$LEAD_ID" != "" ]; then
    log_pass "Create lead (ID: $LEAD_ID)"
    # Test lead detail
    test_endpoint "GET" "/api/v1/leads/$LEAD_ID" "Get lead detail"
else
    log_fail "Create lead"
    echo "  Response: ${CREATE_RESPONSE:0:200}"
fi

echo ""

# ========================================
# PRIORITY 1: LOAN MANAGEMENT
# ========================================
echo "========================================"
echo "PRIORITY 1: LOAN MANAGEMENT"
echo "========================================"

test_endpoint "GET" "/api/v1/loans/?limit=5" "List loans"
test_endpoint "GET" "/api/v1/loans/?status=processing&limit=5" "Filter loans by status"

# Get a loan ID for detail test
LOANS_RESPONSE=$(curl -sL "$BASE_URL/api/v1/loans/?limit=1" \
    -H "Authorization: Bearer $TOKEN" --max-time 30)
LOAN_ID=$(echo "$LOANS_RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d[0]['id'] if isinstance(d,list) and len(d)>0 else d.get('loans',[{}])[0].get('id',''))" 2>/dev/null)

if [ -n "$LOAN_ID" ] && [ "$LOAN_ID" != "" ]; then
    test_endpoint "GET" "/api/v1/loans/$LOAN_ID" "Get loan detail"
fi

echo ""

# ========================================
# PRIORITY 1: MUM CLIENTS
# ========================================
echo "========================================"
echo "PRIORITY 1: MUM CLIENT MANAGEMENT"
echo "========================================"

test_endpoint "GET" "/api/v1/mum/clients?limit=5" "List MUM clients"

echo ""

# ========================================
# PRIORITY 2: EMAIL INTEGRATION
# ========================================
echo "========================================"
echo "PRIORITY 2: EMAIL INTEGRATION"
echo "========================================"

test_endpoint "GET" "/api/v1/gmail/status" "Gmail sync status"
test_endpoint "GET" "/api/v1/email-monitor/stats" "Email monitor stats"
test_endpoint "GET" "/api/v1/email-monitor/captured" "Captured emails"
test_endpoint "GET" "/api/v1/email-monitor/whitelist" "Email whitelist"

# Email Drop parsing test - correct format
EMAIL_PARSE_DATA='{
    "email_data": {
        "filename": "test_email.eml",
        "from": "leads@realtor.com",
        "to": "lo@company.com",
        "subject": "New Lead: John Doe - Purchase $500,000",
        "date": "2025-01-15T10:30:00Z",
        "body": "Name: John Doe\nEmail: john@test.com\nPhone: 555-123-4567\nLoan Amount: $500,000\nProperty: 123 Main St"
    }
}'
test_endpoint "POST" "/api/v1/email-drop/parse" "Email drop parse" "$EMAIL_PARSE_DATA"

echo ""

# ========================================
# PRIORITY 2: VOICE & TELEPHONY
# ========================================
echo "========================================"
echo "PRIORITY 2: VOICE & TELEPHONY"
echo "========================================"

test_endpoint "GET" "/api/v1/dialer/settings" "Dialer settings"
test_endpoint "GET" "/api/v1/dialer/verified-caller-ids" "Verified caller IDs"
test_endpoint "GET" "/api/v1/dialer/call-logs" "Call logs"
test_endpoint "GET" "/api/v1/voice/ai-receptionist-config" "AI receptionist config"
test_endpoint "GET" "/api/v1/voice/call-stats" "Call stats"
test_endpoint "GET" "/api/v1/voice/call-history" "Call history"
test_endpoint "GET" "/api/v1/voicemail/templates" "Voicemail templates"
test_endpoint "GET" "/api/v1/voicemail/history" "Voicemail history"
test_endpoint "GET" "/api/v1/dialer/compliance/check?phone_number=%2B15551234567" "Compliance check"

echo ""

# ========================================
# PRIORITY 3: TASK MANAGEMENT
# ========================================
echo "========================================"
echo "PRIORITY 3: TASK MANAGEMENT"
echo "========================================"

test_endpoint "GET" "/api/v1/tasks/" "List tasks"
test_endpoint "GET" "/api/v1/unified-tasks" "Unified tasks view"

echo ""

# ========================================
# PRIORITY 3: WORKFLOW AUTOMATION
# ========================================
echo "========================================"
echo "PRIORITY 3: WORKFLOW AUTOMATION"
echo "========================================"

test_endpoint "GET" "/api/v1/ai/workflows" "List workflows"
test_endpoint "GET" "/api/v1/ai/workflow-templates" "Workflow templates"
test_endpoint "GET" "/api/v1/ai/scheduler/status" "Scheduler status"
test_endpoint "GET" "/api/v1/workflow-config/workflows" "Workflow configs"

echo ""

# ========================================
# PRIORITY 4: AI SYSTEMS
# ========================================
echo "========================================"
echo "PRIORITY 4: AI SYSTEMS"
echo "========================================"

test_endpoint "GET" "/api/v1/ai/memory-stats" "AI memory stats"
test_endpoint "GET" "/api/v1/ai/knowledge-base" "Knowledge base"
test_endpoint "GET" "/api/v1/ai/audit-logs" "AI audit logs"
test_endpoint "GET" "/api/v1/ai/compliance/rules" "Compliance rules"

# Test AI chat
AI_CHAT_DATA='{"message": "What are my top priorities today?"}'
echo "Testing AI orchestrator chat (may take 30+ seconds)..."
test_endpoint "POST" "/api/v1/ai/orchestrator-chat" "AI orchestrator chat" "$AI_CHAT_DATA"

# Test AI context generation
if [ -n "$LEAD_ID" ] && [ "$LEAD_ID" != "" ]; then
    test_endpoint "GET" "/api/v1/ai/context/lead/$LEAD_ID" "AI lead context"
fi

if [ -n "$LOAN_ID" ] && [ "$LOAN_ID" != "" ]; then
    test_endpoint "GET" "/api/v1/ai/context/loan/$LOAN_ID" "AI loan context"
fi

echo ""

# ========================================
# PRIORITY 5: DATA RECONCILIATION
# ========================================
echo "========================================"
echo "PRIORITY 5: DATA RECONCILIATION"
echo "========================================"

test_endpoint "GET" "/api/v1/reconciliation/pending" "Pending reconciliation items"
test_endpoint "GET" "/api/v1/reconciliation/completed" "Completed reconciliation"
test_endpoint "GET" "/api/v1/reconciliation/blocked-senders" "Blocked senders"
test_endpoint "GET" "/api/v1/merge/duplicates" "Duplicate detection"
test_endpoint "GET" "/api/v1/merge/completed" "Merge history"

echo ""

# ========================================
# PRIORITY 6: FINANCIAL SYSTEMS
# ========================================
echo "========================================"
echo "PRIORITY 6: FINANCIAL SYSTEMS"
echo "========================================"

test_endpoint "GET" "/api/v1/profitability/dashboard" "Profitability dashboard"
test_endpoint "GET" "/api/v1/financial-intelligence/executive-dashboard" "Executive dashboard"
test_endpoint "GET" "/api/v1/financial-intelligence/gain-on-sale" "Gain on sale"
test_endpoint "GET" "/api/v1/financial-intelligence/cost-per-loan" "Cost per loan"
test_endpoint "GET" "/api/v1/financial-intelligence/cash-runway" "Cash runway"
test_endpoint "GET" "/api/v1/analytics/pipeline" "Pipeline analytics"
# Employee performance requires employee ID, test roles instead
test_endpoint "GET" "/api/v1/profitability/roles" "Profitability roles"

echo ""

# ========================================
# PRIORITY 7: USER MANAGEMENT (Admin paths - skip in automated tests)
# ========================================
echo "========================================"
echo "PRIORITY 7: USER MANAGEMENT"
echo "========================================"

# Admin endpoints are IP-restricted for security
log_skip "User roles (admin endpoint - IP restricted)"
log_skip "User categories (admin endpoint - IP restricted)"
log_skip "User responsibilities (admin endpoint - IP restricted)"
log_skip "Permission templates (admin endpoint - IP restricted)"
test_endpoint "GET" "/api/v1/onboarding/roles" "Onboarding roles"

echo ""

# ========================================
# PRIORITY 8: MICROSOFT INTEGRATION
# ========================================
echo "========================================"
echo "PRIORITY 8: MICROSOFT INTEGRATION"
echo "========================================"

test_endpoint "GET" "/api/v1/microsoft/status" "Microsoft sync status"
test_endpoint "GET" "/api/v1/microsoft/sync-diagnostics" "Microsoft sync diagnostics"

echo ""

# ========================================
# PRIORITY 9: ADDITIONAL ENDPOINTS
# ========================================
echo "========================================"
echo "PRIORITY 9: ADDITIONAL SYSTEMS"
echo "========================================"

# /api/v1/contacts doesn't exist yet - skip
log_skip "Contacts list (endpoint not implemented)"
test_endpoint "GET" "/api/v1/activities/" "Activities list"
test_endpoint "GET" "/api/v1/referral-partners/" "Referral partners"
test_endpoint "GET" "/api/v1/team/members" "Team members"
test_endpoint "GET" "/api/v1/system/diagnostics" "System diagnostics"

echo ""

# ========================================
# SCHEDULER & VIDEO
# ========================================
echo "========================================"
echo "SCHEDULER & VIDEO MEETINGS"
echo "========================================"

test_endpoint "GET" "/api/v1/scheduler/config" "Scheduler config"
test_endpoint "GET" "/api/v1/scheduler/appointment-types" "Appointment types"
test_endpoint "GET" "/api/v1/scheduler/appointments" "Appointments list"
test_endpoint "GET" "/api/v1/meetings/rooms" "Video meeting rooms"

echo ""

# ========================================
# SUMMARY
# ========================================
echo "========================================"
echo "TEST SUMMARY"
echo "========================================"
TOTAL=$((PASS + FAIL + SKIP))
echo -e "${GREEN}PASSED${NC}: $PASS"
echo -e "${RED}FAILED${NC}: $FAIL"
echo -e "${YELLOW}SKIPPED${NC}: $SKIP"
echo "TOTAL: $TOTAL"
echo ""
if [ $FAIL -eq 0 ]; then
    echo -e "${GREEN}All tests passed!${NC}"
else
    echo -e "${RED}Some tests failed. Review output above.${NC}"
fi
echo "========================================"
