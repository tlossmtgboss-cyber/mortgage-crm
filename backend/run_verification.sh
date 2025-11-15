#!/bin/bash

echo "======================================================================"
echo "  MISSION CONTROL VERIFICATION - Railway Runner"
echo "======================================================================"
echo ""
echo "This script will:"
echo "  1. Link to Railway project (requires interactive selection)"
echo "  2. Run verification script inside Railway environment"
echo ""

# Check if already linked
if railway status &>/dev/null; then
    echo "✅ Already linked to Railway project"
else
    echo "🔗 Linking to Railway project..."
    echo "   Please select: mortgage-crm"
    railway link
fi

echo ""
echo "======================================================================"
echo "  Running verification script..."
echo "======================================================================"
echo ""

# Run verification inside Railway
railway run python verify_mission_control_production.py

echo ""
echo "======================================================================"
echo "  Verification complete!"
echo "======================================================================"
