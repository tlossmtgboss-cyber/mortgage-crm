#!/bin/bash
# Check demo account emails via production API

BASE_URL="https://app.perenniaai.com"
EMAIL="admin@perenniaai.com"
PASSWORD="demo123"

echo "================================================================================"
echo "CHECKING DEMO ACCOUNT FOR EMAILS TO PROCESS WITH CLAUDE"
echo "================================================================================"

# Login
echo ""
echo "1️⃣  Logging in as admin@perenniaai.com..."
LOGIN_RESPONSE=$(curl -s -X POST "$BASE_URL/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=$EMAIL&password=$PASSWORD")

if echo "$LOGIN_RESPONSE" | grep -q "access_token"; then
  TOKEN=$(echo "$LOGIN_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['access_token'])")
  echo "✅ Logged in successfully"
else
  echo "❌ Login failed"
  echo "$LOGIN_RESPONSE"
  exit 1
fi

# Check for unprocessed emails that can be reprocessed with Claude
echo ""
echo "2️⃣  Checking for unprocessed emails..."
REPROCESS_CHECK=$(curl -s -X POST "$BASE_URL/api/v1/microsoft/reprocess-emails" \
  -H "Authorization: Bearer $TOKEN")

echo "$REPROCESS_CHECK" | python3 -m json.tool 2>/dev/null

TOTAL=$(echo "$REPROCESS_CHECK" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('total_found', 0))" 2>/dev/null)
REPROCESSED=$(echo "$REPROCESS_CHECK" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('reprocessed_count', 0))" 2>/dev/null)

echo ""
echo "================================================================================"
echo "RESULTS"
echo "================================================================================"
echo ""
echo "Unprocessed emails found: $TOTAL"
echo "Emails reprocessed with Claude: $REPROCESSED"

if [ "$REPROCESSED" -gt 0 ]; then
  echo ""
  echo "🎉 SUCCESS! Claude processed $REPROCESSED emails!"
  echo ""
  echo "Check Railway logs to see Claude in action:"
  echo "  railway logs --tail 50 | grep -E '🤖|Claude|demo'"
elif [ "$TOTAL" -eq 0 ]; then
  echo ""
  echo "📭 No unprocessed emails found in demo account"
  echo ""
  echo "💡 To test Claude:"
  echo "  1. Connect Microsoft 365 in Settings > Integrations"
  echo "  2. Send a test email to that inbox"
  echo "  3. Claude will process it automatically"
fi

# Check for Microsoft connection
echo ""
echo "3️⃣  Checking Microsoft 365 connection..."
INTEGRATIONS=$(curl -s -X GET "$BASE_URL/api/v1/integrations/status" \
  -H "Authorization: Bearer $TOKEN" 2>/dev/null)

if echo "$INTEGRATIONS" | grep -q "microsoft"; then
  echo "✅ Microsoft 365 may be connected"
  echo ""
  echo "Trigger email sync:"
  echo "  curl -X POST '$BASE_URL/api/v1/microsoft/sync-emails' -H 'Authorization: Bearer $TOKEN'"
else
  echo "ℹ️  Check integrations in Settings"
fi

echo ""
echo "================================================================================"
echo "DONE"
echo "================================================================================"
