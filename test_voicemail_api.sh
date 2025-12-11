#!/bin/bash

echo "🧪 Testing Voicemail System API"
echo "================================"
echo ""

# Get authentication token
echo "📝 Logging in..."
TOKEN_RESPONSE=$(curl -s -X POST "https://mortgage-crm-production-7a9a.up.railway.app/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin@perenniaai.com&password=demo123")

TOKEN=$(echo $TOKEN_RESPONSE | jq -r '.access_token')

if [ "$TOKEN" = "null" ] || [ -z "$TOKEN" ]; then
  echo "❌ Login failed"
  exit 1
fi

echo "✅ Logged in successfully"
echo ""

# Test 1: Get templates
echo "🔍 Test 1: Get Voicemail Templates"
echo "-----------------------------------"
TEMPLATES_RESPONSE=$(curl -s "https://mortgage-crm-production-7a9a.up.railway.app/api/v1/voicemail/templates" \
  -H "Authorization: Bearer $TOKEN")

echo "$TEMPLATES_RESPONSE" | jq '.'

TEMPLATE_COUNT=$(echo "$TEMPLATES_RESPONSE" | jq -r '.templates | length')
echo ""
echo "✅ Found $TEMPLATE_COUNT templates"
echo ""

# Test 2: Get voicemail history
echo "🔍 Test 2: Get Voicemail History"
echo "-----------------------------------"
HISTORY_RESPONSE=$(curl -s "https://mortgage-crm-production-7a9a.up.railway.app/api/v1/voicemail/history?limit=5" \
  -H "Authorization: Bearer $TOKEN")

echo "$HISTORY_RESPONSE" | jq '.'
echo ""

# Test 3: Get analytics
echo "🔍 Test 3: Get Voicemail Analytics"
echo "-----------------------------------"
ANALYTICS_RESPONSE=$(curl -s "https://mortgage-crm-production-7a9a.up.railway.app/api/v1/voicemail/analytics" \
  -H "Authorization: Bearer $TOKEN")

echo "$ANALYTICS_RESPONSE" | jq '.'
echo ""

echo "================================"
echo "✅ All tests completed!"
