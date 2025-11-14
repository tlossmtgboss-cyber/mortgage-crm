#!/bin/bash
###############################################################################
# AI System Comprehensive Test Suite - 20 Tests
# Must pass all 20 tests consecutively to classify as functioning
###############################################################################

BASE_URL="https://mortgage-crm-production-7a9a.up.railway.app"
TEST_COUNT=0
FAILED_TESTS=()

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_test() {
    local test_num=$1
    local test_name="$2"
    echo -e "${BLUE}[TEST #$test_num]${NC} $test_name"
}

log_pass() {
    local test_num=$1
    local test_name="$2"
    echo -e "${GREEN}✅ PASS${NC} - Test #$test_num: $test_name"
    echo ""
}

log_fail() {
    local test_num=$1
    local test_name="$2"
    local error="$3"
    echo -e "${RED}❌ FAIL${NC} - Test #$test_num: $test_name"
    echo -e "${RED}   Error: $error${NC}"
    echo ""
}

run_test() {
    local test_num=$1
    local test_name="$2"
    local test_func=$3

    log_test "$test_num" "$test_name"

    if $test_func; then
        log_pass "$test_num" "$test_name"
        TEST_COUNT=$((TEST_COUNT + 1))
        return 0
    else
        log_fail "$test_num" "$test_name" "Test function returned false"
        FAILED_TESTS+=("$test_num: $test_name")
        return 1
    fi
}

# Test 1: Health Check
test_health_check() {
    local code=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/health")

    if [ "$code" != "200" ]; then
        echo "HTTP status: $code" >&2
        return 1
    fi

    local body=$(curl -s "$BASE_URL/health")

    if ! echo "$body" | grep -q "healthy"; then
        echo "Response missing 'healthy' status: $body" >&2
        return 1
    fi

    return 0
}

# Test 2: List All Agents
test_list_agents() {
    local code=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/api/ai/agents")

    if [ "$code" != "200" ]; then
        echo "HTTP status: $code" >&2
        return 1
    fi

    local body=$(curl -s "$BASE_URL/api/ai/agents")
    local count=$(echo "$body" | grep -o '"count":[0-9]*' | grep -o '[0-9]*')

    if [ "$count" != "7" ]; then
        echo "Expected 7 agents, got $count" >&2
        return 1
    fi

    return 0
}

# Test 3: List All Tools
test_list_tools() {
    local code=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/api/ai/tools")

    if [ "$code" != "200" ]; then
        echo "HTTP status: $code" >&2
        return 1
    fi

    local body=$(curl -s "$BASE_URL/api/ai/tools")

    if ! echo "$body" | grep -q "tools"; then
        echo "Response missing 'tools' field" >&2
        return 1
    fi

    return 0
}

# Test 4: Verify Lead Manager Agent
test_lead_manager() {
    local response=$(curl -s "$BASE_URL/api/ai/agents")

    if ! echo "$response" | grep -q "lead_manager"; then
        echo "Lead Manager agent not found" >&2
        return 1
    fi

    if ! echo "$response" | grep -q "Lead Management Agent"; then
        echo "Lead Manager name not correct" >&2
        return 1
    fi

    return 0
}

# Test 5: Verify Pipeline Manager Agent
test_pipeline_manager() {
    local response=$(curl -s "$BASE_URL/api/ai/agents")

    if ! echo "$response" | grep -q "pipeline_manager"; then
        echo "Pipeline Manager agent not found" >&2
        return 1
    fi

    return 0
}

# Test 6: Verify Customer Engagement Agent
test_customer_engagement() {
    local response=$(curl -s "$BASE_URL/api/ai/agents")

    if ! echo "$response" | grep -q "customer_engagement"; then
        echo "Customer Engagement agent not found" >&2
        return 1
    fi

    return 0
}

# Test 7: Dispatch LeadCreated Event
test_dispatch_lead_created() {
    local payload='{"event_type":"LeadCreated","payload":{"entity_type":"lead","entity_id":"test_001","first_name":"John","last_name":"Doe"}}'

    local code=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/api/ai/events" \
        -H "Content-Type: application/json" \
        -d "$payload")

    if [ "$code" != "200" ]; then
        echo "HTTP status: $code" >&2
        return 1
    fi

    local body=$(curl -s -X POST "$BASE_URL/api/ai/events" \
        -H "Content-Type: application/json" \
        -d "$payload")

    if ! echo "$body" | grep -q "event_id"; then
        echo "Response missing event_id" >&2
        return 1
    fi

    return 0
}

# Test 8: Dispatch LoanStageChanged Event
test_dispatch_loan_stage() {
    local payload='{"event_type":"LoanStageChanged","payload":{"entity_type":"loan","entity_id":"test_loan_001","old_stage":"application","new_stage":"processing"}}'

    local code=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/api/ai/events" \
        -H "Content-Type: application/json" \
        -d "$payload")

    if [ "$code" != "200" ]; then
        echo "HTTP status: $code" >&2
        return 1
    fi

    return 0
}

# Test 9: List Executions
test_list_executions() {
    local code=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/api/ai/executions")

    if [ "$code" != "200" ]; then
        echo "HTTP status: $code" >&2
        return 1
    fi

    local body=$(curl -s "$BASE_URL/api/ai/executions")

    if ! echo "$body" | grep -q "executions"; then
        echo "Response missing 'executions' field" >&2
        return 1
    fi

    return 0
}

# Test 10: Get Statistics
test_statistics() {
    local code=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/api/ai/statistics")

    if [ "$code" != "200" ]; then
        echo "HTTP status: $code" >&2
        return 1
    fi

    return 0
}

# Test 11: Filter Active Agents
test_filter_active_agents() {
    local code=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/api/ai/agents?status=active")

    if [ "$code" != "200" ]; then
        echo "HTTP status: $code" >&2
        return 1
    fi

    local body=$(curl -s "$BASE_URL/api/ai/agents?status=active")
    local count=$(echo "$body" | grep -o '"count":[0-9]*' | grep -o '[0-9]*')

    if [ "$count" != "7" ]; then
        echo "Expected 7 active agents, got $count" >&2
        return 1
    fi

    return 0
}

# Test 12: Verify Agent Has Tools
test_agent_tools() {
    local response=$(curl -s "$BASE_URL/api/ai/agents")

    if ! echo "$response" | grep -q '"tools":\['; then
        echo "Agents missing tools configuration" >&2
        return 1
    fi

    return 0
}

# Test 13: Verify Agent Has Triggers
test_agent_triggers() {
    local response=$(curl -s "$BASE_URL/api/ai/agents")

    if ! echo "$response" | grep -q "LeadCreated"; then
        echo "Agents missing trigger configuration" >&2
        return 1
    fi

    return 0
}

# Test 14: Dispatch DocUploaded Event
test_dispatch_doc_uploaded() {
    local payload='{"event_type":"DocUploaded","payload":{"entity_type":"document","entity_id":"doc_001","loan_id":"loan_123"}}'

    local code=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/api/ai/events" \
        -H "Content-Type: application/json" \
        -d "$payload")

    if [ "$code" != "200" ]; then
        echo "HTTP status: $code" >&2
        return 1
    fi

    return 0
}

# Test 15: Verify Portfolio Analyst
test_portfolio_analyst() {
    local response=$(curl -s "$BASE_URL/api/ai/agents")

    if ! echo "$response" | grep -q "portfolio_analyst"; then
        echo "Portfolio Analyst not found" >&2
        return 1
    fi

    if ! echo "$response" | grep -q "scanForRefiOpportunities"; then
        echo "Portfolio Analyst missing refi tool" >&2
        return 1
    fi

    return 0
}

# Test 16: Verify Operations Agent
test_operations_agent() {
    local response=$(curl -s "$BASE_URL/api/ai/agents")

    if ! echo "$response" | grep -q "operations_agent"; then
        echo "Operations Agent not found" >&2
        return 1
    fi

    return 0
}

# Test 17: Verify Forecasting Agent
test_forecasting_agent() {
    local response=$(curl -s "$BASE_URL/api/ai/agents")

    if ! echo "$response" | grep -q "forecasting_planner"; then
        echo "Forecasting Agent not found" >&2
        return 1
    fi

    return 0
}

# Test 18: Verify Underwriting Agent
test_underwriting_agent() {
    local response=$(curl -s "$BASE_URL/api/ai/agents")

    if ! echo "$response" | grep -q "underwriting_assistant"; then
        echo "Underwriting Agent not found" >&2
        return 1
    fi

    return 0
}

# Test 19: Verify Tool Names
test_tool_names() {
    local response=$(curl -s "$BASE_URL/api/ai/tools")

    if ! echo "$response" | grep -q "getLeadById"; then
        echo "getLeadById tool not found" >&2
        return 1
    fi

    return 0
}

# Test 20: Final Integration Test
test_final_integration() {
    local payload1='{"event_type":"LeadCreated","payload":{"entity_type":"lead","entity_id":"final_001"}}'
    local payload2='{"event_type":"LoanStageChanged","payload":{"entity_type":"loan","entity_id":"final_002"}}'

    local code1=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/api/ai/events" \
        -H "Content-Type: application/json" \
        -d "$payload1")

    if [ "$code1" != "200" ]; then
        echo "First event failed with HTTP $code1" >&2
        return 1
    fi

    local code2=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/api/ai/events" \
        -H "Content-Type: application/json" \
        -d "$payload2")

    if [ "$code2" != "200" ]; then
        echo "Second event failed with HTTP $code2" >&2
        return 1
    fi

    return 0
}

###############################################################################
# Main Test Runner
###############################################################################

main() {
    echo "================================================================================"
    echo "🤖 AI SYSTEM COMPREHENSIVE TEST SUITE - 20 CONSECUTIVE TESTS"
    echo "================================================================================"
    echo ""

    START_TIME=$(date +%s)

    # Run all 20 tests
    run_test 1 "Health Check" test_health_check || exit 1
    run_test 2 "List All Agents" test_list_agents || exit 1
    run_test 3 "List All Tools" test_list_tools || exit 1
    run_test 4 "Verify Lead Manager Agent" test_lead_manager || exit 1
    run_test 5 "Verify Pipeline Manager Agent" test_pipeline_manager || exit 1
    run_test 6 "Verify Customer Engagement Agent" test_customer_engagement || exit 1
    run_test 7 "Dispatch LeadCreated Event" test_dispatch_lead_created || exit 1
    run_test 8 "Dispatch LoanStageChanged Event" test_dispatch_loan_stage || exit 1
    run_test 9 "List Agent Executions" test_list_executions || exit 1
    run_test 10 "Get Agent Statistics" test_statistics || exit 1
    run_test 11 "Filter Active Agents" test_filter_active_agents || exit 1
    run_test 12 "Verify Agent Tools Config" test_agent_tools || exit 1
    run_test 13 "Verify Agent Triggers Config" test_agent_triggers || exit 1
    run_test 14 "Dispatch DocUploaded Event" test_dispatch_doc_uploaded || exit 1
    run_test 15 "Verify Portfolio Analyst Agent" test_portfolio_analyst || exit 1
    run_test 16 "Verify Operations Agent" test_operations_agent || exit 1
    run_test 17 "Verify Forecasting Agent" test_forecasting_agent || exit 1
    run_test 18 "Verify Underwriting Agent" test_underwriting_agent || exit 1
    run_test 19 "Verify Tool Names" test_tool_names || exit 1
    run_test 20 "Final Integration Test" test_final_integration || exit 1

    END_TIME=$(date +%s)
    DURATION=$((END_TIME - START_TIME))

    echo ""
    echo "================================================================================"
    echo "🎉 TEST SUITE COMPLETED SUCCESSFULLY!"
    echo "================================================================================"
    echo -e "${GREEN}✅ Passed: $TEST_COUNT/20 tests${NC}"
    echo "⏱️  Duration: ${DURATION}s"
    echo "📊 Success Rate: 100%"
    echo ""
    echo "All 20 tests passed consecutively. AI system is FULLY FUNCTIONAL!"
    echo ""

    exit 0
}

main
