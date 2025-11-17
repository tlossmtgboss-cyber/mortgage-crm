#!/bin/bash

API_URL="https://mortgage-crm-production-7a9a.up.railway.app"

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

echo "📋 Testing /api/v1/permissions/available endpoint..."
PERMS_RESPONSE=$(curl -s "$API_URL/api/v1/permissions/available" \
  -H "Authorization: Bearer $TOKEN")

echo "$PERMS_RESPONSE" | python3 -m json.tool | head -30
echo ""

# Check if it contains permissions
if echo "$PERMS_RESPONSE" | grep -q '"permissions"'; then
  echo "✅ Permissions endpoint working - contains 'permissions' key"
else
  echo "❌ Permissions endpoint may have issues"
fi

echo ""
echo "📋 Testing /api/v1/users/1/permissions endpoint..."
USER_PERMS_RESPONSE=$(curl -s "$API_URL/api/v1/users/1/permissions" \
  -H "Authorization: Bearer $TOKEN")

echo "$USER_PERMS_RESPONSE" | python3 -m json.tool | head -20
echo ""

echo "✅ Tests complete"
