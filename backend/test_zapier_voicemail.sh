#!/bin/bash

# Test Zapier + Slybroadcast Ringless Voicemail
# Usage: ./test_zapier_voicemail.sh

echo "🧪 Testing Zapier + Slybroadcast Ringless Voicemail"
echo "===================================================="
echo "📱 Target: 843-834-4997"
echo "⚠️  YOUR PHONE SHOULD NOT RING!"
echo ""

# Get authentication token
echo "📝 Logging in..."
TOKEN_RESPONSE=$(curl -s -X POST "https://mortgage-crm-production-7a9a.up.railway.app/token" \
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

# Send ringless voicemail via Zapier
echo "📞 Sending ringless voicemail via Zapier..."
echo "   (Zapier will trigger Slybroadcast for ringless delivery)"
echo ""

VOICEMAIL_RESPONSE=$(curl -s -X POST "https://mortgage-crm-production-7a9a.up.railway.app/api/v1/voice/drop-voicemail" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "to_number": "8438344997",
    "message": "This is a test of the Zapier ringless voicemail system. Your phone should not have rung. Please check your voicemail to confirm this message was delivered directly without ringing.",
    "recipient_name": "Tim",
    "provider": "zapier"
  }')

echo "Response:"
echo $VOICEMAIL_RESPONSE | jq '.'

# Check if successful
SUCCESS=$(echo $VOICEMAIL_RESPONSE | jq -r '.success')
if [ "$SUCCESS" = "true" ]; then
  echo ""
  echo "✅ Voicemail sent to Zapier successfully!"
  SESSION_ID=$(echo $VOICEMAIL_RESPONSE | jq -r '.session_id')
  PROVIDER=$(echo $VOICEMAIL_RESPONSE | jq -r '.provider')
  echo "📋 Session ID: $SESSION_ID"
  echo "🔧 Provider: $PROVIDER"
  echo ""
  echo "🎉 Check Zapier task history to see if it triggered"
  echo "📱 Check voicemail on (843) 834-4997 in 1-2 minutes"
  echo "⚠️  If your phone rang, check Zapier Zap configuration"
else
  echo ""
  echo "❌ Failed to send to Zapier"
  ERROR=$(echo $VOICEMAIL_RESPONSE | jq -r '.error // .detail')
  echo "Error: $ERROR"
  echo ""
  if [[ "$ERROR" == *"not configured"* ]]; then
    echo "💡 Next steps:"
    echo "1. Create Zapier Zap (Webhook → Slybroadcast)"
    echo "2. Copy webhook URL from Zapier"
    echo "3. Add to Railway: railway variables --set \"ZAPIER_VOICEMAIL_WEBHOOK_URL=https://hooks.zapier.com/...\""
    echo "4. See ZAPIER_SLYBROADCAST_SETUP.md for detailed instructions"
  fi
fi

echo ""
echo "===================================================="
