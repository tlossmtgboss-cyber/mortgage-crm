#!/bin/bash

echo "🧪 Testing Voicemail to Phil (925-389-6782)"
echo "============================================"
echo ""

# Get authentication token
echo "📝 Logging in..."
TOKEN_RESPONSE=$(curl -s -X POST "https://app.perenniaai.com/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin@perenniaai.com&password=demo123")

TOKEN=$(echo $TOKEN_RESPONSE | jq -r '.access_token')

if [ "$TOKEN" = "null" ] || [ -z "$TOKEN" ]; then
  echo "❌ Login failed"
  exit 1
fi

echo "✅ Logged in successfully"
echo ""

# Send voicemail to Phil
echo "📞 Calling Phil to ask for callback..."
VOICEMAIL_RESPONSE=$(curl -s -X POST "https://app.perenniaai.com/api/v1/voice/drop-voicemail" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "to_number": "9253896782",
    "message": "Please give us a call back when you get a chance. We need to test the voicemail system. Thank you!",
    "recipient_name": "Phil",
    "provider": "vapi"
  }')

echo "Response:"
echo $VOICEMAIL_RESPONSE | jq '.'

SUCCESS=$(echo $VOICEMAIL_RESPONSE | jq -r '.success')
if [ "$SUCCESS" = "true" ]; then
  echo ""
  echo "✅ Voicemail initiated successfully!"
  echo "📞 Calling Phil now - phone will ring"
else
  echo ""
  echo "❌ Failed"
  ERROR=$(echo $VOICEMAIL_RESPONSE | jq -r '.error // .detail')
  echo "Error: $ERROR"
fi

echo ""
echo "============================================"
