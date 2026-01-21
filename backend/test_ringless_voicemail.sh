#!/bin/bash

# Test Ringless Voicemail Drop with Slybroadcast
# Usage: ./test_ringless_voicemail.sh

echo "🧪 Testing RINGLESS Voicemail Drop via Slybroadcast"
echo "====================================================="
echo "📱 Target: 843-834-4997"
echo "⚠️  YOUR PHONE SHOULD NOT RING!"
echo ""

# Get authentication token
echo "📝 Logging in..."
TOKEN_RESPONSE=$(curl -s -X POST "https://app.perenniaai.com/token" \
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

# Send ringless voicemail via Slybroadcast
echo "📞 Sending ringless voicemail via Slybroadcast..."
echo "   (Your phone should NOT ring - check voicemail directly in 1-2 minutes)"
echo ""

VOICEMAIL_RESPONSE=$(curl -s -X POST "https://app.perenniaai.com/api/v1/voice/drop-voicemail" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "to_number": "8438344997",
    "message": "This is a test of the ringless voicemail system. Your phone should not have rung. Please check your voicemail to confirm this message was delivered directly.",
    "recipient_name": "Tim",
    "provider": "slybroadcast"
  }')

echo "Response:"
echo $VOICEMAIL_RESPONSE | jq '.'

# Check if successful
SUCCESS=$(echo $VOICEMAIL_RESPONSE | jq -r '.success')
if [ "$SUCCESS" = "true" ]; then
  echo ""
  echo "✅ Ringless voicemail sent successfully!"
  SESSION_ID=$(echo $VOICEMAIL_RESPONSE | jq -r '.session_id')
  PROVIDER=$(echo $VOICEMAIL_RESPONSE | jq -r '.provider')
  echo "📋 Session ID: $SESSION_ID"
  echo "🔧 Provider: $PROVIDER"
  echo ""
  echo "🎉 SUCCESS! Check voicemail on (843) 834-4997 in 1-2 minutes"
  echo "⚠️  If your phone rang, something went wrong - let me know!"
else
  echo ""
  echo "❌ Ringless voicemail failed"
  ERROR=$(echo $VOICEMAIL_RESPONSE | jq -r '.error // .detail')
  echo "Error: $ERROR"
fi

echo ""
echo "====================================================="
