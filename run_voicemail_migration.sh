#!/bin/bash

echo "🔧 Running Voicemail System Migration"
echo "===================================="
echo ""

# Get authentication token
echo "📝 Logging in..."
TOKEN_RESPONSE=$(curl -s -X POST "https://app.perenniaai.com/token" \
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

# Run migration
echo "🔄 Running voicemail system migration..."
MIGRATION_RESPONSE=$(curl -s -X POST "https://app.perenniaai.com/api/v1/migrations/add-voicemail-system" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json")

echo "Response:"
echo $MIGRATION_RESPONSE | jq '.'

SUCCESS=$(echo $MIGRATION_RESPONSE | jq -r '.success')
if [ "$SUCCESS" = "true" ]; then
  echo ""
  echo "✅ Voicemail system migration completed successfully!"
  echo ""
  echo "Tables created:"
  echo $MIGRATION_RESPONSE | jq -r '.tables_created[]' | sed 's/^/  - /'
  echo ""
  echo "Default templates:"
  echo $MIGRATION_RESPONSE | jq -r '.default_templates[]' | sed 's/^/  - /'
else
  echo ""
  echo "⚠️  Migration response: $(echo $MIGRATION_RESPONSE | jq -r '.message')"
fi

echo ""
echo "===================================="
