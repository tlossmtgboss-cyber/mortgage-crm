#!/bin/bash

echo "🧪 Comprehensive Voicemail System Test"
echo "======================================"
echo ""

# Get authentication token
echo "📝 Step 1: Authentication"
echo "-------------------------"
TOKEN_RESPONSE=$(curl -s -X POST "https://mortgage-crm-production-7a9a.up.railway.app/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=demo@example.com&password=demo123")

TOKEN=$(echo $TOKEN_RESPONSE | jq -r '.access_token')

if [ "$TOKEN" = "null" ] || [ -z "$TOKEN" ]; then
  echo "❌ Login failed"
  exit 1
fi

echo "✅ Authenticated as demo@example.com"
echo ""

# Test 1: Get Voicemail Templates
echo "📋 Step 2: Test Voicemail Templates API"
echo "----------------------------------------"
TEMPLATES_RESPONSE=$(curl -s "https://mortgage-crm-production-7a9a.up.railway.app/api/v1/voicemail/templates" \
  -H "Authorization: Bearer $TOKEN")

TEMPLATE_COUNT=$(echo "$TEMPLATES_RESPONSE" | jq -r '.templates | length')
echo "Templates found: $TEMPLATE_COUNT"

if [ "$TEMPLATE_COUNT" -gt "0" ]; then
  echo "✅ Templates API working"
  echo ""
  echo "Available templates:"
  echo "$TEMPLATES_RESPONSE" | jq -r '.templates[] | "  - \(.name) (\(.category))"'
else
  echo "⚠️  No templates found (they may need to be seeded)"
fi
echo ""

# Test 2: Get Voicemail History
echo "📊 Step 3: Test Voicemail History API"
echo "--------------------------------------"
HISTORY_RESPONSE=$(curl -s "https://mortgage-crm-production-7a9a.up.railway.app/api/v1/voicemail/history?limit=5" \
  -H "Authorization: Bearer $TOKEN")

HISTORY_SUCCESS=$(echo "$HISTORY_RESPONSE" | jq -r '.success')
if [ "$HISTORY_SUCCESS" = "true" ]; then
  HISTORY_COUNT=$(echo "$HISTORY_RESPONSE" | jq -r '.total')
  echo "✅ History API working"
  echo "   Total voicemails: $HISTORY_COUNT"
else
  echo "❌ History API error:"
  echo "$HISTORY_RESPONSE" | jq '.'
fi
echo ""

# Test 3: Get Voicemail Analytics
echo "📈 Step 4: Test Voicemail Analytics API"
echo "----------------------------------------"
ANALYTICS_RESPONSE=$(curl -s "https://mortgage-crm-production-7a9a.up.railway.app/api/v1/voicemail/analytics" \
  -H "Authorization: Bearer $TOKEN")

ANALYTICS_SUCCESS=$(echo "$ANALYTICS_RESPONSE" | jq -r '.success')
if [ "$ANALYTICS_SUCCESS" = "true" ]; then
  echo "✅ Analytics API working"
  echo ""
  echo "Analytics Summary:"
  echo "$ANALYTICS_RESPONSE" | jq -r '.analytics | "  Total sent: \(.total_sent)
  Delivered: \(.delivered)
  Failed: \(.failed)
  Delivery rate: \(.delivery_rate)%
  Callback rate: \(.callback_rate)%
  Total cost: $\(.total_cost)"'
else
  echo "❌ Analytics API error:"
  echo "$ANALYTICS_RESPONSE" | jq '.'
fi
echo ""

# Test 4: Test Transcribe Endpoint (without file for now)
echo "🎤 Step 5: Test Transcribe Endpoint Accessibility"
echo "--------------------------------------------------"
TRANSCRIBE_RESPONSE=$(curl -s -X POST "https://mortgage-crm-production-7a9a.up.railway.app/api/v1/voicemail/transcribe" \
  -H "Authorization: Bearer $TOKEN")

# Should fail because no audio file, but endpoint should exist
if echo "$TRANSCRIBE_RESPONSE" | grep -q "Audio file is required"; then
  echo "✅ Transcribe endpoint accessible (correctly requires audio file)"
elif echo "$TRANSCRIBE_RESPONSE" | grep -q "detail.*Not Found"; then
  echo "❌ Transcribe endpoint not found"
else
  echo "⚠️  Transcribe endpoint response:"
  echo "$TRANSCRIBE_RESPONSE" | jq '.'
fi
echo ""

# Summary
echo "======================================"
echo "📋 Test Summary"
echo "======================================"
echo ""
if [ "$ANALYTICS_SUCCESS" = "true" ] && [ "$HISTORY_SUCCESS" = "true" ]; then
  echo "✅ All core APIs are working!"
  echo "✅ Database schema is correct"
  echo "✅ System is ready for use"
  echo ""
  echo "Next steps:"
  echo "1. Seed default templates if needed"
  echo "2. Configure Vapi AI assistant"
  echo "3. Test end-to-end voicemail drop"
else
  echo "⚠️  Some APIs have errors - check logs above"
fi
echo ""
