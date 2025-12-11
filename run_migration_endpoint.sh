#!/bin/bash

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
echo "🔧 Running compliance migrations..."
curl -s -X POST "$API_URL/api/v1/admin/run-compliance-migrations" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" | python3 -m json.tool
echo ""
echo "✅ Done!"
