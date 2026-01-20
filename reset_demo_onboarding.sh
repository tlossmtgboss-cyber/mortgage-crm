#!/bin/bash

echo "🔄 Resetting Demo Account Onboarding"
echo "====================================="
echo ""

# Get authentication token for demo user
echo "📝 Logging in as demo user..."
TOKEN_RESPONSE=$(curl -s -X POST "https://api.perenniaai.com/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin@perenniaai.com&password=demo123")

TOKEN=$(echo $TOKEN_RESPONSE | jq -r '.access_token')

if [ "$TOKEN" = "null" ] || [ -z "$TOKEN" ]; then
  echo "❌ Login failed"
  echo "Response: $TOKEN_RESPONSE"
  exit 1
fi

echo "✅ Logged in successfully"
echo ""

# Reset onboarding
echo "🔄 Resetting onboarding..."
RESET_RESPONSE=$(curl -s -X POST "https://api.perenniaai.com/api/v1/onboarding/reset" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json")

echo "Response:"
echo $RESET_RESPONSE | jq '.'

MESSAGE=$(echo $RESET_RESPONSE | jq -r '.message // .detail')
if [[ "$MESSAGE" == *"successfully"* ]]; then
  echo ""
  echo "✅ Onboarding reset successfully!"
  echo "📱 Next time you log in, the onboarding wizard will appear"
else
  echo ""
  echo "⚠️  Response: $MESSAGE"
fi

echo ""
echo "====================================="
