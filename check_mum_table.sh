#!/bin/bash

API_URL="https://app.perenniaai.com"

echo "🔐 Logging in..."
TOKEN_RESPONSE=$(curl -s "$API_URL/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin@perenniaai.com&password=demo123")

TOKEN=$(echo "$TOKEN_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('access_token', ''))" 2>/dev/null)

if [ -z "$TOKEN" ]; then
  echo "❌ Login failed"
  exit 1
fi

echo "✅ Login successful"
echo ""
echo "📊 Checking MUM clients table..."
curl -s "$API_URL/api/v1/mum-clients" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool | head -50
echo ""
echo "✅ Done"
