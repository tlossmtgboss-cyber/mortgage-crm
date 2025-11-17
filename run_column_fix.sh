#!/bin/bash

echo "🔧 Running Voicemail Columns Fix Migration"
echo "==========================================="
echo ""

# Get authentication token
echo "📝 Logging in..."
TOKEN_RESPONSE=$(curl -s -X POST "https://mortgage-crm-production-7a9a.up.railway.app/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=demo@example.com&password=demo123")

TOKEN=$(echo $TOKEN_RESPONSE | jq -r '.access_token')

if [ "$TOKEN" = "null" ] || [ -z "$TOKEN" ]; then
  echo "❌ Login failed"
  exit 1
fi

echo "✅ Logged in successfully"
echo ""

# Run migration
echo "🔄 Running column fix migration..."
MIGRATION_RESPONSE=$(curl -s -X POST "https://mortgage-crm-production-7a9a.up.railway.app/api/v1/migrations/fix-voicemail-drops-columns" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json")

echo "$MIGRATION_RESPONSE" | jq '.'

SUCCESS=$(echo $MIGRATION_RESPONSE | jq -r '.success')
if [ "$SUCCESS" = "true" ]; then
  echo ""
  echo "✅ Column fix migration completed successfully!"
else
  echo ""
  echo "⚠️  Migration response: $(echo $MIGRATION_RESPONSE | jq -r '.message')"
fi

echo ""
echo "==========================================="
