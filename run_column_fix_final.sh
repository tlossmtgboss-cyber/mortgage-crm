#!/bin/bash

echo "🔧 Voicemail System - Column Fix Migration"
echo "=========================================="
echo ""

# Get authentication token
echo "📝 Authenticating..."
TOKEN_RESPONSE=$(curl -s -X POST "https://mortgage-crm-production-7a9a.up.railway.app/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin@perenniaai.com&password=demo123")

TOKEN=$(echo $TOKEN_RESPONSE | jq -r '.access_token')

if [ "$TOKEN" = "null" ] || [ -z "$TOKEN" ]; then
  echo "❌ Login failed"
  exit 1
fi

echo "✅ Authenticated successfully"
echo ""

# Run column fix migration
echo "🔄 Running column fix migration..."
MIGRATION_RESPONSE=$(curl -s -X POST "https://mortgage-crm-production-7a9a.up.railway.app/api/v1/migrations/fix-voicemail-drops-columns" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json")

echo "$MIGRATION_RESPONSE" | jq '.'

SUCCESS=$(echo $MIGRATION_RESPONSE | jq -r '.success')
if [ "$SUCCESS" = "true" ]; then
  echo ""
  echo "✅ Schema update complete!"
  echo "   All missing columns have been added to voicemail_drops table"
elif [ "$SUCCESS" = "null" ]; then
  echo ""
  echo "⏳ Migration endpoint not yet deployed. Waiting 30 seconds..."
  sleep 30
  # Retry
  echo "🔄 Retrying migration..."
  MIGRATION_RESPONSE=$(curl -s -X POST "https://mortgage-crm-production-7a9a.up.railway.app/api/v1/migrations/fix-voicemail-drops-columns" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json")
  echo "$MIGRATION_RESPONSE" | jq '.'
  SUCCESS=$(echo $MIGRATION_RESPONSE | jq -r '.success')
  if [ "$SUCCESS" = "true" ]; then
    echo ""
    echo "✅ Schema update complete!"
  else
    echo ""
    echo "⚠️  Migration failed: $(echo $MIGRATION_RESPONSE | jq -r '.message')"
  fi
else
  echo ""
  echo "⚠️  Migration failed: $(echo $MIGRATION_RESPONSE | jq -r '.message')"
fi

echo ""
echo "=========================================="
