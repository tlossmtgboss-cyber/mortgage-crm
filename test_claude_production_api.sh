#!/bin/bash
# Test Claude integration via Railway production API

BASE_URL="https://app.perenniaai.com"
EMAIL="tloss@cmgfi.com"

echo "================================================================================"
echo "TESTING CLAUDE WITH PRODUCTION API"
echo "================================================================================"

# Get password
read -sp "Enter password for $EMAIL: " PASSWORD
echo ""

# Login
echo ""
echo "1️⃣  Logging in as $EMAIL..."
LOGIN_RESPONSE=$(curl -s -X POST "$BASE_URL/api/v1/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=$EMAIL&password=$PASSWORD")

# Check if login was successful
if echo "$LOGIN_RESPONSE" | grep -q "access_token"; then
  TOKEN=$(echo "$LOGIN_RESPONSE" | grep -o '"access_token":"[^"]*"' | cut -d'"' -f4)
  echo "✅ Login successful! Token: ${TOKEN:0:20}..."
else
  echo "❌ Login failed"
  echo "Response: $LOGIN_RESPONSE"
  exit 1
fi

# Check for unprocessed emails
echo ""
echo "2️⃣  Checking for unprocessed emails..."
REPROCESS_RESPONSE=$(curl -s -X POST "$BASE_URL/api/v1/microsoft/reprocess-emails" \
  -H "Authorization: Bearer $TOKEN")

echo "$REPROCESS_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$REPROCESS_RESPONSE"

if echo "$REPROCESS_RESPONSE" | grep -q '"status":"success"'; then
  REPROCESSED=$(echo "$REPROCESS_RESPONSE" | grep -o '"reprocessed_count":[0-9]*' | cut -d':' -f2)
  TOTAL=$(echo "$REPROCESS_RESPONSE" | grep -o '"total_found":[0-9]*' | cut -d':' -f2)

  echo ""
  echo "✅ Reprocessing complete!"
  echo "   Total found: $TOTAL"
  echo "   Reprocessed: $REPROCESSED"

  if [ "$REPROCESSED" -gt 0 ]; then
    echo ""
    echo "🎉 Claude processed $REPROCESSED emails!"
    echo "   Check logs: railway logs --tail 50 | grep -E 'Claude|🤖'"
  fi
fi

# Trigger email sync
echo ""
echo "3️⃣  Triggering Microsoft 365 email sync..."
SYNC_RESPONSE=$(curl -s -X POST "$BASE_URL/api/v1/microsoft/sync-emails" \
  -H "Authorization: Bearer $TOKEN")

echo "$SYNC_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$SYNC_RESPONSE"

if echo "$SYNC_RESPONSE" | grep -q '"status":"success"'; then
  NEW_COUNT=$(echo "$SYNC_RESPONSE" | grep -o '"new_count":[0-9]*' | cut -d':' -f2)
  echo ""
  echo "✅ Sync complete! New emails: $NEW_COUNT"

  if [ "$NEW_COUNT" -gt 0 ]; then
    echo ""
    echo "🎉 Claude processed $NEW_COUNT new emails!"
  fi
elif echo "$SYNC_RESPONSE" | grep -q "not connected"; then
  echo ""
  echo "⚠️  Microsoft 365 not connected for this account"
  echo "   Please connect in CRM Settings > Integrations"
fi

echo ""
echo "================================================================================"
echo "✅ TEST COMPLETE"
echo "================================================================================"
echo ""
echo "💡 To see Claude in action:"
echo "   1. railway logs --tail 50"
echo "   2. Look for: '🤖 Using Claude parser'"
echo "   3. Or send an email to your connected inbox"
