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

echo "================================"
echo "TEST 1: My Permissions Page Fix"
echo "================================"
echo "Testing /api/v1/permissions/available endpoint..."
PERMS=$(curl -s "$API_URL/api/v1/permissions/available" \
  -H "Authorization: Bearer $TOKEN")

if echo "$PERMS" | grep -q '"permissions"'; then
  echo "✅ Permissions endpoint working"
  echo "   - Returns 'permissions' key"
  PERM_COUNT=$(echo "$PERMS" | python3 -c "import sys, json; print(len(json.load(sys.stdin).get('permissions', {})))" 2>/dev/null)
  echo "   - Found $PERM_COUNT permissions"
else
  echo "❌ Permissions endpoint failed"
  echo "$PERMS" | python3 -m json.tool | head -20
fi

echo ""
echo "================================"
echo "TEST 2: Team Member Detail Fix"
echo "================================"
echo "Testing /api/v1/team/members/2 endpoint..."
MEMBER=$(curl -s "$API_URL/api/v1/team/members/2" \
  -H "Authorization: Bearer $TOKEN")

if echo "$MEMBER" | grep -q '"first_name"'; then
  echo "✅ Team member endpoint working"
  echo "   - Returns correct data structure"
  echo "   - Sample data:"
  echo "$MEMBER" | python3 -m json.tool | head -15
else
  echo "❌ Team member endpoint failed"
  echo "$MEMBER" | python3 -m json.tool | head -20
fi

echo ""
echo "================================"
echo "📊 Summary"
echo "================================"
echo "My Permissions Fix: $(echo "$PERMS" | grep -q '"permissions"' && echo '✅ WORKING' || echo '❌ FAILED')"
echo "Team Member Fix: $(echo "$MEMBER" | grep -q '"first_name"' && echo '✅ WORKING' || echo '❌ FAILED')"
echo ""
echo "✅ All tests complete"
