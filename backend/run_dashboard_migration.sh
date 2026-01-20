#!/bin/bash

echo "🚀 Running AI Receptionist Dashboard Tables Migration..."
echo ""

# Production URL
API_URL="https://api.perenniaai.com"

# Try to get auth token
echo "Step 1: Getting authentication token..."

# Try demo user first
LOGIN_RESPONSE=$(curl -s -X POST "$API_URL/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin@perenniaai.com&password=demo123")

TOKEN=$(echo "$LOGIN_RESPONSE" | jq -r '.access_token' 2>/dev/null)

if [ -z "$TOKEN" ] || [ "$TOKEN" = "null" ]; then
    echo "Demo user failed, trying alternative credentials..."

    # Try with tloss
    LOGIN_RESPONSE=$(curl -s -X POST "$API_URL/token" \
      -H "Content-Type: application/x-www-form-urlencoded" \
      -d "username=tloss@cmgfi.com&password=your_password_here")

    TOKEN=$(echo "$LOGIN_RESPONSE" | jq -r '.access_token' 2>/dev/null)
fi

if [ -z "$TOKEN" ] || [ "$TOKEN" = "null" ]; then
    echo "❌ Could not authenticate automatically"
    echo ""
    echo "Please run manually:"
    echo "  curl -X POST $API_URL/api/v1/migrations/add-ai-receptionist-dashboard-tables \\"
    echo "    -H 'Authorization: Bearer YOUR_TOKEN' \\"
    echo "    -H 'Content-Type: application/json'"
    echo ""
    echo "Get your token from the browser console after logging in"
    exit 1
fi

if [ -z "$TOKEN" ] || [ "$TOKEN" = "null" ]; then
    echo "❌ Authentication failed"
    echo "Response: $LOGIN_RESPONSE"
    exit 1
fi

echo "✅ Authenticated successfully"
echo ""

# Run migration
echo "Step 2: Running migration..."
echo ""

RESPONSE=$(curl -s -X POST "$API_URL/api/v1/migrations/add-ai-receptionist-dashboard-tables" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json")

echo "Response:"
echo "$RESPONSE" | jq '.' 2>/dev/null || echo "$RESPONSE"
echo ""

# Check if successful
SUCCESS=$(echo "$RESPONSE" | jq -r '.success' 2>/dev/null)

if [ "$SUCCESS" = "true" ]; then
    echo "✅ Migration completed successfully!"
    echo ""
    echo "Dashboard tables created:"
    echo "  • ai_receptionist_activity"
    echo "  • ai_receptionist_metrics_daily"
    echo "  • ai_receptionist_skills"
    echo "  • ai_receptionist_errors"
    echo "  • ai_receptionist_system_health"
    echo "  • ai_receptionist_conversations"
    echo ""
    echo "🎉 AI Receptionist Dashboard is now ready!"
else
    echo "⚠️  Migration may have failed or tables already exist"
    echo "Check the response above for details"
fi
