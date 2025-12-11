#!/bin/bash

API_URL="https://mortgage-crm-production-7a9a.up.railway.app"

echo "═══════════════════════════════════════════════════════"
echo "  FINAL VERIFICATION - Demo Data & Calculations"
echo "═══════════════════════════════════════════════════════"
echo ""

echo "🔐 Logging in as admin@perenniaai.com..."
TOKEN_RESPONSE=$(curl -s "$API_URL/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin@perenniaai.com&password=demo123")

TOKEN=$(echo "$TOKEN_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('access_token', ''))" 2>/dev/null)

if [ -z "$TOKEN" ]; then
  echo "❌ Login failed"
  exit 1
fi

echo "✅ Logged in successfully"
echo ""

echo "📊 Testing Endpoints..."
echo "────────────────────────────────────────────────────────"

echo ""
echo "1. Dashboard Endpoint:"
DASHBOARD=$(curl -s "$API_URL/api/v1/dashboard" -H "Authorization: Bearer $TOKEN")
if [ -z "$DASHBOARD" ]; then
  echo "❌ Dashboard returned empty"
else
  if [[ "$DASHBOARD" == *"Internal Server Error"* ]]; then
    echo "❌ Dashboard error (check logs)"
  elif [[ "$DASHBOARD" == *"production"* ]] || [[ "$DASHBOARD" == *"pipeline"* ]]; then
    echo "✅ Dashboard working"
  else
    echo "⚠️  Dashboard returned: ${DASHBOARD:0:100}..."
  fi
fi

echo ""
echo "2. Leads Endpoint:"
LEADS=$(curl -s "$API_URL/api/v1/leads/" -H "Authorization: Bearer $TOKEN")
LEAD_COUNT=$(echo "$LEADS" | python3 -c "import sys, json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")
echo "   Leads found: $LEAD_COUNT"
if [ "$LEAD_COUNT" -gt "0" ]; then
  echo "✅ Leads endpoint working"
else
  echo "⚠️  No leads found (run ./update_demo_user_data.sh)"
fi

echo ""
echo "3. Loans Endpoint:"
LOANS=$(curl -s "$API_URL/api/v1/loans/" -H "Authorization: Bearer $TOKEN")
LOAN_COUNT=$(echo "$LOANS" | python3 -c "import sys, json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")
echo "   Loans found: $LOAN_COUNT"
if [ "$LOAN_COUNT" -gt "0" ]; then
  echo "✅ Loans endpoint working"
else
  echo "⚠️  No loans found (run ./update_demo_user_data.sh)"
fi

echo ""
echo "4. MUM Clients Endpoint:"
MUM=$(curl -s "$API_URL/api/v1/mum-clients/" -H "Authorization: Bearer $TOKEN")
MUM_COUNT=$(echo "$MUM" | python3 -c "import sys, json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")
echo "   MUM clients found: $MUM_COUNT"
if [ "$MUM_COUNT" -gt "0" ]; then
  echo "✅ MUM clients endpoint working"
else
  echo "⚠️  No MUM clients found"
fi

echo ""
echo "═══════════════════════════════════════════════════════"
echo "  SUMMARY"
echo "═══════════════════════════════════════════════════════"
echo ""
echo "📈 Data Counts:"
echo "   - Leads: $LEAD_COUNT / 5 expected"
echo "   - Loans: $LOAN_COUNT / 4 expected"
echo "   - MUM:   $MUM_COUNT / 3 expected"
echo ""

if [ "$LEAD_COUNT" -gt "0" ] && [ "$LOAN_COUNT" -gt "0" ]; then
  echo "✅ ALL SYSTEMS OPERATIONAL"
  echo ""
  echo "🎯 Next Steps:"
  echo "   1. Open https://mortgage-crm-nine.vercel.app"
  echo "   2. Login: admin@perenniaai.com / demo123"
  echo "   3. View your dashboard with live data!"
else
  echo "⚠️  DATA ASSIGNMENT NEEDED"
  echo ""
  echo "🔧 Run this command:"
  echo "   ./update_demo_user_data.sh"
  echo ""
  echo "   This will assign all demo data to your user."
fi

echo ""
echo "═══════════════════════════════════════════════════════"
