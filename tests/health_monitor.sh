#!/bin/bash
# =============================================================================
# Health Monitoring Script for Pipeline360
# =============================================================================
# Usage: ./tests/health_monitor.sh [API_URL] [--continuous]
# Example: ./tests/health_monitor.sh https://api.perenniaai.com
#          ./tests/health_monitor.sh --continuous   # Run every 5 minutes
#
# Environment Variables:
#   TEST_API_KEY - API key to bypass IP restrictions (set in server .env)
#
# Examples:
#   ./tests/health_monitor.sh https://staging-api.example.com
#   TEST_API_KEY=your-secret-key ./tests/health_monitor.sh https://api.example.com

set -e

API_URL="${1:-https://api.perenniaai.com}"
TEST_API_KEY="${TEST_API_KEY:-}"
CONTINUOUS=false
INTERVAL=300  # 5 minutes

# Check for continuous flag
if [ "$1" = "--continuous" ] || [ "$2" = "--continuous" ]; then
    CONTINUOUS=true
fi

# Build API key header if provided
API_KEY_HEADER=""
if [ -n "$TEST_API_KEY" ]; then
    API_KEY_HEADER="-H X-Test-API-Key:$TEST_API_KEY"
fi

echo "=============================================="
echo "  Pipeline360 Health Monitor"
echo "=============================================="
echo "API URL: $API_URL"
echo "Using Test API Key: $([ -n "$TEST_API_KEY" ] && echo "Yes" || echo "No")"
echo "Mode: $([ "$CONTINUOUS" = true ] && echo "Continuous (every $INTERVAL seconds)" || echo "Single check")"
echo ""

# Health check function
check_health() {
    local TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
    local ALL_HEALTHY=true

    echo "[$TIMESTAMP] Running health checks..."
    echo ""

    # 1. Basic health check
    echo "1. Basic Health Endpoint"
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL/health" --max-time 10 || echo "000")
    if [ "$HTTP_CODE" = "200" ]; then
        echo "   ✅ /health: OK (HTTP $HTTP_CODE)"
    else
        echo "   ❌ /health: FAILED (HTTP $HTTP_CODE)"
        ALL_HEALTHY=false
    fi

    # 2. Detailed health check
    echo ""
    echo "2. Detailed Health Endpoint"
    HEALTH_RESPONSE=$(curl -s "$API_URL/health/detailed" --max-time 15 || echo '{"error":"timeout"}')

    if echo "$HEALTH_RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); sys.exit(0 if d.get('status')=='healthy' else 1)" 2>/dev/null; then
        echo "   ✅ /health/detailed: HEALTHY"

        # Parse individual checks
        echo ""
        echo "   Component Status:"
        echo "$HEALTH_RESPONSE" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    checks = d.get('checks', {})
    for name, status in checks.items():
        icon = '✅' if status.get('healthy', False) else '❌'
        print(f'     {icon} {name}: {status.get(\"status\", \"unknown\")}')
except: pass
" 2>/dev/null || echo "     Could not parse component status"

    else
        echo "   ⚠️  /health/detailed: UNHEALTHY or not available"
        ALL_HEALTHY=false
    fi

    # 3. Auth endpoint check
    echo ""
    echo "3. Authentication Endpoint"
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL/token" $API_KEY_HEADER -X POST \
        -H "Content-Type: application/x-www-form-urlencoded" \
        -d "username=admin@perenniaai.com&password=demo123" --max-time 10 || echo "000")
    if [ "$HTTP_CODE" = "200" ]; then
        echo "   ✅ /token: OK (HTTP $HTTP_CODE)"
    else
        echo "   ❌ /token: FAILED (HTTP $HTTP_CODE)"
        ALL_HEALTHY=false
    fi

    # 4. API response time check
    echo ""
    echo "4. API Response Time"
    START_TIME=$(python3 -c "import time; print(time.time())")
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL/api/v1/loans/" $API_KEY_HEADER \
        -H "Authorization: Bearer $(curl -s -X POST "$API_URL/token" $API_KEY_HEADER \
            -H "Content-Type: application/x-www-form-urlencoded" \
            -d "username=admin@perenniaai.com&password=demo123" | \
            python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null)" \
        --max-time 15 || echo "000")
    END_TIME=$(python3 -c "import time; print(time.time())")
    RESPONSE_TIME=$(python3 -c "print(f'{$END_TIME - $START_TIME:.3f}')")

    if [ "$HTTP_CODE" = "200" ]; then
        if python3 -c "exit(0 if $RESPONSE_TIME < 2.0 else 1)"; then
            echo "   ✅ /api/v1/loans/: OK (${RESPONSE_TIME}s)"
        else
            echo "   ⚠️  /api/v1/loans/: SLOW (${RESPONSE_TIME}s)"
            ALL_HEALTHY=false
        fi
    else
        echo "   ❌ /api/v1/loans/: FAILED (HTTP $HTTP_CODE)"
        ALL_HEALTHY=false
    fi

    # 5. OpenAPI docs check
    echo ""
    echo "5. API Documentation"
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL/docs" --max-time 10 || echo "000")
    if [ "$HTTP_CODE" = "200" ]; then
        echo "   ✅ /docs: OK (HTTP $HTTP_CODE)"
    else
        echo "   ⚠️  /docs: Not available (HTTP $HTTP_CODE)"
    fi

    # Summary
    echo ""
    echo "=============================================="
    if [ "$ALL_HEALTHY" = true ]; then
        echo "  STATUS: ✅ ALL SYSTEMS HEALTHY"
    else
        echo "  STATUS: ⚠️  ISSUES DETECTED"
    fi
    echo "=============================================="
    echo ""

    return $([ "$ALL_HEALTHY" = true ] && echo 0 || echo 1)
}

# Run health checks
if [ "$CONTINUOUS" = true ]; then
    echo "Starting continuous monitoring (Ctrl+C to stop)..."
    echo ""

    while true; do
        check_health || true
        echo "Next check in $INTERVAL seconds..."
        echo ""
        sleep $INTERVAL
    done
else
    check_health
fi
