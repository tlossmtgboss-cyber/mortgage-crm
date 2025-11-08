#!/bin/bash
# ============================================================================
# Microsoft Integration Update Script
# Updates Microsoft OAuth redirect URIs after Railway deployment is fixed
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
echo "============================================================================"
echo "🔧 Microsoft Integration - Update Redirect URIs"
echo "============================================================================"
echo -e "${NC}"

# Get Railway URL
RAILWAY_URL="https://mortgage-crm-production-7a9a.up.railway.app"

echo -e "${BOLD}Your Railway Backend URL:${NC} $RAILWAY_URL"
echo ""

# ============================================================================
# Step 1: Update Azure AD App Registration
# ============================================================================
echo -e "${BOLD}${BLUE}Step 1: Update Azure AD App Registration${NC}"
echo ""
echo "You need to update your Microsoft Azure AD app registration:"
echo ""
echo "1. Go to: ${BLUE}https://portal.azure.com/#blade/Microsoft_AAD_RegisteredApps${NC}"
echo ""
echo "2. Click on your app registration for the Mortgage CRM"
echo ""
echo "3. Click ${BOLD}'Authentication'${NC} in the left menu"
echo ""
echo "4. Under ${BOLD}'Platform configurations'${NC} → ${BOLD}'Web'${NC}"
echo ""
echo "5. Add this Redirect URI:"
echo -e "   ${GREEN}${RAILWAY_URL}/auth/microsoft/callback${NC}"
echo ""
echo "6. Also ensure these localhost URIs are added for development:"
echo "   http://localhost:8000/auth/microsoft/callback"
echo "   http://localhost:3000/auth/microsoft/callback"
echo ""
echo "7. Click ${BOLD}'Save'${NC}"
echo ""
echo -e "${YELLOW}⚠ Important: Wait 5-10 minutes for changes to propagate${NC}"
echo ""

read -p "Press Enter when you've updated Azure AD..."

# ============================================================================
# Step 2: Update Railway Environment Variables
# ============================================================================
echo -e "\n${BOLD}${BLUE}Step 2: Update Railway Environment Variables${NC}"
echo ""
echo "Go to Railway and update these variables:"
echo ""
echo "1. Go to: ${BLUE}https://railway.app/dashboard${NC}"
echo ""
echo "2. Navigate to: mortgage-crm project → backend service → Variables"
echo ""
echo "3. Add or update these variables:"
echo ""
echo -e "   ${BOLD}MICROSOFT_CLIENT_ID${NC} = <your-azure-ad-client-id>"
echo "   (Found in Azure Portal → App Registration → Overview → Application (client) ID)"
echo ""
echo -e "   ${BOLD}MICROSOFT_CLIENT_SECRET${NC} = <your-azure-ad-client-secret>"
echo "   (Found in Azure Portal → App Registration → Certificates & secrets → Client secrets)"
echo ""
echo -e "   ${BOLD}MICROSOFT_TENANT_ID${NC} = <your-azure-ad-tenant-id>"
echo "   (Found in Azure Portal → App Registration → Overview → Directory (tenant) ID)"
echo ""
echo -e "   ${BOLD}MICROSOFT_REDIRECT_URI${NC} = ${GREEN}${RAILWAY_URL}/auth/microsoft/callback${NC}"
echo ""
echo -e "   ${BOLD}MICROSOFT_FROM_EMAIL${NC} = <your-microsoft-365-email>"
echo "   (The email address that will send emails via Outlook)"
echo ""
echo "4. Click 'Add' for each variable"
echo ""

read -p "Press Enter when you've updated Railway variables..."

# ============================================================================
# Step 3: Update Frontend Environment (if using Vercel)
# ============================================================================
echo -e "\n${BOLD}${BLUE}Step 3: Update Vercel Frontend (Optional)${NC}"
echo ""
echo "If you're using Microsoft authentication in the frontend:"
echo ""
echo "1. Go to: ${BLUE}https://vercel.com/dashboard${NC}"
echo ""
echo "2. Navigate to: mortgage-crm project → Settings → Environment Variables"
echo ""
echo "3. Add these variables (if not already set):"
echo ""
echo -e "   ${BOLD}REACT_APP_MICROSOFT_CLIENT_ID${NC} = <your-azure-ad-client-id>"
echo -e "   ${BOLD}REACT_APP_API_URL${NC} = ${GREEN}${RAILWAY_URL}${NC}"
echo ""
echo "4. Redeploy the frontend to pick up changes"
echo ""

read -p "Press Enter to continue..."

# ============================================================================
# Step 4: Test the Integration
# ============================================================================
echo -e "\n${BOLD}${BLUE}Step 4: Test the Integration${NC}"
echo ""
echo "Test your Microsoft Graph API integration:"
echo ""
echo "1. ${BOLD}Test Backend Health:${NC}"
echo -e "   ${BLUE}curl ${RAILWAY_URL}/health${NC}"
echo ""
echo "2. ${BOLD}Test Microsoft Graph API:${NC}"
echo "   Go to: ${RAILWAY_URL}/docs"
echo "   Find the Microsoft integration endpoints"
echo "   Try sending a test email or Teams message"
echo ""
echo "3. ${BOLD}Check Railway Logs:${NC}"
echo "   railway logs"
echo "   Look for: 'Microsoft Graph API initialized successfully'"
echo ""

# ============================================================================
# Summary
# ============================================================================
echo -e "\n${BOLD}${BLUE}"
echo "============================================================================"
echo "📝 SUMMARY - What You Need"
echo "============================================================================"
echo -e "${NC}"

echo -e "${BOLD}Azure AD App Registration:${NC}"
echo "✓ Redirect URI: ${RAILWAY_URL}/auth/microsoft/callback"
echo "✓ API Permissions:"
echo "  - Mail.Send (for sending emails)"
echo "  - Mail.Read (for reading emails)"
echo "  - Calendars.ReadWrite (for calendar)"
echo "  - Chat.ReadWrite (for Teams messages)"
echo "  - User.Read.All (for user info)"
echo ""

echo -e "${BOLD}Railway Environment Variables:${NC}"
echo "✓ MICROSOFT_CLIENT_ID"
echo "✓ MICROSOFT_CLIENT_SECRET"
echo "✓ MICROSOFT_TENANT_ID"
echo "✓ MICROSOFT_REDIRECT_URI"
echo "✓ MICROSOFT_FROM_EMAIL"
echo ""

echo -e "${BOLD}Features Enabled:${NC}"
echo "✓ Send emails via Outlook"
echo "✓ Read emails from Outlook"
echo "✓ Create calendar events"
echo "✓ Send Teams messages"
echo "✓ OAuth authentication flow"
echo ""

echo -e "${GREEN}${BOLD}✅ Microsoft Integration Setup Complete!${NC}"
echo ""
echo -e "Next steps:"
echo "1. Wait 5-10 minutes for Azure AD changes to propagate"
echo "2. Restart your Railway deployment (or wait for auto-deploy)"
echo "3. Test the integration via ${RAILWAY_URL}/docs"
echo ""

echo -e "${BOLD}${BLUE}"
echo "============================================================================"
echo -e "${NC}\n"
