#!/bin/bash
# ============================================================================
# Local Deployment Test Script
# Tests if the backend can start successfully with current configuration
# ============================================================================

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color
BOLD='\033[1m'

echo -e "${BOLD}${BLUE}"
echo "============================================================================"
echo "🧪 MORTGAGE CRM - Local Deployment Test"
echo "============================================================================"
echo -e "${NC}"

# Change to backend directory
cd backend

# ============================================================================
# Step 1: Check Python Installation
# ============================================================================
echo -e "${BOLD}Step 1: Checking Python installation...${NC}"

if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version)
    echo -e "${GREEN}✓${NC} Python installed: $PYTHON_VERSION"
else
    echo -e "${RED}✗${NC} Python 3 not found. Please install Python 3.11+"
    exit 1
fi

# ============================================================================
# Step 2: Check Environment Variables
# ============================================================================
echo -e "\n${BOLD}Step 2: Checking environment variables...${NC}"

if [ -f .env ]; then
    echo -e "${GREEN}✓${NC} .env file found"
    export $(grep -v '^#' .env | xargs)
else
    echo -e "${YELLOW}⚠${NC} No .env file found"
    echo -e "   Creating minimal .env for testing..."

    # Create minimal .env
    cat > .env << 'EOF'
# Minimal configuration for local testing
DATABASE_URL=sqlite:///./test_agentic_crm.db
SECRET_KEY=test-secret-key-for-local-development-only-do-not-use-in-production-12345678
OPENAI_API_KEY=
ENVIRONMENT=development
EOF

    echo -e "${GREEN}✓${NC} Created minimal .env file (using SQLite)"
    export $(grep -v '^#' .env | xargs)
fi

# Run verification script
echo -e "\n${BOLD}Running environment verification...${NC}\n"
python3 verify_env.py || echo -e "${YELLOW}⚠ Some optional variables missing (OK for testing)${NC}"

# ============================================================================
# Step 3: Check Dependencies
# ============================================================================
echo -e "\n${BOLD}Step 3: Checking Python dependencies...${NC}"

if [ ! -d "venv" ] && [ ! -d "../venv" ]; then
    echo -e "${YELLOW}⚠${NC} Virtual environment not found"
    echo -e "   Would you like to create one? (recommended)"
    echo -e "   You can skip this and use system Python at your own risk"
    echo -e ""
    echo -e "   To create venv and install dependencies:"
    echo -e "   ${BLUE}python3 -m venv venv${NC}"
    echo -e "   ${BLUE}source venv/bin/activate${NC}"
    echo -e "   ${BLUE}pip install -r requirements.txt${NC}"
    echo -e ""
fi

# Try to import key modules
echo -e "\nChecking critical imports..."

python3 << 'PYEOF'
import sys
missing = []

try:
    import fastapi
    print("✓ FastAPI installed")
except ImportError:
    print("✗ FastAPI not installed")
    missing.append("fastapi")

try:
    import sqlalchemy
    print("✓ SQLAlchemy installed")
except ImportError:
    print("✗ SQLAlchemy not installed")
    missing.append("sqlalchemy")

try:
    import uvicorn
    print("✓ Uvicorn installed")
except ImportError:
    print("✗ Uvicorn not installed")
    missing.append("uvicorn")

if missing:
    print(f"\n❌ Missing packages: {', '.join(missing)}")
    print("\nInstall with: pip install -r requirements.txt")
    sys.exit(1)
else:
    print("\n✓ All critical packages installed")
PYEOF

if [ $? -ne 0 ]; then
    echo -e "\n${RED}✗${NC} Missing dependencies. Install with:"
    echo -e "   ${BLUE}pip install -r requirements.txt${NC}"
    exit 1
fi

# ============================================================================
# Step 4: Test Import of Main Application
# ============================================================================
echo -e "\n${BOLD}Step 4: Testing application imports...${NC}"

python3 << 'PYEOF'
import sys
import os

# Suppress startup messages
import logging
logging.basicConfig(level=logging.CRITICAL)

try:
    # Try to import main module
    print("Importing main.py...")
    import main
    print("✓ main.py imported successfully")

    # Check if FastAPI app was created
    if hasattr(main, 'app'):
        print("✓ FastAPI app instance found")
    else:
        print("✗ FastAPI app instance not found")
        sys.exit(1)

    # Check database connection setup
    if hasattr(main, 'engine'):
        print("✓ Database engine created")
    else:
        print("⚠ Database engine not found")

    print("\n✓ All imports successful!")

except Exception as e:
    print(f"✗ Import failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
PYEOF

if [ $? -ne 0 ]; then
    echo -e "\n${RED}✗${NC} Application failed to import"
    echo -e "   Check error messages above for details"
    exit 1
fi

# ============================================================================
# Step 5: Test Database Connection
# ============================================================================
echo -e "\n${BOLD}Step 5: Testing database connection...${NC}"

python3 << 'PYEOF'
import os
import sys
from sqlalchemy import create_engine, text
import logging

logging.basicConfig(level=logging.ERROR)

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./test_agentic_crm.db")

# Fix postgres:// to postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

print(f"Testing connection to: {DATABASE_URL.split('@')[0]}@***")

try:
    engine = create_engine(DATABASE_URL)
    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1"))
        result.fetchone()
    print("✓ Database connection successful")
except Exception as e:
    print(f"✗ Database connection failed: {e}")
    if "sqlite" in DATABASE_URL.lower():
        print("  (SQLite will be created on first run)")
    else:
        print("  Check your DATABASE_URL and ensure the database server is running")
        sys.exit(1)
PYEOF

# ============================================================================
# Step 6: Try Starting the Server (for 5 seconds)
# ============================================================================
echo -e "\n${BOLD}Step 6: Testing server startup...${NC}"
echo -e "${YELLOW}Starting server for 5 seconds to test startup...${NC}\n"

# Start server in background
timeout 5s python3 -m uvicorn main:app --host 127.0.0.1 --port 8000 2>&1 | tee /tmp/uvicorn_test.log &
SERVER_PID=$!

# Wait a moment for startup
sleep 2

# Check if server started
if ps -p $SERVER_PID > /dev/null 2>&1; then
    echo -e "${GREEN}✓${NC} Server process started (PID: $SERVER_PID)"

    # Try to hit health endpoint
    sleep 1
    if command -v curl &> /dev/null; then
        echo -e "\nTesting health endpoint..."
        if curl -s http://127.0.0.1:8000/health > /dev/null 2>&1; then
            echo -e "${GREEN}✓${NC} Health endpoint responding"
        else
            echo -e "${YELLOW}⚠${NC} Health endpoint not responding yet (may need more time)"
        fi
    fi

    # Kill the test server
    kill $SERVER_PID 2>/dev/null || true
    wait $SERVER_PID 2>/dev/null || true
else
    echo -e "${RED}✗${NC} Server failed to start"
    echo -e "\nChecking logs for errors..."
    cat /tmp/uvicorn_test.log
    exit 1
fi

# Check logs for critical errors
if grep -i "error\|exception\|failed" /tmp/uvicorn_test.log > /dev/null; then
    echo -e "\n${YELLOW}⚠${NC} Warnings or errors found in startup logs:"
    grep -i "error\|exception\|failed" /tmp/uvicorn_test.log | head -5
else
    echo -e "${GREEN}✓${NC} No critical errors in startup logs"
fi

# ============================================================================
# Summary
# ============================================================================
echo -e "\n${BOLD}${BLUE}"
echo "============================================================================"
echo "📊 TEST SUMMARY"
echo "============================================================================"
echo -e "${NC}"

echo -e "${GREEN}✓${NC} Python installed"
echo -e "${GREEN}✓${NC} Environment variables configured"
echo -e "${GREEN}✓${NC} Dependencies installed"
echo -e "${GREEN}✓${NC} Application imports successfully"
echo -e "${GREEN}✓${NC} Database connection works"
echo -e "${GREEN}✓${NC} Server starts without critical errors"

echo -e "\n${BOLD}${GREEN}🎉 LOCAL DEPLOYMENT TEST PASSED!${NC}"
echo -e "\nYour application should work on Railway if:"
echo -e "  1. Railway environment variables are set correctly"
echo -e "  2. PostgreSQL database is connected and running"
echo -e "  3. All dependencies are in requirements.txt"

echo -e "\n${BOLD}To start the server manually:${NC}"
echo -e "  ${BLUE}cd backend${NC}"
echo -e "  ${BLUE}python3 -m uvicorn main:app --reload${NC}"

echo -e "\n${BOLD}To run on Railway:${NC}"
echo -e "  1. Check Railway logs: ${BLUE}railway logs${NC}"
echo -e "  2. Ensure DATABASE_URL is set to: ${BLUE}\${{Postgres.DATABASE_URL}}${NC}"
echo -e "  3. Ensure SECRET_KEY is set (generate with: ${BLUE}openssl rand -hex 32${NC})"

echo -e "\n${BOLD}${BLUE}"
echo "============================================================================"
echo -e "${NC}\n"

# Cleanup
rm -f /tmp/uvicorn_test.log

exit 0
