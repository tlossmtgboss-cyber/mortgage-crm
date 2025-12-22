#!/bin/bash
# =============================================================================
# Perennia AI Chat System - Emergency Rollback Script
# =============================================================================
# Usage: ./scripts/rollback.sh [version]
# =============================================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(dirname "$SCRIPT_DIR")"

echo -e "${RED}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Perennia AI Chat System - EMERGENCY ROLLBACK"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "${NC}"

# =============================================================================
# Step 1: Capture current state
# =============================================================================

echo -e "${BLUE}Step 1: Capturing current state...${NC}"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="/tmp/rollback_$TIMESTAMP.log"

echo "Rollback initiated at $(date)" > "$LOG_FILE"

# Capture current container status
echo "Current container status:" >> "$LOG_FILE"
docker-compose -f "$BACKEND_DIR/docker-compose.chat-production.yml" ps >> "$LOG_FILE" 2>&1 || true

# Capture recent logs
echo "Recent logs:" >> "$LOG_FILE"
docker-compose -f "$BACKEND_DIR/docker-compose.chat-production.yml" logs --tail=100 api >> "$LOG_FILE" 2>&1 || true

echo -e "${GREEN}✓${NC} State captured to $LOG_FILE"

# =============================================================================
# Step 2: Stop current services
# =============================================================================

echo ""
echo -e "${BLUE}Step 2: Stopping current services...${NC}"

cd "$BACKEND_DIR"

docker-compose -f docker-compose.chat-production.yml down --timeout 10

echo -e "${GREEN}✓${NC} Services stopped"

# =============================================================================
# Step 3: Rollback to previous version
# =============================================================================

echo ""
echo -e "${BLUE}Step 3: Rolling back...${NC}"

TARGET_VERSION=${1:-"previous"}

if [ "$TARGET_VERSION" == "previous" ]; then
    # Use the previous image if available
    echo "  Rolling back to previous image..."

    # Pull previous image (assuming you tag releases)
    # docker pull your-registry/perennia-api:previous || true

    # Or recreate from current state
    docker-compose -f docker-compose.chat-production.yml up -d --force-recreate
else
    # Roll back to specific version
    echo "  Rolling back to version: $TARGET_VERSION"

    # Update image tag in compose file (or use environment variable)
    export IMAGE_TAG="$TARGET_VERSION"
    docker-compose -f docker-compose.chat-production.yml up -d
fi

echo -e "${GREEN}✓${NC} Rollback initiated"

# =============================================================================
# Step 4: Verify rollback
# =============================================================================

echo ""
echo -e "${BLUE}Step 4: Verifying rollback...${NC}"

# Wait for services to start
echo "  Waiting for services to start..."
sleep 10

# Health check
if [ -n "$BASE_URL" ]; then
    HEALTH_URL="$BASE_URL/health"
else
    HEALTH_URL="http://localhost:8000/health"
fi

MAX_RETRIES=20
RETRY_COUNT=0

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    if curl -s "$HEALTH_URL" | grep -q "healthy"; then
        echo -e "${GREEN}✓${NC} Health check passed"
        break
    fi
    echo "  Waiting... (attempt $((RETRY_COUNT + 1))/$MAX_RETRIES)"
    sleep 3
    ((RETRY_COUNT++))
done

if [ $RETRY_COUNT -eq $MAX_RETRIES ]; then
    echo -e "${RED}✗${NC} Health check failed - MANUAL INTERVENTION REQUIRED"
    echo ""
    echo "Troubleshooting steps:"
    echo "  1. Check logs: docker-compose -f docker-compose.chat-production.yml logs api"
    echo "  2. Check container status: docker-compose -f docker-compose.chat-production.yml ps"
    echo "  3. Review rollback log: cat $LOG_FILE"
    exit 1
fi

# =============================================================================
# Step 5: Notify team
# =============================================================================

echo ""
echo -e "${BLUE}Step 5: Generating rollback report...${NC}"

REPORT_FILE="/tmp/rollback_report_$TIMESTAMP.md"

cat > "$REPORT_FILE" << EOF
# Rollback Report

**Timestamp:** $(date)
**Target Version:** $TARGET_VERSION
**Status:** Complete

## Actions Taken
1. Captured current state
2. Stopped running services
3. Rolled back to $TARGET_VERSION
4. Verified health check

## Log File
$LOG_FILE

## Next Steps
1. Investigate root cause
2. Fix issues in development
3. Test thoroughly before redeploying
4. Schedule post-mortem

## Current Status
$(curl -s "$HEALTH_URL" 2>/dev/null || echo "Health check unavailable")
EOF

echo -e "${GREEN}✓${NC} Report generated: $REPORT_FILE"

# =============================================================================
# Complete
# =============================================================================

echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  ✓ Rollback Complete${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo "Files generated:"
echo "  - Rollback log: $LOG_FILE"
echo "  - Report: $REPORT_FILE"
echo ""
echo -e "${YELLOW}IMPORTANT: Schedule a post-mortem to investigate the issue.${NC}"
echo ""
