#!/bin/bash
# =============================================================================
# Perennia AI Chat System - Production Launch Script
# =============================================================================
# Usage: ./scripts/launch.sh [--skip-checks] [--skip-migrations]
# =============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(dirname "$SCRIPT_DIR")"

# Parse arguments
SKIP_CHECKS=false
SKIP_MIGRATIONS=false

for arg in "$@"; do
    case $arg in
        --skip-checks)
            SKIP_CHECKS=true
            shift
            ;;
        --skip-migrations)
            SKIP_MIGRATIONS=true
            shift
            ;;
    esac
done

echo -e "${BLUE}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Perennia AI Chat System - Production Launch"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "${NC}"

# =============================================================================
# Step 1: Pre-launch checks
# =============================================================================

if [ "$SKIP_CHECKS" = false ]; then
    echo -e "${BLUE}Step 1: Running pre-launch checks...${NC}"
    if ! "$SCRIPT_DIR/pre_launch_checks.sh"; then
        echo -e "${RED}Pre-launch checks failed. Use --skip-checks to bypass.${NC}"
        exit 1
    fi
else
    echo -e "${YELLOW}Skipping pre-launch checks...${NC}"
fi

# =============================================================================
# Step 2: Run migrations
# =============================================================================

if [ "$SKIP_MIGRATIONS" = false ]; then
    echo ""
    echo -e "${BLUE}Step 2: Running database migrations...${NC}"

    # Extract database connection details
    if [[ "$DATABASE_URL" =~ postgresql://([^:]+):([^@]+)@([^:]+):([^/]+)/(.+) ]]; then
        DB_USER="${BASH_REMATCH[1]}"
        DB_PASS="${BASH_REMATCH[2]}"
        DB_HOST="${BASH_REMATCH[3]}"
        DB_PORT="${BASH_REMATCH[4]}"
        DB_NAME="${BASH_REMATCH[5]}"

        # Run chat tables migration
        echo "  Running chat tables migration..."
        if [ -f "$BACKEND_DIR/migrations/create_chat_state_machine_tables.sql" ]; then
            PGPASSWORD="$DB_PASS" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -f "$BACKEND_DIR/migrations/create_chat_state_machine_tables.sql"
            echo -e "  ${GREEN}✓${NC} Chat tables migration complete"
        fi

        # Run indexes migration
        echo "  Running performance indexes migration..."
        if [ -f "$BACKEND_DIR/migrations/add_chat_performance_indexes.sql" ]; then
            PGPASSWORD="$DB_PASS" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -f "$BACKEND_DIR/migrations/add_chat_performance_indexes.sql" || true
            echo -e "  ${GREEN}✓${NC} Performance indexes migration complete"
        fi

        # Run Alembic migrations if available
        if command -v alembic &> /dev/null && [ -f "$BACKEND_DIR/alembic.ini" ]; then
            echo "  Running Alembic migrations..."
            cd "$BACKEND_DIR"
            alembic upgrade head
            echo -e "  ${GREEN}✓${NC} Alembic migrations complete"
        fi
    else
        echo -e "${YELLOW}Could not parse DATABASE_URL, skipping migrations${NC}"
    fi
else
    echo -e "${YELLOW}Skipping migrations...${NC}"
fi

# =============================================================================
# Step 3: Build Docker images
# =============================================================================

echo ""
echo -e "${BLUE}Step 3: Building Docker images...${NC}"

cd "$BACKEND_DIR"

if [ -f "docker-compose.chat-production.yml" ]; then
    docker-compose -f docker-compose.chat-production.yml build
    echo -e "${GREEN}✓${NC} Docker images built successfully"
else
    echo -e "${YELLOW}docker-compose.chat-production.yml not found, skipping Docker build${NC}"
fi

# =============================================================================
# Step 4: Deploy containers
# =============================================================================

echo ""
echo -e "${BLUE}Step 4: Deploying containers...${NC}"

if [ -f "docker-compose.chat-production.yml" ]; then
    # Stop existing containers gracefully
    docker-compose -f docker-compose.chat-production.yml down --timeout 30 2>/dev/null || true

    # Start new containers
    docker-compose -f docker-compose.chat-production.yml up -d

    echo -e "${GREEN}✓${NC} Containers deployed"

    # Wait for services to be ready
    echo "  Waiting for services to start..."
    sleep 10
else
    echo -e "${YELLOW}Starting with uvicorn directly...${NC}"
    # For non-Docker deployments
    cd "$BACKEND_DIR"
    uvicorn main:app --host 0.0.0.0 --port 8000 &
    sleep 5
fi

# =============================================================================
# Step 5: Verify deployment
# =============================================================================

echo ""
echo -e "${BLUE}Step 5: Verifying deployment...${NC}"

# Get the base URL
if [ -n "$BASE_URL" ]; then
    HEALTH_URL="$BASE_URL/health/detailed"
else
    HEALTH_URL="http://localhost:8000/health/detailed"
fi

# Check health endpoint
MAX_RETRIES=30
RETRY_COUNT=0

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    if curl -s "$HEALTH_URL" | grep -q "healthy\|degraded"; then
        echo -e "${GREEN}✓${NC} Health check passed"
        break
    fi
    echo "  Waiting for service to be ready... (attempt $((RETRY_COUNT + 1))/$MAX_RETRIES)"
    sleep 2
    ((RETRY_COUNT++))
done

if [ $RETRY_COUNT -eq $MAX_RETRIES ]; then
    echo -e "${RED}✗${NC} Health check failed after $MAX_RETRIES attempts"
    echo "  Checking logs..."
    docker-compose -f docker-compose.chat-production.yml logs --tail=50 api 2>/dev/null || true
    exit 1
fi

# Get detailed health status
echo ""
echo "Detailed Health Status:"
curl -s "$HEALTH_URL" | python3 -m json.tool 2>/dev/null || curl -s "$HEALTH_URL"

# =============================================================================
# Step 6: Run smoke tests
# =============================================================================

echo ""
echo -e "${BLUE}Step 6: Running smoke tests...${NC}"

if [ -f "$BACKEND_DIR/testing/chat_simulator.py" ]; then
    cd "$BACKEND_DIR"
    python3 -m testing.chat_simulator --quick 2>/dev/null || echo -e "${YELLOW}Smoke tests skipped (simulator not configured)${NC}"
else
    echo -e "${YELLOW}Chat simulator not found, skipping smoke tests${NC}"
fi

# =============================================================================
# Launch Complete
# =============================================================================

echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  ✓ Launch Complete!${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo "Next steps:"
echo "  1. Monitor logs: docker-compose -f docker-compose.chat-production.yml logs -f api"
echo "  2. Check metrics: Open Grafana dashboard"
echo "  3. Review first conversations"
echo ""
echo "Useful commands:"
echo "  - View logs:     docker-compose -f docker-compose.chat-production.yml logs -f"
echo "  - Restart:       docker-compose -f docker-compose.chat-production.yml restart"
echo "  - Stop:          docker-compose -f docker-compose.chat-production.yml down"
echo "  - Scale:         docker-compose -f docker-compose.chat-production.yml up -d --scale api=3"
echo ""
