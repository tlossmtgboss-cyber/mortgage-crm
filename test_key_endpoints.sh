#!/bin/bash

API_URL="https://mortgage-crm-production-7a9a.up.railway.app"

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

# Test critical endpoints
echo "================================"
echo "Testing Critical API Endpoints"
echo "================================"
echo ""

# 1. Team Members List
echo "1️⃣  Testing /api/v1/team/members (Team Members List)..."
TEAM_LIST=$(curl -s "$API_URL/api/v1/team/members" \
  -H "Authorization: Bearer $TOKEN")

if echo "$TEAM_LIST" | grep -q '"members"'; then
  MEMBER_COUNT=$(echo "$TEAM_LIST" | python3 -c "import sys, json; print(len(json.load(sys.stdin).get('members', [])))" 2>/dev/null)
  echo "   ✅ Team members endpoint working ($MEMBER_COUNT members)"
else
  echo "   ❌ Team members endpoint failed"
  echo "$TEAM_LIST" | python3 -m json.tool | head -10
fi
echo ""

# 2. Compliance Overview
echo "2️⃣  Testing /api/v1/compliance/overview (Compliance Dashboard)..."
COMPLIANCE=$(curl -s "$API_URL/api/v1/compliance/overview" \
  -H "Authorization: Bearer $TOKEN")

if echo "$COMPLIANCE" | grep -q '"users"'; then
  echo "   ✅ Compliance overview endpoint working"
else
  echo "   ❌ Compliance overview endpoint failed"
  echo "$COMPLIANCE" | python3 -m json.tool | head -10
fi
echo ""

# 3. Permission Templates
echo "3️⃣  Testing /api/v1/permissions/templates (Settings)..."
TEMPLATES=$(curl -s "$API_URL/api/v1/permissions/templates" \
  -H "Authorization: Bearer $TOKEN")

if echo "$TEMPLATES" | grep -q '"templates"'; then
  TEMPLATE_COUNT=$(echo "$TEMPLATES" | python3 -c "import sys, json; print(len(json.load(sys.stdin).get('templates', [])))" 2>/dev/null)
  echo "   ✅ Permission templates endpoint working ($TEMPLATE_COUNT templates)"
else
  echo "   ❌ Permission templates endpoint failed"
  echo "$TEMPLATES" | python3 -m json.tool | head -10
fi
echo ""

# 4. Certifications Due
echo "4️⃣  Testing /api/v1/certifications/due..."
CERTS_DUE=$(curl -s "$API_URL/api/v1/certifications/due" \
  -H "Authorization: Bearer $TOKEN")

if echo "$CERTS_DUE" | grep -q '"certifications"'; then
  echo "   ✅ Certifications due endpoint working"
else
  echo "   ❌ Certifications due endpoint failed"
  echo "$CERTS_DUE" | python3 -m json.tool | head -10
fi
echo ""

# 5. Current User
echo "5️⃣  Testing /api/v1/users/me (Current User)..."
CURRENT_USER=$(curl -s "$API_URL/api/v1/users/me" \
  -H "Authorization: Bearer $TOKEN")

if echo "$CURRENT_USER" | grep -q '"email"'; then
  USER_EMAIL=$(echo "$CURRENT_USER" | python3 -c "import sys, json; print(json.load(sys.stdin).get('email', ''))" 2>/dev/null)
  echo "   ✅ Current user endpoint working (${USER_EMAIL})"
else
  echo "   ❌ Current user endpoint failed"
  echo "$CURRENT_USER" | python3 -m json.tool | head -10
fi
echo ""

echo "================================"
echo "📊 Endpoint Test Summary"
echo "================================"
echo "Team Members:        $(echo "$TEAM_LIST" | grep -q '"members"' && echo '✅ OK' || echo '❌ FAIL')"
echo "Compliance Overview: $(echo "$COMPLIANCE" | grep -q '"users"' && echo '✅ OK' || echo '❌ FAIL')"
echo "Permission Templates:$(echo "$TEMPLATES" | grep -q '"templates"' && echo '✅ OK' || echo '❌ FAIL')"
echo "Certifications Due:  $(echo "$CERTS_DUE" | grep -q '"certifications"' && echo '✅ OK' || echo '❌ FAIL')"
echo "Current User:        $(echo "$CURRENT_USER" | grep -q '"email"' && echo '✅ OK' || echo '❌ FAIL')"
echo ""
echo "✅ All tests complete"
