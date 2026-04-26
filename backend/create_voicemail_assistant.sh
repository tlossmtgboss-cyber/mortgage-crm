#!/bin/bash

# Create dedicated voicemail drop assistant
echo "Creating Voicemail Drop Assistant..."

RESPONSE=$(curl -s -X POST "https://api.vapi.ai/assistant" \
  -H "Authorization: Bearer 13af9bfd-8639-4a4a-90d9-fe5fdd8ec886" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Voicemail Drop Only",
    "voice": {
      "provider": "cartesia",
      "voiceId": "b7d50908-b17c-442d-ad8d-810c63997ed9"
    },
    "model": {
      "provider": "openai",
      "model": "gpt-4o",
      "messages": [
        {
          "role": "system",
          "content": "You are a voicemail delivery system. Your ONLY job is to leave voicemail messages. If a human answers the phone, you must IMMEDIATELY end the call by saying nothing. Only speak if you detect a voicemail beep."
        }
      ],
      "temperature": 0.7
    },
    "firstMessage": "{{message}}",
    "voicemailMessage": "{{message}}",
    "endCallMessage": "",
    "transcriber": {
      "provider": "deepgram",
      "model": "nova-2",
      "language": "en"
    },
    "recordingEnabled": true,
    "silenceTimeoutSeconds": 5,
    "maxDurationSeconds": 120,
    "voicemailDetection": {
      "provider": "vapi",
      "beepMaxAwaitSeconds": 25
    }
  }')

echo "Response:"
echo $RESPONSE | jq '.'

ASSISTANT_ID=$(echo $RESPONSE | jq -r '.id')
echo ""
echo "Voicemail Assistant ID: $ASSISTANT_ID"
echo "Add to Railway: VAPI_VOICEMAIL_ASSISTANT_ID=$ASSISTANT_ID"
