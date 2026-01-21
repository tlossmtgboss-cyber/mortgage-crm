#!/bin/bash

echo "================================="
echo "PRODUCTION DATA CHECK"
echo "================================="
echo ""

# Get a token first
echo "Step 1: Getting auth token..."
LOGIN_RESPONSE=$(curl -s -X POST "https://app.perenniaai.com/api/v1/login" \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@perenniaai.com", "password": "demo123"}')

TOKEN=$(echo "$LOGIN_RESPONSE" | jq -r '.access_token' 2>/dev/null)

if [ -z "$TOKEN" ] || [ "$TOKEN" = "null" ]; then
    echo "❌ Could not get auth token. Trying tloss@cmgfi.com..."

    LOGIN_RESPONSE=$(curl -s -X POST "https://app.perenniaai.com/api/v1/login" \
      -H "Content-Type: application/json" \
      -d '{"email": "tloss@cmgfi.com", "password": "your_password_here"}')

    TOKEN=$(echo "$LOGIN_RESPONSE" | jq -r '.access_token' 2>/dev/null)
fi

if [ -z "$TOKEN" ] || [ "$TOKEN" = "null" ]; then
    echo "❌ Authentication failed. Cannot check users."
    echo "Response: $LOGIN_RESPONSE"
    exit 1
fi

echo "✅ Authenticated successfully"
echo ""

# Check if there's a users endpoint
echo "Step 2: Checking for users endpoint..."
USERS_RESPONSE=$(curl -s -X GET "https://app.perenniaai.com/api/v1/users" \
  -H "Authorization: Bearer $TOKEN" \
  -w "\n%{http_code}")

HTTP_CODE=$(echo "$USERS_RESPONSE" | tail -n1)
USERS_BODY=$(echo "$USERS_RESPONSE" | sed '$d')

if [ "$HTTP_CODE" = "200" ]; then
    echo "✅ Users endpoint accessible"
    echo ""
    echo "Sample users (first 5):"
    echo "$USERS_BODY" | jq '.[:5] | .[] | {id: .id, name: .name, email: .email, role: .role, phone: .phone}' 2>/dev/null || echo "$USERS_BODY"
else
    echo "⚠️  Users endpoint returned HTTP $HTTP_CODE"
    echo "Response: $USERS_BODY"
fi

echo ""
echo "================================="
echo "NEXT STEPS"
echo "================================="
echo ""
echo "Based on the users above, you need to configure:"
echo "1. Production Assistant - user_id, name, phone"
echo "2. Loan Officer - user_id, name, phone"
echo "3. Processor - user_id, name, phone"
echo ""
