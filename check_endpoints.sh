#!/bin/bash

API_URL="https://api.perenniaai.com"

echo "🔐 Logging in..."
TOKEN_RESPONSE=$(curl -s "$API_URL/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin@perenniaai.com&password=demo123")

TOKEN=$(echo "$TOKEN_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('access_token', ''))" 2>/dev/null)

echo "✅ Logged in"
echo ""

echo "📊 Checking Dashboard..."
curl -s "$API_URL/api/v1/dashboard" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
echo ""

echo "🎯 Checking Leads..."
curl -s "$API_URL/api/v1/leads" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool | head -50
echo ""

echo "💰 Checking Loans..."
curl -s "$API_URL/api/v1/loans" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool | head -50
echo ""
