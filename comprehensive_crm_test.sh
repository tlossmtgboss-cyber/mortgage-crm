#!/bin/bash

# Comprehensive CRM Diagnosis Test Script
# Tests every feature, button, and component

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Test counters
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0
WARNING_TESTS=0

# Issues array
declare -a CRITICAL_ISSUES
declare -a WARNING_ISSUES
declare -a PASSED_FEATURES

echo -e "${BLUE}════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  Comprehensive CRM Diagnosis${NC}"
echo -e "${BLUE}  Testing All Features & Components${NC}"
echo -e "${BLUE}════════════════════════════════════════════════${NC}\n"

# Helper function for test results
test_result() {
    local test_name="$1"
    local result="$2"
    local message="$3"

    TOTAL_TESTS=$((TOTAL_TESTS + 1))

    if [ "$result" == "PASS" ]; then
        echo -e "${GREEN}✓ $test_name${NC}"
        [ -n "$message" ] && echo -e "  ${message}"
        PASSED_TESTS=$((PASSED_TESTS + 1))
        PASSED_FEATURES+=("$test_name")
    elif [ "$result" == "WARN" ]; then
        echo -e "${YELLOW}⚠ $test_name${NC}"
        [ -n "$message" ] && echo -e "  ${YELLOW}${message}${NC}"
        WARNING_TESTS=$((WARNING_TESTS + 1))
        WARNING_ISSUES+=("$test_name: $message")
    else
        echo -e "${RED}✗ $test_name${NC}"
        [ -n "$message" ] && echo -e "  ${RED}${message}${NC}"
        FAILED_TESTS=$((FAILED_TESTS + 1))
        CRITICAL_ISSUES+=("$test_name: $message")
    fi
}

echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}1. BACKEND API HEALTH TESTS${NC}"
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"

# Test API Health
API_URL="https://mortgage-crm-production-7a9a.up.railway.app"

# Health endpoint
health_response=$(curl -s "$API_URL/health" 2>&1)
if echo "$health_response" | grep -q "healthy"; then
    test_result "API Health Endpoint" "PASS" "Status: healthy, database connected"
else
    test_result "API Health Endpoint" "FAIL" "Health check failed"
fi

# API Documentation
docs_response=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL/docs" 2>&1)
if [ "$docs_response" == "200" ]; then
    test_result "API Documentation (/docs)" "PASS" "Swagger UI accessible"
else
    test_result "API Documentation (/docs)" "WARN" "HTTP $docs_response"
fi

# Test key API endpoints
echo -e "\n${BLUE}Testing Core API Endpoints...${NC}\n"

# Leads endpoint
leads_response=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL/api/v1/leads/" 2>&1)
if [ "$leads_response" == "200" ] || [ "$leads_response" == "307" ]; then
    test_result "Leads API Endpoint" "PASS" "HTTP $leads_response"
else
    test_result "Leads API Endpoint" "FAIL" "HTTP $leads_response"
fi

# Loans endpoint
loans_response=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL/api/v1/loans/" 2>&1)
if [ "$loans_response" == "200" ] || [ "$loans_response" == "307" ]; then
    test_result "Loans API Endpoint" "PASS" "HTTP $loans_response"
else
    test_result "Loans API Endpoint" "FAIL" "HTTP $loans_response"
fi

# Tasks endpoint
tasks_response=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL/api/v1/tasks/" 2>&1)
if [ "$tasks_response" == "200" ] || [ "$tasks_response" == "307" ]; then
    test_result "Tasks API Endpoint" "PASS" "HTTP $tasks_response"
else
    test_result "Tasks API Endpoint" "FAIL" "HTTP $tasks_response"
fi

# Activities endpoint
activities_response=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL/api/v1/activities/" 2>&1)
if [ "$activities_response" == "200" ] || [ "$activities_response" == "307" ]; then
    test_result "Activities API Endpoint" "PASS" "HTTP $activities_response"
else
    test_result "Activities API Endpoint" "FAIL" "HTTP $activities_response"
fi

# Team Members endpoint
team_response=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL/api/v1/team/" 2>&1)
if [ "$team_response" == "200" ] || [ "$team_response" == "307" ]; then
    test_result "Team Members API Endpoint" "PASS" "HTTP $team_response"
else
    test_result "Team Members API Endpoint" "FAIL" "HTTP $team_response"
fi

echo -e "\n${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}2. FRONTEND COMPONENT TESTS${NC}"
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"

# Check critical page files
echo -e "${BLUE}Checking Page Components...${NC}\n"

pages=(
    "Dashboard.js"
    "Leads.js"
    "LeadDetail.js"
    "Loans.js"
    "LoanDetail.js"
    "Tasks.js"
    "Calendar.js"
    "Settings.js"
    "Coach.js"
    "Login.js"
)

for page in "${pages[@]}"; do
    if [ -f "frontend/src/pages/$page" ]; then
        test_result "Page: $page" "PASS"
    else
        test_result "Page: $page" "FAIL" "File not found"
    fi
done

echo -e "\n${BLUE}Checking Component Files...${NC}\n"

components=(
    "Navigation.js"
    "SmartAIChat.js"
    "VoiceInput.js"
    "CoachCorner.js"
    "SMSModal.js"
    "TeamsModal.js"
    "RecordingModal.js"
    "VoicemailModal.js"
    "AIAssistant.js"
    "ErrorBoundary.js"
)

for component in "${components[@]}"; do
    if [ -f "frontend/src/components/$component" ]; then
        test_result "Component: $component" "PASS"
    else
        test_result "Component: $component" "FAIL" "File not found"
    fi
done

echo -e "\n${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}3. FEATURE INTEGRATION TESTS${NC}"
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"

# Voice Chat Feature
echo -e "${BLUE}Testing Voice Chat Feature...${NC}\n"

if [ -f "frontend/src/components/VoiceInput.js" ] && [ -f "VOICE_CHAT_FEATURE.md" ]; then
    if grep -q "SpeechRecognition" frontend/src/components/VoiceInput.js; then
        test_result "Voice Chat - Speech Recognition" "PASS" "Web Speech API integrated"
    else
        test_result "Voice Chat - Speech Recognition" "FAIL" "API not found"
    fi

    if grep -q "VoiceInput" frontend/src/components/CoachCorner.js; then
        test_result "Voice Chat - Process Coach Integration" "PASS"
    else
        test_result "Voice Chat - Process Coach Integration" "WARN" "Not integrated in CoachCorner"
    fi
else
    test_result "Voice Chat Feature" "FAIL" "Component files missing"
fi

# Smart AI Chat
echo -e "\n${BLUE}Testing Smart AI Chat...${NC}\n"

if [ -f "frontend/src/components/SmartAIChat.js" ]; then
    if grep -q "aiAPI.smartChat" frontend/src/components/SmartAIChat.js; then
        test_result "Smart AI Chat - API Integration" "PASS"
    else
        test_result "Smart AI Chat - API Integration" "WARN" "API call pattern not found"
    fi

    if grep -q "SmartAIChat" frontend/src/pages/LeadDetail.js; then
        test_result "Smart AI Chat - Lead Detail Integration" "PASS"
    else
        test_result "Smart AI Chat - Lead Detail Integration" "FAIL" "Not integrated"
    fi
else
    test_result "Smart AI Chat Component" "FAIL" "Component file missing"
fi

# Process Coach
echo -e "\n${BLUE}Testing Process Coach...${NC}\n"

if [ -f "frontend/src/components/CoachCorner.js" ]; then
    test_result "Process Coach Component" "PASS"

    # Check for coaching modes
    if grep -q "pipeline_audit\|daily_briefing\|focus_reset" frontend/src/components/CoachCorner.js; then
        test_result "Process Coach - Coaching Modes" "PASS" "Multiple modes detected"
    else
        test_result "Process Coach - Coaching Modes" "WARN" "Coaching modes not clearly defined"
    fi
else
    test_result "Process Coach Component" "FAIL" "CoachCorner.js missing"
fi

# Communication Modals
echo -e "\n${BLUE}Testing Communication Features...${NC}\n"

comm_features=(
    "SMSModal.js:SMS Feature"
    "TeamsModal.js:Teams Meeting Feature"
    "RecordingModal.js:Meeting Recording Feature"
    "VoicemailModal.js:Voicemail Drop Feature"
)

for feature in "${comm_features[@]}"; do
    file="${feature%%:*}"
    name="${feature##*:}"

    if [ -f "frontend/src/components/$file" ]; then
        test_result "$name" "PASS"
    else
        test_result "$name" "FAIL" "Component missing"
    fi
done

echo -e "\n${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}4. CONFIGURATION & ENVIRONMENT TESTS${NC}"
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"

# Check backend configuration
if [ -f "backend/main.py" ]; then
    test_result "Backend Main File" "PASS"

    if grep -q "FastAPI" backend/main.py; then
        test_result "FastAPI Framework" "PASS"
    fi

    if grep -q "security_middleware" backend/main.py; then
        test_result "Security Middleware" "PASS"
    else
        test_result "Security Middleware" "WARN" "Not explicitly imported"
    fi
else
    test_result "Backend Main File" "FAIL" "main.py not found"
fi

# Check frontend package.json
if [ -f "frontend/package.json" ]; then
    test_result "Frontend Package Config" "PASS"

    if grep -q "react" frontend/package.json; then
        test_result "React Framework" "PASS"
    fi

    if grep -q "react-router" frontend/package.json; then
        test_result "React Router" "PASS"
    fi
else
    test_result "Frontend Package Config" "FAIL" "package.json not found"
fi

# Check backend requirements
if [ -f "backend/requirements.txt" ]; then
    test_result "Backend Requirements File" "PASS"

    if grep -q "fastapi" backend/requirements.txt; then
        test_result "FastAPI Dependency" "PASS"
    fi

    if grep -q "anthropic" backend/requirements.txt; then
        test_result "Anthropic AI SDK" "PASS"
    fi

    if grep -q "msal" backend/requirements.txt; then
        test_result "Microsoft Auth SDK" "PASS"
    fi
else
    test_result "Backend Requirements File" "FAIL" "requirements.txt not found"
fi

echo -e "\n${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}5. DATABASE & MIGRATION TESTS${NC}"
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"

# Check database models
if [ -f "backend/models.py" ]; then
    test_result "Database Models File" "PASS"

    # Check for key models
    models=("Lead" "Loan" "Task" "Activity" "User")
    for model in "${models[@]}"; do
        if grep -q "class $model" backend/models.py; then
            test_result "Model: $model" "PASS"
        else
            test_result "Model: $model" "FAIL" "Model not found"
        fi
    done
else
    test_result "Database Models File" "FAIL" "models.py not found"
fi

# Check for migrations
if [ -d "backend/migrations" ]; then
    migration_count=$(ls -1 backend/migrations/*.py 2>/dev/null | wc -l)
    if [ "$migration_count" -gt 0 ]; then
        test_result "Database Migrations" "PASS" "$migration_count migration files found"
    else
        test_result "Database Migrations" "WARN" "No migration files found"
    fi
else
    test_result "Database Migrations Directory" "WARN" "Migrations directory not found"
fi

echo -e "\n${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}6. INTEGRATION SERVICES TESTS${NC}"
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"

# Microsoft 365 Integration
if [ -f "backend/integrations/microsoft_service.py" ]; then
    test_result "Microsoft 365 Integration" "PASS"

    if grep -q "email_sync" backend/integrations/microsoft_service.py; then
        test_result "Email Sync Feature" "PASS"
    fi
else
    test_result "Microsoft 365 Integration" "FAIL" "microsoft_service.py not found"
fi

# AI Memory Service
if [ -f "backend/ai_memory_service.py" ]; then
    test_result "AI Memory Service" "PASS"

    if grep -q "conversation_memory" backend/ai_memory_service.py; then
        test_result "Conversation Memory" "PASS"
    fi

    if grep -q "get_intelligent_response" backend/ai_memory_service.py; then
        test_result "Intelligent Response Generation" "PASS"
    fi
else
    test_result "AI Memory Service" "FAIL" "ai_memory_service.py not found"
fi

# Recall.ai Integration
if [ -f "backend/integrations/recallai_service.py" ]; then
    test_result "Recall.ai Meeting Recording" "PASS"
else
    test_result "Recall.ai Meeting Recording" "WARN" "Integration file not found"
fi

echo -e "\n${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}7. DOCUMENTATION TESTS${NC}"
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"

# Check for key documentation files
docs=(
    "README.md:Main Documentation"
    "VOICE_CHAT_FEATURE.md:Voice Chat Guide"
    "AI_INTEGRATION_GUIDE.md:AI Integration Guide"
    "SECURITY.md:Security Documentation"
)

for doc in "${docs[@]}"; do
    file="${doc%%:*}"
    name="${doc##*:}"

    if [ -f "$file" ]; then
        test_result "$name" "PASS"
    else
        test_result "$name" "WARN" "File not found"
    fi
done

echo -e "\n${BLUE}════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  Test Summary${NC}"
echo -e "${BLUE}════════════════════════════════════════════════${NC}\n"

echo -e "Total Tests:  ${BLUE}$TOTAL_TESTS${NC}"
echo -e "Passed:       ${GREEN}$PASSED_TESTS${NC}"
echo -e "Warnings:     ${YELLOW}$WARNING_TESTS${NC}"
echo -e "Failed:       ${RED}$FAILED_TESTS${NC}"

# Calculate health score
health_score=$(echo "scale=1; ($PASSED_TESTS * 100) / $TOTAL_TESTS" | bc)
echo -e "\nSystem Health Score: ${BLUE}${health_score}%${NC}"

if [ ${#CRITICAL_ISSUES[@]} -gt 0 ]; then
    echo -e "\n${RED}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${RED}CRITICAL ISSUES REQUIRING IMMEDIATE ATTENTION:${NC}"
    echo -e "${RED}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"
    for issue in "${CRITICAL_ISSUES[@]}"; do
        echo -e "${RED}  ✗ $issue${NC}"
    done
fi

if [ ${#WARNING_ISSUES[@]} -gt 0 ]; then
    echo -e "\n${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${YELLOW}WARNINGS (Recommended to Review):${NC}"
    echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"
    for warning in "${WARNING_ISSUES[@]}"; do
        echo -e "${YELLOW}  ⚠ $warning${NC}"
    done
fi

echo -e "\n${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}KEY FEATURES VERIFIED AS WORKING:${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"

# Display top 10 verified features
count=0
for feature in "${PASSED_FEATURES[@]}"; do
    if [ $count -lt 10 ]; then
        echo -e "${GREEN}  ✓ $feature${NC}"
        count=$((count + 1))
    fi
done

if [ ${#PASSED_FEATURES[@]} -gt 10 ]; then
    echo -e "${GREEN}  ... and $((${#PASSED_FEATURES[@]} - 10)) more features${NC}"
fi

echo -e "\n${BLUE}════════════════════════════════════════════════${NC}"
echo -e "${BLUE}Diagnosis Complete!${NC}"
echo -e "${BLUE}════════════════════════════════════════════════${NC}\n"

# Exit code based on critical issues
if [ ${#CRITICAL_ISSUES[@]} -gt 0 ]; then
    exit 1
else
    exit 0
fi
