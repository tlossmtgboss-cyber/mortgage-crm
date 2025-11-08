#!/bin/bash
# ============================================================================
# AUTOMATED RAILWAY SETUP SCRIPT
# This script will automatically add all required environment variables
# ============================================================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'
BOLD='\033[1m'

echo -e "${BOLD}${BLUE}"
echo "════════════════════════════════════════════════════════════════"
echo "🚀 AUTOMATED RAILWAY SETUP"
echo "════════════════════════════════════════════════════════════════"
echo -e "${NC}"

# ============================================================================
# Step 1: Check if Railway CLI is installed
# ============================================================================
echo -e "${BOLD}Step 1: Checking Railway CLI...${NC}"

if ! command -v railway &> /dev/null; then
    echo -e "${YELLOW}⚠ Railway CLI not found. Installing now...${NC}\n"

    # Install Railway CLI
    echo "Installing Railway CLI..."
    if command -v npm &> /dev/null; then
        npm install -g @railway/cli
        echo -e "${GREEN}✓ Railway CLI installed!${NC}\n"
    elif command -v brew &> /dev/null; then
        brew install railway
        echo -e "${GREEN}✓ Railway CLI installed!${NC}\n"
    else
        echo -e "${RED}✗ Cannot install Railway CLI automatically.${NC}"
        echo ""
        echo "Please install manually:"
        echo "  Using npm: ${BLUE}npm install -g @railway/cli${NC}"
        echo "  Using brew: ${BLUE}brew install railway${NC}"
        echo ""
        echo "Then run this script again."
        exit 1
    fi
else
    echo -e "${GREEN}✓ Railway CLI is installed${NC}\n"
fi

# ============================================================================
# Step 2: Login to Railway
# ============================================================================
echo -e "${BOLD}Step 2: Logging into Railway...${NC}"
echo "This will open a browser window for authentication."
echo ""

railway login

if [ $? -ne 0 ]; then
    echo -e "${RED}✗ Railway login failed${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Logged into Railway${NC}\n"

# ============================================================================
# Step 3: Link to Project
# ============================================================================
echo -e "${BOLD}Step 3: Linking to your Railway project...${NC}"
echo ""
echo "If you see a list of projects, select 'mortgage-crm' (or your project name)"
echo ""

# Check if already linked
if railway status &> /dev/null; then
    echo -e "${GREEN}✓ Already linked to a project${NC}"
    railway status
else
    echo "Linking to project..."
    railway link

    if [ $? -ne 0 ]; then
        echo -e "${RED}✗ Failed to link project${NC}"
        echo "Please run: ${BLUE}railway link${NC} manually and select your project"
        exit 1
    fi
fi

echo ""

# ============================================================================
# Step 4: Select the Backend Service
# ============================================================================
echo -e "${BOLD}Step 4: Selecting backend service...${NC}"
echo ""
echo "If prompted, select your 'backend' service (NOT the Postgres service)"
echo ""

# Note: Railway CLI should auto-detect or prompt for service selection

# ============================================================================
# Step 5: Add Environment Variables
# ============================================================================
echo -e "${BOLD}Step 5: Adding environment variables...${NC}\n"

# SECRET_KEY
echo -e "Adding ${BOLD}SECRET_KEY${NC}..."
railway variables --set SECRET_KEY=d29e43b5059126da6dda9a061609a329c827a638eb43947cff69f115f4fbdd0a

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ SECRET_KEY added${NC}\n"
else
    echo -e "${RED}✗ Failed to add SECRET_KEY${NC}\n"
fi

# OPENAI_API_KEY (empty for now)
echo -e "Adding ${BOLD}OPENAI_API_KEY${NC}..."
railway variables --set OPENAI_API_KEY=""

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ OPENAI_API_KEY added (empty)${NC}\n"
else
    echo -e "${RED}✗ Failed to add OPENAI_API_KEY${NC}\n"
fi

# ENVIRONMENT
echo -e "Adding ${BOLD}ENVIRONMENT${NC}..."
railway variables --set ENVIRONMENT=production

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ ENVIRONMENT added${NC}\n"
else
    echo -e "${RED}✗ Failed to add ENVIRONMENT${NC}\n"
fi

# ============================================================================
# DATABASE_URL - Special handling
# ============================================================================
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}⚠  DATABASE_URL requires manual setup${NC}"
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo "DATABASE_URL needs to be added as a SERVICE REFERENCE, not a raw value."
echo "The Railway CLI doesn't support this, so you need to do it manually:"
echo ""
echo "1. Go to: ${BLUE}https://railway.app/dashboard${NC}"
echo "2. Click: mortgage-crm → backend → Variables"
echo "3. Click: + New Variable"
echo "4. Click: 'Variable Reference' tab (NOT 'Variable')"
echo "5. Service: Select 'Postgres'"
echo "6. Variable: Select 'DATABASE_URL'"
echo "7. Click: Add"
echo ""
echo -e "${YELLOW}This is the ONE variable you must add manually.${NC}"
echo ""

read -p "Press Enter when you've added DATABASE_URL in the Railway dashboard..."

# ============================================================================
# Step 6: Verify Variables
# ============================================================================
echo ""
echo -e "${BOLD}Step 6: Verifying variables...${NC}\n"

echo "Checking current variables:"
railway variables

echo ""

# ============================================================================
# Step 7: Trigger Redeploy
# ============================================================================
echo -e "${BOLD}Step 7: Triggering deployment...${NC}\n"

echo "Railway should auto-deploy when variables change."
echo "You can also manually trigger a deploy:"
echo ""
echo "  ${BLUE}railway up${NC}"
echo ""

read -p "Do you want to trigger a deployment now? (y/n) " -n 1 -r
echo ""

if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "Deploying..."
    railway up
    echo -e "${GREEN}✓ Deployment triggered${NC}\n"
else
    echo "Skipping deployment. Railway will auto-deploy when it detects variable changes."
fi

# ============================================================================
# Step 8: Check Deployment Status
# ============================================================================
echo ""
echo -e "${BOLD}Step 8: Checking deployment status...${NC}\n"

echo "Getting deployment status..."
railway status

echo ""
echo "To view logs in real-time:"
echo "  ${BLUE}railway logs${NC}"
echo ""

# ============================================================================
# Step 9: Test the Deployment
# ============================================================================
echo -e "${BOLD}Step 9: Testing deployment...${NC}\n"

echo "Waiting 30 seconds for deployment to start..."
sleep 30

echo "Getting your Railway URL..."
RAILWAY_URL=$(railway domain 2>/dev/null || echo "")

if [ -n "$RAILWAY_URL" ]; then
    echo "Your Railway URL: ${BLUE}https://$RAILWAY_URL${NC}"
    echo ""
    echo "Testing health endpoint..."

    sleep 10  # Wait a bit more for app to start

    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "https://$RAILWAY_URL/health" 2>/dev/null || echo "000")

    if [ "$HTTP_CODE" = "200" ]; then
        echo -e "${GREEN}✓ Backend is responding! (HTTP $HTTP_CODE)${NC}"
        echo ""
        curl -s "https://$RAILWAY_URL/health"
        echo ""
    elif [ "$HTTP_CODE" = "502" ]; then
        echo -e "${YELLOW}⚠ Still getting 502 error${NC}"
        echo "The deployment might still be in progress. Wait 2-3 minutes and try:"
        echo "  ${BLUE}curl https://$RAILWAY_URL/health${NC}"
    else
        echo -e "${YELLOW}⚠ Got HTTP $HTTP_CODE${NC}"
        echo "Deployment might still be in progress."
    fi

    echo ""
    echo "API Documentation:"
    echo "  ${BLUE}https://$RAILWAY_URL/docs${NC}"
else
    echo -e "${YELLOW}⚠ Could not detect Railway URL${NC}"
    echo "Check your Railway dashboard for the URL"
fi

# ============================================================================
# Summary
# ============================================================================
echo ""
echo -e "${BOLD}${BLUE}"
echo "════════════════════════════════════════════════════════════════"
echo "📊 SETUP SUMMARY"
echo "════════════════════════════════════════════════════════════════"
echo -e "${NC}"

echo -e "${BOLD}Variables Added via CLI:${NC}"
echo "✓ SECRET_KEY"
echo "✓ OPENAI_API_KEY (empty)"
echo "✓ ENVIRONMENT"
echo ""

echo -e "${BOLD}Manual Setup Required:${NC}"
echo "⚠ DATABASE_URL (must be added as service reference in Railway dashboard)"
echo ""

echo -e "${BOLD}Next Steps:${NC}"
echo "1. Ensure DATABASE_URL is added in Railway dashboard"
echo "2. Wait 3-5 minutes for deployment to complete"
echo "3. Check logs: ${BLUE}railway logs${NC}"
echo "4. Test health endpoint"
echo "5. Test frontend: ${BLUE}https://mortgage-crm-nine.vercel.app${NC}"
echo ""

echo -e "${BOLD}Useful Commands:${NC}"
echo "  ${BLUE}railway logs${NC}                 - View live logs"
echo "  ${BLUE}railway status${NC}               - Check deployment status"
echo "  ${BLUE}railway variables${NC}            - List all variables"
echo "  ${BLUE}railway open${NC}                 - Open Railway dashboard"
echo ""

echo -e "${GREEN}${BOLD}✅ Automated setup complete!${NC}"
echo ""
