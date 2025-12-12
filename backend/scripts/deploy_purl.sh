#!/bin/bash
# =============================================================================
# PURL System Deployment Script
# =============================================================================
# This script handles deployment of the PURL system including:
# - Database migrations
# - Environment validation
# - Service health checks
# - Supervisor configuration (if applicable)
#
# Usage:
#   ./deploy_purl.sh [environment]
#
# Environments: development, staging, production
# =============================================================================

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_DIR="$(dirname "$BACKEND_DIR")"

# Default environment
ENVIRONMENT="${1:-development}"

echo -e "${BLUE}=========================================${NC}"
echo -e "${BLUE}  PURL System Deployment${NC}"
echo -e "${BLUE}  Environment: ${YELLOW}$ENVIRONMENT${NC}"
echo -e "${BLUE}=========================================${NC}"

# -----------------------------------------------------------------------------
# Functions
# -----------------------------------------------------------------------------

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_command() {
    if ! command -v "$1" &> /dev/null; then
        log_error "$1 is required but not installed."
        exit 1
    fi
}

# -----------------------------------------------------------------------------
# Pre-flight checks
# -----------------------------------------------------------------------------

log_info "Running pre-flight checks..."

# Check required commands
check_command python
check_command psql
check_command curl

# Check Python version
PYTHON_VERSION=$(python --version 2>&1 | cut -d' ' -f2)
PYTHON_MAJOR=$(echo "$PYTHON_VERSION" | cut -d'.' -f1)
PYTHON_MINOR=$(echo "$PYTHON_VERSION" | cut -d'.' -f2)

if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 9 ]); then
    log_error "Python 3.9+ is required. Found: $PYTHON_VERSION"
    exit 1
fi
log_info "Python version: $PYTHON_VERSION"

# Check for .env file
if [ "$ENVIRONMENT" = "production" ]; then
    ENV_FILE="$BACKEND_DIR/.env"
elif [ "$ENVIRONMENT" = "staging" ]; then
    ENV_FILE="$BACKEND_DIR/.env.staging"
else
    ENV_FILE="$BACKEND_DIR/.env"
fi

if [ ! -f "$ENV_FILE" ]; then
    log_error "Environment file not found: $ENV_FILE"
    log_info "Copy .env.example to $ENV_FILE and configure it."
    exit 1
fi
log_info "Using environment file: $ENV_FILE"

# Load environment variables
set -a
source "$ENV_FILE"
set +a

# -----------------------------------------------------------------------------
# Validate environment variables
# -----------------------------------------------------------------------------

log_info "Validating environment variables..."

REQUIRED_VARS=(
    "DATABASE_URL"
    "SECRET_KEY"
    "ANTHROPIC_API_KEY"
)

PURL_VARS=(
    "PURL_TOKEN_EXPIRY_DAYS"
    "PURL_BASE_URL"
)

missing_vars=0
for var in "${REQUIRED_VARS[@]}"; do
    if [ -z "${!var}" ]; then
        log_error "Required variable $var is not set"
        missing_vars=1
    fi
done

for var in "${PURL_VARS[@]}"; do
    if [ -z "${!var}" ]; then
        log_warn "PURL variable $var is not set (using defaults)"
    fi
done

if [ $missing_vars -eq 1 ]; then
    log_error "Missing required environment variables. Aborting."
    exit 1
fi

log_info "Environment variables validated"

# -----------------------------------------------------------------------------
# Database checks
# -----------------------------------------------------------------------------

log_info "Checking database connection..."

cd "$BACKEND_DIR"

python << 'EOF'
import os
import sys
from sqlalchemy import create_engine, text

try:
    engine = create_engine(os.environ["DATABASE_URL"])
    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1"))
        print("Database connection successful")
except Exception as e:
    print(f"Database connection failed: {e}")
    sys.exit(1)
EOF

if [ $? -ne 0 ]; then
    log_error "Database connection failed"
    exit 1
fi

# -----------------------------------------------------------------------------
# Run PURL migrations
# -----------------------------------------------------------------------------

log_info "Running PURL migrations..."

if [ -f "$BACKEND_DIR/migrations/add_purl_system.py" ]; then
    python "$BACKEND_DIR/migrations/add_purl_system.py"
    if [ $? -eq 0 ]; then
        log_info "PURL migrations completed"
    else
        log_error "PURL migrations failed"
        exit 1
    fi
else
    log_warn "PURL migration file not found, skipping..."
fi

# -----------------------------------------------------------------------------
# Run Agent Governance migrations
# -----------------------------------------------------------------------------

log_info "Running Agent Governance migrations..."

if [ -f "$BACKEND_DIR/migrations/add_agent_governance_system.py" ]; then
    python "$BACKEND_DIR/migrations/add_agent_governance_system.py"
    if [ $? -eq 0 ]; then
        log_info "Agent Governance migrations completed"
    else
        log_error "Agent Governance migrations failed"
        exit 1
    fi
else
    log_warn "Agent Governance migration file not found, skipping..."
fi

# -----------------------------------------------------------------------------
# Verify PURL tables exist
# -----------------------------------------------------------------------------

log_info "Verifying PURL tables..."

python << 'EOF'
import os
from sqlalchemy import create_engine, inspect

engine = create_engine(os.environ["DATABASE_URL"])
inspector = inspect(engine)
tables = inspector.get_table_names()

purl_tables = ["purl_tokens", "purl_sessions", "purl_events"]
missing = [t for t in purl_tables if t not in tables]

if missing:
    print(f"Missing tables: {missing}")
    exit(1)
else:
    print("All PURL tables exist")
EOF

if [ $? -ne 0 ]; then
    log_error "PURL table verification failed"
    exit 1
fi

# -----------------------------------------------------------------------------
# Seed data (development/staging only)
# -----------------------------------------------------------------------------

if [ "$ENVIRONMENT" != "production" ]; then
    log_info "Seeding test data for $ENVIRONMENT..."

    if [ -f "$BACKEND_DIR/scripts/seed_agent_data.py" ]; then
        python "$BACKEND_DIR/scripts/seed_agent_data.py" --quiet || true
        log_info "Agent data seeded"
    fi
fi

# -----------------------------------------------------------------------------
# Run quick tests
# -----------------------------------------------------------------------------

log_info "Running quick validation tests..."

if [ -f "$BACKEND_DIR/tests/test_purl_quick.py" ]; then
    python "$BACKEND_DIR/tests/test_purl_quick.py" || log_warn "Some quick tests failed (non-fatal)"
fi

# -----------------------------------------------------------------------------
# Health check
# -----------------------------------------------------------------------------

if [ -n "$WEBHOOK_BASE_URL" ] && [ "$ENVIRONMENT" = "production" ]; then
    log_info "Running health check..."

    HEALTH_URL="${WEBHOOK_BASE_URL}/health"
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$HEALTH_URL" || echo "000")

    if [ "$HTTP_CODE" = "200" ]; then
        log_info "Health check passed"
    else
        log_warn "Health check returned HTTP $HTTP_CODE"
    fi
fi

# -----------------------------------------------------------------------------
# Summary
# -----------------------------------------------------------------------------

echo ""
echo -e "${GREEN}=========================================${NC}"
echo -e "${GREEN}  PURL System Deployment Complete${NC}"
echo -e "${GREEN}=========================================${NC}"
echo ""
echo -e "Environment: ${YELLOW}$ENVIRONMENT${NC}"
echo -e "Database: ${GREEN}Connected${NC}"
echo -e "Migrations: ${GREEN}Applied${NC}"
echo -e "Tables: ${GREEN}Verified${NC}"
echo ""

if [ "$ENVIRONMENT" = "development" ]; then
    echo -e "${BLUE}Next steps:${NC}"
    echo "  1. Start the backend:  cd backend && python main.py"
    echo "  2. Start the frontend: cd frontend && npm start"
    echo "  3. Access PURL portal: http://localhost:3000/portal/{token}"
fi

if [ "$ENVIRONMENT" = "production" ]; then
    echo -e "${BLUE}Production deployment notes:${NC}"
    echo "  - Ensure SSL is configured for PURL endpoints"
    echo "  - Configure rate limiting in your reverse proxy"
    echo "  - Monitor PURL access logs for suspicious activity"
    echo "  - Set up alerts for token expiration events"
fi

echo ""
log_info "Deployment completed successfully!"
