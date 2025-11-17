#!/bin/bash

API_URL="https://mortgage-crm-production-7a9a.up.railway.app"

echo "🌱 Seeding Demo Data to Production"
echo "===================================="
echo ""

echo "🔐 Logging in..."
TOKEN_RESPONSE=$(curl -s "$API_URL/token" \
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

echo "📊 Seeding demo people..."
curl -s -X POST "$API_URL/api/v1/admin/seed-demo-people" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" | python3 -m json.tool

echo ""
echo "✅ Done!"
