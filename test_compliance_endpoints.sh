#!/bin/bash

# Test compliance system endpoints in production

API_URL="https://mortgage-crm-production-7a9a.up.railway.app/api/v1"

echo "🔐 Logging in..."
TOKEN_RESPONSE=$(curl -s "https://mortgage-crm-production-7a9a.up.railway.app/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=demo@example.com&password=demo123")

TOKEN=$(echo "$TOKEN_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('access_token', ''))" 2>/dev/null)

if [ -z "$TOKEN" ]; then
  echo "❌ Login failed"
  echo "$TOKEN_RESPONSE"
  exit 1
fi

echo "✅ Login successful"
echo ""

echo "📋 Testing /api/v1/certifications/due endpoint..."
curl -s "$API_URL/certifications/due" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool | head -20
echo ""

echo "📊 Testing /api/v1/compliance/overview endpoint..."
curl -s "$API_URL/compliance/overview" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
echo ""

echo "🏢 Testing /api/v1/compliance/certifications/by-department endpoint..."
curl -s "$API_URL/compliance/certifications/by-department" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
echo ""

echo "✅ All tests complete!"
