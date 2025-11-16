#!/bin/bash

# Update Vapi Assistant with Function Calling
# Usage: ./update_vapi_assistant.sh YOUR_VAPI_API_KEY

if [ -z "$1" ]; then
    echo "❌ Error: VAPI_API_KEY required"
    echo ""
    echo "Usage: ./update_vapi_assistant.sh YOUR_VAPI_API_KEY"
    echo ""
    echo "Find your API key at: https://dashboard.vapi.ai/account"
    exit 1
fi

VAPI_API_KEY="$1"
ASSISTANT_ID="120e239e-4d19-4e43-ad92-1f8b07d08c8c"

echo "🚀 Updating Vapi assistant with function calling..."
echo "📋 Assistant ID: $ASSISTANT_ID"
echo ""

response=$(curl -X PATCH "https://api.vapi.ai/assistant/$ASSISTANT_ID" \
  -H "Authorization: Bearer $VAPI_API_KEY" \
  -H "Content-Type: application/json" \
  -d @backend/vapi_assistant_update.json \
  -w "\n%{http_code}" \
  -s)

http_code=$(echo "$response" | tail -n1)
body=$(echo "$response" | sed '$d')

echo "Response:"
echo "$body" | jq '.' 2>/dev/null || echo "$body"
echo ""

if [ "$http_code" -eq 200 ] || [ "$http_code" -eq 201 ]; then
    echo "✅ Success! Assistant updated with 5 function calling endpoints"
    echo ""
    echo "Functions configured:"
    echo "  1. get_lead_info - Lookup existing customers"
    echo "  2. update_lead_status - Update CRM records during calls"
    echo "  3. create_task - Create follow-up tasks"
    echo "  4. schedule_appointment - Schedule meetings"
    echo "  5. get_available_time_slots - Show appointment availability"
    echo ""
    echo "🎉 Your AI receptionist can now update your CRM in real-time!"
    echo ""
    echo "Test it by calling: (832) 648-2297"
else
    echo "❌ Error: HTTP $http_code"
    echo ""
    echo "Troubleshooting:"
    echo "  - Verify your API key is correct"
    echo "  - Check that the assistant ID exists: $ASSISTANT_ID"
    echo "  - Visit https://dashboard.vapi.ai to verify"
fi
