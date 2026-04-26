#!/bin/bash

# Update Vapi Assistant with Improved Configuration
# Fixes: background noise handling, phone-only appointments, no double questions

set -e

echo "🚀 Updating VAPI Assistant with improved configuration..."
echo ""

# Use VAPI_API_KEY from environment or Railway
if [ -z "$VAPI_API_KEY" ]; then
    # Try to get from Railway if available
    VAPI_API_KEY=$(railway run printenv VAPI_API_KEY 2>/dev/null || echo "")
fi

ASSISTANT_ID="120e239e-4d19-4e43-ad92-1f8b07d08c8c"

if [ -z "$VAPI_API_KEY" ]; then
    echo "❌ VAPI_API_KEY not found"
    echo ""
    echo "Usage:"
    echo "  export VAPI_API_KEY='your_key_here'"
    echo "  ./update_vapi_assistant_improved.sh"
    echo ""
    echo "Or:"
    echo "  railway run ./update_vapi_assistant_improved.sh"
    exit 1
fi

echo "✅ Found VAPI_API_KEY"
echo "📋 Assistant ID: $ASSISTANT_ID"
echo ""

echo "Improvements in this update:"
echo "  ✅ Enhanced background noise handling (endpointing: 255)"
echo "  ✅ AI can be interrupted with just 2 words"
echo "  ✅ Phone appointments only (no video/in-person mentions)"
echo "  ✅ Stronger 'one question at a time' enforcement"
echo "  ✅ Removed background office noise"
echo ""

# Skip confirmation if AUTO_CONFIRM is set
if [ -z "$AUTO_CONFIRM" ]; then
    read -p "Continue with update? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Update cancelled"
        exit 1
    fi
fi

echo "Updating assistant..."
response=$(curl -X PATCH "https://api.vapi.ai/assistant/$ASSISTANT_ID" \
  -H "Authorization: Bearer $VAPI_API_KEY" \
  -H "Content-Type: application/json" \
  -d @vapi_assistant_with_transfer_v2.json \
  -w "\n%{http_code}" \
  -s)

http_code=$(echo "$response" | tail -n1)
body=$(echo "$response" | sed '$d')

echo ""
echo "Response:"
echo "$body" | jq '.' 2>/dev/null || echo "$body"
echo ""

if [ "$http_code" -eq 200 ] || [ "$http_code" -eq 201 ]; then
    echo "✅ Success! VAPI assistant updated with improvements"
    echo ""
    echo "🎉 Your AI receptionist now has:"
    echo "  • Better background noise handling"
    echo "  • Interruption support (caller can say 'wait' or 'Aria')"
    echo "  • Phone appointments only"
    echo "  • One question at a time enforcement"
    echo ""
    echo "Test by calling: (832) 648-2297"
else
    echo "❌ Error: HTTP $http_code"
    echo ""
    echo "Troubleshooting:"
    echo "  - Verify the API key is correct in Railway"
    echo "  - Check that the assistant ID exists: $ASSISTANT_ID"
    echo "  - Visit https://dashboard.vapi.ai to verify"
fi
