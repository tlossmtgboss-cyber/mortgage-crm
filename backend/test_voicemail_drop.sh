#!/bin/bash

# Test Voicemail Drop Feature
# Usage: ./test_voicemail_drop.sh

echo "🧪 Testing Voicemail Drop to 843-834-4997"
echo "=========================================="
echo ""

# Get authentication token
echo "📝 Logging in..."
TOKEN_RESPONSE=$(curl -s -X POST "https://api.perenniaai.com/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin@perenniaai.com&password=demo123")

TOKEN=$(echo $TOKEN_RESPONSE | jq -r '.access_token')

if [ "$TOKEN" = "null" ] || [ -z "$TOKEN" ]; then
  echo "❌ Login failed. Make sure backend is running and demo user exists."
  echo "Response: $TOKEN_RESPONSE"
  exit 1
fi

echo "✅ Logged in successfully"
echo ""

# Send voicemail drop
echo "📞 Dropping voicemail..."
VOICEMAIL_RESPONSE=$(curl -s -X POST "https://api.perenniaai.com/api/v1/voice/drop-voicemail" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "to_number": "8438344997",
    "message": "This is a test voicemail from the CRM system. Please call me back when you get a chance. Thank you!",
    "recipient_name": "Test User"
  }')

echo "Response:"
echo $VOICEMAIL_RESPONSE | jq '.'

# Check if successful
SUCCESS=$(echo $VOICEMAIL_RESPONSE | jq -r '.success')
if [ "$SUCCESS" = "true" ]; then
  echo ""
  echo "✅ Voicemail drop initiated successfully!"
  CALL_SID=$(echo $VOICEMAIL_RESPONSE | jq -r '.call_sid')
  echo "📞 Call SID: $CALL_SID"
  echo ""
  echo "🎉 Check phone (843) 834-4997 for the voicemail in a few moments!"
else
  echo ""
  echo "❌ Voicemail drop failed"
  ERROR=$(echo $VOICEMAIL_RESPONSE | jq -r '.error // .detail')
  echo "Error: $ERROR"
fi

echo ""
echo "=========================================="
