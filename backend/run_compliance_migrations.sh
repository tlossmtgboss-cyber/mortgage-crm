#!/bin/bash

# Run all compliance-related database migrations

set -e  # Exit on error

echo "=================================================="
echo "  Running Compliance System Migrations"
echo "=================================================="
echo ""

# Ensure we're in the backend directory
cd "$(dirname "$0")"

echo "📋 Step 1: Add user compliance columns (account_status, department, full_name)"
python migrations/add_user_compliance_columns.py
echo ""

echo "📋 Step 2: Create access certifications table"
python migrations/add_access_certifications.py
echo ""

echo "✅ All compliance migrations completed successfully!"
echo ""
echo "Next steps:"
echo "  1. Commit the changes to certification_jobs.py"
echo "  2. Deploy to Railway"
echo "  3. Test the endpoints"
