#!/bin/bash

# Test admin certification job endpoints

API_URL="https://mortgage-crm-production-7a9a.up.railway.app"

echo "🔐 Logging in..."
TOKEN_RESPONSE=$(curl -s "$API_URL/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin@perenniaai.com&password=demo123")

TOKEN=$(echo "$TOKEN_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('access_token', ''))" 2>/dev/null)

if [ -z "$TOKEN" ]; then
  echo "❌ Login failed"
  echo "$TOKEN_RESPONSE"
  exit 1
fi

echo "✅ Login successful"
echo ""

echo "📋 Testing Create Certifications endpoint..."
echo "POST $API_URL/api/v1/admin/certification-jobs/create"
RESULT=$(curl -s -X POST "$API_URL/api/v1/admin/certification-jobs/create" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json")
echo "$RESULT" | python3 -m json.tool
echo ""

echo "📧 Testing Send Reminders endpoint..."
echo "POST $API_URL/api/v1/admin/certification-jobs/reminders"
RESULT=$(curl -s -X POST "$API_URL/api/v1/admin/certification-jobs/reminders" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json")
echo "$RESULT" | python3 -m json.tool
echo ""

echo "✅ Tests complete"
