#!/bin/bash

API_URL="https://mortgage-crm-production-7a9a.up.railway.app"

# Login
echo "🔐 Logging in..."
TOKEN_RESPONSE=$(curl -s "$API_URL/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=demo@example.com&password=demo123")

TOKEN=$(echo "$TOKEN_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('access_token', ''))" 2>/dev/null)

if [ -z "$TOKEN" ]; then
  echo "❌ Login failed"
  exit 1
fi

echo "✅ Logged in"
echo ""

# Test leads endpoint
echo "Testing /api/v1/leads/..."
LEADS_RESPONSE=$(curl -s "$API_URL/api/v1/leads/" -H "Authorization: Bearer $TOKEN")
echo "Response: $LEADS_RESPONSE"
echo ""

# Test loans endpoint
echo "Testing /api/v1/loans/..."
LOANS_RESPONSE=$(curl -s "$API_URL/api/v1/loans/" -H "Authorization: Bearer $TOKEN")
echo "Response: $LOANS_RESPONSE"
echo ""

# Test dashboard
echo "Testing /api/v1/dashboard..."
DASHBOARD_RESPONSE=$(curl -s "$API_URL/api/v1/dashboard" -H "Authorization: Bearer $TOKEN")
echo "Response: ${DASHBOARD_RESPONSE:0:200}"
echo ""

# Check user info
echo "Testing /api/v1/users/me..."
USER_RESPONSE=$(curl -s "$API_URL/api/v1/users/me" -H "Authorization: Bearer $TOKEN")
echo "Response: $USER_RESPONSE" | python3 -m json.tool 2>&1 | head -20
