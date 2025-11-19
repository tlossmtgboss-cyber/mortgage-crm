#!/bin/bash

# Comprehensive CRM Page Testing Script
# Tests all routes and pages for errors

set -e

echo "======================================"
echo "CRM Comprehensive Page Testing"
echo "======================================"
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

ERRORS_FOUND=0
WARNINGS_FOUND=0

# Function to check file syntax
check_file() {
    local file=$1
    local name=$2

    echo -n "Checking $name... "

    # Check if file exists
    if [ ! -f "$file" ]; then
        echo -e "${RED}MISSING${NC}"
        ((ERRORS_FOUND++))
        return 1
    fi

    # Check for syntax errors using node
    if node -c "$file" 2>/dev/null; then
        echo -e "${GREEN}OK${NC}"
        return 0
    else
        echo -e "${RED}SYNTAX ERROR${NC}"
        node -c "$file" 2>&1 | head -5
        ((ERRORS_FOUND++))
        return 1
    fi
}

echo "========================================"
echo "PHASE 1: Build and Compilation Check"
echo "========================================"
echo ""

cd /Users/timothyloss/my-project/mortgage-crm/frontend

# Check if build succeeds
echo "Running production build..."
if npm run build > /tmp/build_output.txt 2>&1; then
    echo -e "${GREEN}✓ Build successful${NC}"
else
    echo -e "${RED}✗ Build failed${NC}"
    echo "Build errors:"
    cat /tmp/build_output.txt | tail -50
    ((ERRORS_FOUND++))
fi

echo ""
echo "========================================"
echo "PHASE 2: Page Component Syntax Check"
echo "========================================"
echo ""

# Check all page components
check_file "src/pages/LandingPage.js" "Landing Page"
check_file "src/pages/Registration.js" "Registration"
check_file "src/pages/EmailVerificationSent.js" "Email Verification Sent"
check_file "src/pages/Login.js" "Login"
check_file "src/pages/Onboarding.js" "Onboarding"
check_file "src/pages/Dashboard.js" "Dashboard"
check_file "src/pages/PipelineEfficiency.js" "Pipeline Efficiency"
check_file "src/pages/Leads.js" "Leads"
check_file "src/pages/LeadDetail.js" "Lead Detail"
check_file "src/pages/Loans.js" "Loans"
check_file "src/pages/LoanDetail.js" "Loan Detail"
check_file "src/pages/Portfolio.js" "Portfolio"
check_file "src/pages/PortfolioDetail.js" "Portfolio Detail"
check_file "src/pages/YearOverYear.js" "Year Over Year"
check_file "src/pages/MumClientDetail.js" "MUM Client Detail"
check_file "src/pages/Tasks.js" "Tasks"
check_file "src/pages/Calendar.js" "Calendar"
check_file "src/pages/Scorecard.js" "Scorecard"
check_file "src/pages/Assistant.js" "Assistant"
check_file "src/pages/AIReceptionistDashboard.js" "AI Receptionist Dashboard"
check_file "src/pages/ClientProfile.js" "Client Profile"
check_file "src/pages/ReferralPartners.js" "Referral Partners"
check_file "src/pages/ReferralPartnerDetail.js" "Referral Partner Detail"
check_file "src/pages/AIUnderwriter.js" "AI Underwriter"
check_file "src/pages/GoalTracker.js" "Goal Tracker"
check_file "src/pages/Coach.js" "Coach"
check_file "src/pages/ReconciliationCenter.js" "Reconciliation Center"
check_file "src/pages/MergeCenter.js" "Merge Center"
check_file "src/pages/Settings.js" "Settings"
check_file "src/pages/TeamMembers.js" "Team Members"
check_file "src/pages/TeamMemberProfile.js" "Team Member Profile"
check_file "src/pages/MyProfile.js" "My Profile"
check_file "src/pages/MyPermissions.js" "My Permissions"
check_file "src/pages/ComplianceDashboard.js" "Compliance Dashboard"
check_file "src/pages/AdminSettings.js" "Admin Settings"
check_file "src/pages/DataUpload.js" "Data Upload"
check_file "src/pages/VerizonTest.js" "Verizon Test"
check_file "src/pages/Users.js" "Users"
check_file "src/pages/UserProfile.js" "User Profile"
check_file "src/pages/ProcessTemplates.js" "Process Templates"
check_file "src/pages/BuyerIntake.js" "Buyer Intake"

echo ""
echo "========================================"
echo "PHASE 3: Component Dependency Check"
echo "========================================"
echo ""

# Check critical components
check_file "src/components/Navigation.js" "Navigation"
check_file "src/components/AIAssistant.js" "AI Assistant"
check_file "src/components/CoachCorner.js" "Coach Corner"
check_file "src/components/OnboardingPrompt.js" "Onboarding Prompt"
check_file "src/components/ImpersonationBanner.js" "Impersonation Banner"
check_file "src/components/ErrorBoundary.js" "Error Boundary"

echo ""
echo "========================================"
echo "PHASE 4: Context Provider Check"
echo "========================================"
echo ""

check_file "src/contexts/ImpersonationContext.js" "Impersonation Context"
check_file "src/contexts/PermissionContext.js" "Permission Context"

echo ""
echo "========================================"
echo "PHASE 5: Routing Configuration Check"
echo "========================================"
echo ""

check_file "src/App.js" "App.js (Main Router)"

# Count routes
ROUTE_COUNT=$(grep -c "path=" src/App.js || true)
echo "Total routes defined: $ROUTE_COUNT"

echo ""
echo "========================================"
echo "PHASE 6: JavaScript/React Error Check"
echo "========================================"
echo ""

# Search for common error patterns in all page files
echo "Scanning for common error patterns..."

# Check for undefined variables
echo -n "Checking for potential undefined variables... "
UNDEFINED_COUNT=$(grep -r "undefined" src/pages/*.js 2>/dev/null | grep -v "!== undefined" | grep -v "=== undefined" | wc -l || echo "0")
if [ "$UNDEFINED_COUNT" -gt 0 ]; then
    echo -e "${YELLOW}$UNDEFINED_COUNT potential issues found${NC}"
    ((WARNINGS_FOUND++))
else
    echo -e "${GREEN}OK${NC}"
fi

# Check for console.error calls
echo -n "Checking for console.error calls... "
ERROR_COUNT=$(grep -r "console.error" src/pages/*.js 2>/dev/null | wc -l || echo "0")
echo "$ERROR_COUNT found (informational)"

# Check for TODO comments
echo -n "Checking for TODO comments... "
TODO_COUNT=$(grep -r "TODO\|FIXME" src/pages/*.js 2>/dev/null | wc -l || echo "0")
echo "$TODO_COUNT found (informational)"

echo ""
echo "========================================"
echo "PHASE 7: Import Statement Check"
echo "========================================"
echo ""

# Check for broken imports
echo "Checking for potential import issues..."
for file in src/pages/*.js; do
    if [ -f "$file" ]; then
        filename=$(basename "$file")
        # Extract imports and check if files exist
        imports=$(grep "^import.*from.*'\.\/" "$file" 2>/dev/null || true)
        if [ ! -z "$imports" ]; then
            while IFS= read -r line; do
                # Extract the path from the import
                path=$(echo "$line" | sed -n "s/.*from '\(.*\)'.*/\1/p")
                if [[ ! "$path" =~ ^\./ ]]; then
                    continue
                fi
                # Convert relative path to actual file path
                dir=$(dirname "$file")
                check_path="$dir/$path"
                if [ ! -f "$check_path.js" ] && [ ! -f "$check_path.jsx" ] && [ ! -f "$check_path/index.js" ]; then
                    echo -e "${YELLOW}Warning: Potential missing import in $filename: $path${NC}"
                    ((WARNINGS_FOUND++))
                fi
            done <<< "$imports"
        fi
    fi
done

echo ""
echo "========================================"
echo "PHASE 8: CSS/Styling Check"
echo "========================================"
echo ""

# Check for missing CSS files
echo "Checking for missing CSS imports..."
CSS_ERRORS=0
for file in src/pages/*.js; do
    if [ -f "$file" ]; then
        filename=$(basename "$file")
        css_imports=$(grep "import.*\.css" "$file" 2>/dev/null || true)
        if [ ! -z "$css_imports" ]; then
            while IFS= read -r line; do
                css_file=$(echo "$line" | sed -n "s/.*['\"]\\(.*\\.css\\)['\"].*/\\1/p")
                if [ ! -z "$css_file" ]; then
                    dir=$(dirname "$file")
                    css_path="$dir/$css_file"
                    if [ ! -f "$css_path" ]; then
                        echo -e "${RED}Missing CSS: $css_file (referenced in $filename)${NC}"
                        ((CSS_ERRORS++))
                        ((ERRORS_FOUND++))
                    fi
                fi
            done <<< "$css_imports"
        fi
    fi
done

if [ $CSS_ERRORS -eq 0 ]; then
    echo -e "${GREEN}All CSS files found${NC}"
fi

echo ""
echo "========================================"
echo "FINAL SUMMARY"
echo "========================================"
echo ""

echo "Total Routes: $ROUTE_COUNT"
echo -e "Build Status: ${GREEN}Checked${NC}"
echo -e "Pages Checked: 39"
echo -e "Components Checked: 6"
echo -e "Contexts Checked: 2"
echo ""

if [ $ERRORS_FOUND -eq 0 ]; then
    echo -e "${GREEN}✓ All pages passed syntax and structure checks!${NC}"
else
    echo -e "${RED}✗ Found $ERRORS_FOUND error(s)${NC}"
fi

if [ $WARNINGS_FOUND -gt 0 ]; then
    echo -e "${YELLOW}⚠ Found $WARNINGS_FOUND warning(s)${NC}"
fi

echo ""
echo "========================================"
echo "ROUTE LIST (for reference)"
echo "========================================"
echo ""
echo "Public Routes:"
echo "  / - Landing Page"
echo "  /apply - Buyer Intake"
echo "  /register - Registration"
echo "  /verify-email-sent - Email Verification"
echo "  /login - Login"
echo ""
echo "Protected Routes:"
echo "  /onboarding - Onboarding"
echo "  /onboarding/:step - Onboarding Wizard"
echo "  /dashboard - Dashboard"
echo "  /dashboard/efficiency - Pipeline Efficiency"
echo "  /leads - Leads List"
echo "  /leads/:id - Lead Detail"
echo "  /loans - Loans List"
echo "  /loans/:id - Loan Detail"
echo "  /portfolio - Portfolio (MUM)"
echo "  /portfolio/detail - Portfolio Detail"
echo "  /portfolio/year-over-year - Year Over Year"
echo "  /portfolio/:id - MUM Client Detail"
echo "  /tasks - Tasks"
echo "  /calendar - Calendar"
echo "  /scorecard - Scorecard"
echo "  /assistant - Assistant"
echo "  /ai-receptionist-dashboard - AI Receptionist"
echo "  /client/:type/:id - Client Profile"
echo "  /referral-partners - Referral Partners"
echo "  /referral-partners/:id - Partner Detail"
echo "  /ai-underwriter - AI Underwriter"
echo "  /goal-tracker - Goal Tracker"
echo "  /coach - Coach"
echo "  /reconciliation - Reconciliation Center"
echo "  /merge - Merge Center"
echo "  /settings - Settings"
echo "  /team-members - Team Members"
echo "  /team-members/:id - Team Member Profile"
echo "  /my-profile - My Profile"
echo "  /my-permissions - My Permissions"
echo "  /compliance - Compliance Dashboard"
echo "  /admin/settings - Admin Settings"
echo "  /data-upload - Data Upload"
echo "  /verizon-test - Verizon Test"
echo "  /users - Users"
echo "  /users/:id - User Profile"
echo "  /team/:userId - User Profile (alt route)"
echo "  /process-templates - Process Templates"
echo ""

exit $ERRORS_FOUND
