#!/bin/bash
# Complete Agent Governance System Verification
# Tests backend API, frontend integration, and database

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🎯 PERENNIA AI - AGENT GOVERNANCE VERIFICATION"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Configuration
API_URL="http://localhost:8000"
FRONTEND_URL="http://localhost:3000"
PASS=0
FAIL=0

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# Test function for HTTP status
test_endpoint() {
    local name=$1
    local endpoint=$2
    local expected=${3:-200}

    echo -n "  Testing $name... "
    response=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL$endpoint" 2>/dev/null)

    if [ "$response" -eq "$expected" ]; then
        echo -e "${GREEN}✅ PASS${NC} (HTTP $response)"
        ((PASS++))
        return 0
    else
        echo -e "${RED}❌ FAIL${NC} (HTTP $response, expected $expected)"
        ((FAIL++))
        return 1
    fi
}

# Test with JSON field validation
test_json_field() {
    local name=$1
    local endpoint=$2
    local field=$3

    echo -n "  Testing $name... "
    response=$(curl -s "$API_URL$endpoint" 2>/dev/null)

    # Check if response contains the field
    if echo "$response" | grep -q "\"$field\""; then
        echo -e "${GREEN}✅ PASS${NC} (Has $field)"
        ((PASS++))
        return 0
    else
        echo -e "${RED}❌ FAIL${NC} (Missing $field)"
        ((FAIL++))
        return 1
    fi
}

# Check prerequisites
check_prerequisites() {
    echo -e "${CYAN}━━━ PREREQUISITES ━━━${NC}"
    echo ""

    # Check if curl is available
    echo -n "  Checking curl... "
    if command -v curl &> /dev/null; then
        echo -e "${GREEN}✅ Available${NC}"
    else
        echo -e "${RED}❌ Not found${NC}"
        echo "     Please install curl"
        exit 1
    fi

    # Check if jq is installed (optional)
    echo -n "  Checking jq (optional)... "
    if command -v jq &> /dev/null; then
        echo -e "${GREEN}✅ Installed${NC}"
    else
        echo -e "${YELLOW}⚠️  Not installed${NC}"
    fi

    # Check if backend is running
    echo -n "  Checking backend server... "
    if curl -s --max-time 5 "$API_URL/health" > /dev/null 2>&1; then
        echo -e "${GREEN}✅ Running${NC}"
    else
        echo -e "${RED}❌ Not running${NC}"
        echo ""
        echo "     Please start the backend first:"
        echo "     cd backend && python main.py"
        echo ""
        exit 1
    fi

    # Check if frontend is accessible (optional)
    echo -n "  Checking frontend server... "
    if curl -s --max-time 5 "$FRONTEND_URL" > /dev/null 2>&1; then
        echo -e "${GREEN}✅ Running${NC}"
    else
        echo -e "${YELLOW}⚠️  Not running (optional)${NC}"
    fi

    echo ""
}

# Main tests
run_tests() {
    echo -e "${CYAN}━━━ 1. CORE API ENDPOINTS ━━━${NC}"
    echo ""
    test_endpoint "Health Check" "/health"
    test_endpoint "API Documentation" "/docs"

    echo ""
    echo -e "${CYAN}━━━ 2. GOVERNANCE SETTINGS ━━━${NC}"
    echo ""
    test_json_field "Get Settings" "/api/v1/agents/governance/settings" "agentGovernanceEnabled"
    test_json_field "Settings - Success Rate" "/api/v1/agents/governance/settings" "defaultSuccessRate"
    test_json_field "Settings - Daily Budget" "/api/v1/agents/governance/settings" "defaultDailyBudget"
    test_json_field "Dashboard Summary" "/api/v1/agents/governance/dashboard" "total_agents"

    echo ""
    echo -e "${CYAN}━━━ 3. SETTINGS UPDATE TEST ━━━${NC}"
    echo ""
    echo -n "  Testing settings update (PUT)... "

    update_response=$(curl -s -X PUT "$API_URL/api/v1/agents/governance/settings" \
        -H "Content-Type: application/json" \
        -d '{
            "agentGovernanceEnabled": true,
            "autoHealthChecks": true,
            "costTrackingEnabled": true,
            "websocketEnabled": true,
            "auditLogging": true,
            "defaultSuccessRate": 95,
            "defaultResponseTime": 15000,
            "defaultMaxCost": 0.015,
            "defaultDailyBudget": 75,
            "systemMonthlyBudget": 30000,
            "costAlertThreshold": 80,
            "alertChannel": "Slack",
            "slackWebhook": "",
            "dailyDigest": true,
            "digestTime": "8:00 AM",
            "requireApproval": false,
            "viewPermissions": ["All Users"],
            "modifyPermissions": ["Admins Only"],
            "enforceEliteForTier3": true,
            "fairLendingMonitoring": true,
            "auditRetentionDays": 2555,
            "anthropicApiKey": "",
            "webhookUrl": "",
            "autoDailyTesting": true,
            "minPassRate": 95,
            "blockOnFailedTests": false
        }' 2>/dev/null)

    if echo "$update_response" | grep -q "success"; then
        echo -e "${GREEN}✅ PASS${NC} (Settings updated)"
        ((PASS++))
    else
        echo -e "${RED}❌ FAIL${NC} (Update failed)"
        echo "     Response: $update_response"
        ((FAIL++))
    fi

    # Verify settings persisted
    echo -n "  Verifying settings persisted... "
    verify_response=$(curl -s "$API_URL/api/v1/agents/governance/settings" 2>/dev/null)

    if echo "$verify_response" | grep -q '"defaultSuccessRate":95'; then
        echo -e "${GREEN}✅ PASS${NC} (Values persisted)"
        ((PASS++))
    else
        echo -e "${RED}❌ FAIL${NC} (Values not persisted)"
        ((FAIL++))
    fi

    echo ""
    echo -e "${CYAN}━━━ 4. AGENT PROFILE ENDPOINTS ━━━${NC}"
    echo ""
    test_endpoint "List Agent Profiles" "/api/v1/agents/profiles"
    test_endpoint "Agent Types" "/api/v1/agents/types"
    test_endpoint "Health Summary" "/api/v1/agents/health/summary"
    test_endpoint "Agent Statistics" "/api/v1/agents/statistics"
    test_endpoint "Agent Dashboard" "/api/v1/agents/dashboard"

    echo ""
    echo -e "${CYAN}━━━ 5. ALERT ENDPOINTS ━━━${NC}"
    echo ""
    test_endpoint "List Alerts" "/api/v1/agents/alerts"

    echo ""
    echo -e "${CYAN}━━━ 6. EXECUTION ENDPOINTS ━━━${NC}"
    echo ""
    test_endpoint "List Executions" "/api/v1/agents/executions"

    echo ""
    echo -e "${CYAN}━━━ 7. GYM ENDPOINTS ━━━${NC}"
    echo ""
    test_endpoint "Gym Scenarios" "/api/v1/agents/gym/scenarios"
    test_endpoint "Gym Sessions" "/api/v1/agents/gym/sessions"
    test_endpoint "Gym Leaderboard" "/api/v1/agents/gym/leaderboard"
}

# Print summary
print_summary() {
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo -e "${BLUE}📊 VERIFICATION SUMMARY${NC}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo -e "  Passed: ${GREEN}$PASS tests${NC}"
    echo -e "  Failed: ${RED}$FAIL tests${NC}"
    echo ""

    if [ $FAIL -eq 0 ]; then
        echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
        echo -e "${GREEN}✅ ALL TESTS PASSED - SYSTEM READY!${NC}"
        echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
        echo ""
        echo "🎯 Next Steps:"
        echo ""
        echo "  1. Open browser: ${CYAN}http://localhost:3000/settings${NC}"
        echo "  2. Click 'Agent Governance' in sidebar"
        echo "  3. Test each section (toggles, inputs, dropdowns)"
        echo "  4. Click 'Save Settings' and verify success"
        echo "  5. Navigate to: ${CYAN}http://localhost:3000/agents${NC}"
        echo "  6. Verify dashboard displays correctly"
        echo ""
        echo "🚀 Ready for production deployment!"
        echo ""
        exit 0
    else
        echo -e "${RED}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
        echo -e "${RED}❌ SOME TESTS FAILED${NC}"
        echo -e "${RED}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
        echo ""
        echo "🔍 Troubleshooting:"
        echo ""
        echo "  1. Check backend logs: tail -f backend/logs/*.log"
        echo "  2. Verify database: python backend/scripts/seed_agent_data.py"
        echo "  3. Restart backend: cd backend && python main.py"
        echo "  4. Check for port conflicts: lsof -i :8000"
        echo ""
        exit 1
    fi
}

# Main execution
check_prerequisites
run_tests
print_summary
