#!/bin/bash

echo "🔧 Fixing Voicemail Schema"
echo "=========================="
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

# Drop old tables and run migration
echo "🗑️  Dropping old voicemail tables..."
RESPONSE=$(curl -s -X POST "https://app.perenniaai.com/api/v1/admin/sql-debug" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "sql": "DROP TABLE IF EXISTS voicemail_events CASCADE; DROP TABLE IF EXISTS voicemail_drops CASCADE; DROP TABLE IF EXISTS voicemail_campaigns CASCADE; DROP TABLE IF EXISTS voicemail_templates CASCADE;"
  }')

echo "$RESPONSE" | jq '.'
echo ""

echo "🔄 Running voicemail system migration..."
MIGRATION_RESPONSE=$(curl -s -X POST "https://app.perenniaai.com/api/v1/migrations/add-voicemail-system" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json")

echo "$MIGRATION_RESPONSE" | jq '.'

SUCCESS=$(echo $MIGRATION_RESPONSE | jq -r '.success')
if [ "$SUCCESS" = "true" ]; then
  echo ""
  echo "✅ Voicemail system migration completed successfully!"
else
  echo ""
  echo "⚠️  Migration failed: $(echo $MIGRATION_RESPONSE | jq -r '.message')"
fi

echo ""
echo "=========================="
