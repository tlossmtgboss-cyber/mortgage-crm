#!/bin/bash
# =============================================================================
# Perennia AI Chat System - Pre-Launch Validation Script
# =============================================================================
# Run this script before deploying to production to validate all requirements
# Usage: ./scripts/pre_launch_checks.sh
# =============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Counters
PASSED=0
FAILED=0
WARNINGS=0

# =============================================================================
# Helper Functions
# =============================================================================

print_header() {
    echo ""
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}  $1${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

check_pass() {
    echo -e "  ${GREEN}✓${NC} $1"
    ((PASSED++))
}

check_fail() {
    echo -e "  ${RED}✗${NC} $1"
    ((FAILED++))
}

check_warn() {
    echo -e "  ${YELLOW}⚠${NC} $1"
    ((WARNINGS++))
}

# =============================================================================
# Environment Variable Checks
# =============================================================================

print_header "Checking Environment Variables"

# Required variables
REQUIRED_VARS=(
    "DATABASE_URL"
    "REDIS_URL"
    "ANTHROPIC_API_KEY"
    "TWILIO_ACCOUNT_SID"
    "TWILIO_AUTH_TOKEN"
    "TWILIO_PHONE_NUMBER"
    "LO_PHONE_NUMBER"
    "BASE_URL"
)

for var in "${REQUIRED_VARS[@]}"; do
    if [ -z "${!var}" ]; then
        check_fail "$var is not set"
    else
        # Mask sensitive values
        if [[ "$var" == *"KEY"* ]] || [[ "$var" == *"TOKEN"* ]] || [[ "$var" == *"PASSWORD"* ]]; then
            check_pass "$var is set (***masked***)"
        else
            check_pass "$var is set: ${!var:0:30}..."
        fi
    fi
done

# Check for production environment
if [ "$ENVIRONMENT" == "production" ]; then
    check_pass "ENVIRONMENT is set to production"
else
    check_warn "ENVIRONMENT is not 'production' (current: ${ENVIRONMENT:-not set})"
fi

# Check DEBUG is false
if [ "$DEBUG" == "false" ] || [ -z "$DEBUG" ]; then
    check_pass "DEBUG is disabled"
else
    check_fail "DEBUG should be 'false' in production (current: $DEBUG)"
fi

# =============================================================================
# Database Checks
# =============================================================================

print_header "Checking Database Connection"

if command -v psql &> /dev/null; then
    # Extract database connection details
    if [[ "$DATABASE_URL" =~ postgresql://([^:]+):([^@]+)@([^:]+):([^/]+)/(.+) ]]; then
        DB_USER="${BASH_REMATCH[1]}"
        DB_PASS="${BASH_REMATCH[2]}"
        DB_HOST="${BASH_REMATCH[3]}"
        DB_PORT="${BASH_REMATCH[4]}"
        DB_NAME="${BASH_REMATCH[5]}"

        # Test connection
        if PGPASSWORD="$DB_PASS" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -c "SELECT 1" &> /dev/null; then
            check_pass "Database connection successful"

            # Check for chat tables
            TABLE_COUNT=$(PGPASSWORD="$DB_PASS" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -t -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_name IN ('chat_sessions', 'chat_messages', 'call_requests')")
            TABLE_COUNT=$(echo "$TABLE_COUNT" | tr -d ' ')

            if [ "$TABLE_COUNT" -eq 3 ]; then
                check_pass "All chat tables exist (chat_sessions, chat_messages, call_requests)"
            else
                check_fail "Missing chat tables (found $TABLE_COUNT/3)"
            fi

            # Check for indexes
            INDEX_COUNT=$(PGPASSWORD="$DB_PASS" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -t -c "SELECT COUNT(*) FROM pg_indexes WHERE tablename IN ('chat_sessions', 'chat_messages', 'call_requests')")
            INDEX_COUNT=$(echo "$INDEX_COUNT" | tr -d ' ')

            if [ "$INDEX_COUNT" -ge 20 ]; then
                check_pass "Performance indexes exist ($INDEX_COUNT indexes found)"
            else
                check_warn "Expected 20+ indexes, found $INDEX_COUNT"
            fi
        else
            check_fail "Database connection failed"
        fi
    else
        check_fail "Could not parse DATABASE_URL"
    fi
else
    check_warn "psql not found, skipping database checks"
fi

# =============================================================================
# Redis Checks
# =============================================================================

print_header "Checking Redis Connection"

if command -v redis-cli &> /dev/null; then
    # Extract Redis connection details
    if [[ "$REDIS_URL" =~ redis://([^:]+):([0-9]+) ]]; then
        REDIS_HOST="${BASH_REMATCH[1]}"
        REDIS_PORT="${BASH_REMATCH[2]}"

        if redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" ping &> /dev/null; then
            check_pass "Redis connection successful"

            # Check Redis info
            REDIS_VERSION=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" INFO server | grep redis_version | cut -d: -f2 | tr -d '\r')
            check_pass "Redis version: $REDIS_VERSION"

            REDIS_MEMORY=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" INFO memory | grep used_memory_human | cut -d: -f2 | tr -d '\r')
            check_pass "Redis memory usage: $REDIS_MEMORY"
        else
            check_fail "Redis connection failed"
        fi
    else
        check_fail "Could not parse REDIS_URL"
    fi
else
    check_warn "redis-cli not found, skipping Redis checks"
fi

# =============================================================================
# Python Dependencies
# =============================================================================

print_header "Checking Python Dependencies"

if command -v python3 &> /dev/null; then
    check_pass "Python3 found: $(python3 --version)"

    # Check critical packages
    PACKAGES=(
        "fastapi"
        "uvicorn"
        "sqlalchemy"
        "redis"
        "anthropic"
        "twilio"
        "pydantic"
        "pydantic_settings"
    )

    for pkg in "${PACKAGES[@]}"; do
        if python3 -c "import $pkg" 2>/dev/null; then
            check_pass "$pkg is installed"
        else
            check_fail "$pkg is not installed"
        fi
    done
else
    check_fail "Python3 not found"
fi

# =============================================================================
# File Checks
# =============================================================================

print_header "Checking Required Files"

REQUIRED_FILES=(
    "main.py"
    "config.py"
    "chat_system_bootstrap.py"
    "routes/chat_state_routes.py"
    "services/chat_session_manager.py"
    "services/circuit_breaker.py"
    "services/graceful_degradation.py"
    "services/response_cache.py"
    "services/message_deduplication.py"
    "services/conversation_quality.py"
    "middleware/rate_limiting.py"
    "middleware/structured_logging.py"
    "models/chat_state_machine_models.py"
)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(dirname "$SCRIPT_DIR")"

for file in "${REQUIRED_FILES[@]}"; do
    if [ -f "$BACKEND_DIR/$file" ]; then
        check_pass "$file exists"
    else
        check_fail "$file not found"
    fi
done

# =============================================================================
# Docker Checks
# =============================================================================

print_header "Checking Docker Configuration"

if command -v docker &> /dev/null; then
    check_pass "Docker found: $(docker --version)"

    if docker info &> /dev/null; then
        check_pass "Docker daemon is running"
    else
        check_fail "Docker daemon is not running"
    fi

    if [ -f "$BACKEND_DIR/docker-compose.chat-production.yml" ]; then
        check_pass "docker-compose.chat-production.yml exists"

        if command -v docker-compose &> /dev/null; then
            if docker-compose -f "$BACKEND_DIR/docker-compose.chat-production.yml" config &> /dev/null; then
                check_pass "Docker Compose config is valid"
            else
                check_fail "Docker Compose config has errors"
            fi
        fi
    else
        check_warn "docker-compose.chat-production.yml not found"
    fi
else
    check_warn "Docker not found"
fi

# =============================================================================
# API Connectivity Checks
# =============================================================================

print_header "Checking External API Connectivity"

# Anthropic API
if [ -n "$ANTHROPIC_API_KEY" ]; then
    if curl -s -o /dev/null -w "%{http_code}" -H "x-api-key: $ANTHROPIC_API_KEY" -H "anthropic-version: 2023-06-01" "https://api.anthropic.com/v1/messages" -X POST -d '{"model":"claude-sonnet-4-20250514","max_tokens":1,"messages":[]}' | grep -q "400\|401\|200"; then
        check_pass "Anthropic API is reachable"
    else
        check_warn "Could not verify Anthropic API connectivity"
    fi
else
    check_fail "ANTHROPIC_API_KEY not set"
fi

# Twilio API
if [ -n "$TWILIO_ACCOUNT_SID" ] && [ -n "$TWILIO_AUTH_TOKEN" ]; then
    TWILIO_RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" -u "$TWILIO_ACCOUNT_SID:$TWILIO_AUTH_TOKEN" "https://api.twilio.com/2010-04-01/Accounts/$TWILIO_ACCOUNT_SID.json")
    if [ "$TWILIO_RESPONSE" == "200" ]; then
        check_pass "Twilio API is reachable and authenticated"
    else
        check_fail "Twilio API authentication failed (HTTP $TWILIO_RESPONSE)"
    fi
else
    check_fail "Twilio credentials not set"
fi

# =============================================================================
# Security Checks
# =============================================================================

print_header "Security Checks"

# Check for .env in .gitignore
if [ -f "$BACKEND_DIR/../.gitignore" ]; then
    if grep -q "\.env" "$BACKEND_DIR/../.gitignore"; then
        check_pass ".env is in .gitignore"
    else
        check_fail ".env should be in .gitignore"
    fi
fi

# Check for hardcoded secrets (basic check)
if grep -r "sk-ant-" "$BACKEND_DIR"/*.py 2>/dev/null | grep -v "\.pyc" | grep -v "__pycache__"; then
    check_fail "Possible hardcoded API keys found in Python files"
else
    check_pass "No hardcoded API keys found"
fi

# Check HTTPS in BASE_URL
if [[ "$BASE_URL" == https://* ]]; then
    check_pass "BASE_URL uses HTTPS"
else
    check_warn "BASE_URL should use HTTPS in production"
fi

# =============================================================================
# Summary
# =============================================================================

print_header "Pre-Launch Check Summary"

echo ""
echo -e "  ${GREEN}Passed:${NC}   $PASSED"
echo -e "  ${RED}Failed:${NC}   $FAILED"
echo -e "  ${YELLOW}Warnings:${NC} $WARNINGS"
echo ""

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}  ✓ All critical checks passed! Ready for launch.${NC}"
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    exit 0
else
    echo -e "${RED}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${RED}  ✗ $FAILED check(s) failed. Please fix before launching.${NC}"
    echo -e "${RED}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    exit 1
fi
