#!/bin/bash

# Script to run MUM client fields migration on Railway

# SECURITY: Password must be provided via environment variable
if [ -z "${MIGRATION_USERNAME}" ] || [ -z "${MIGRATION_PASSWORD}" ]; then
  echo "❌ Error: Set MIGRATION_USERNAME and MIGRATION_PASSWORD environment variables"
  echo "Usage: MIGRATION_USERNAME='user@example.com' MIGRATION_PASSWORD='...' ./run_mum_migration.sh"
  exit 1
fi

echo "🔑 Getting authentication token..."
TOKEN=$(curl -X POST "https://app.perenniaai.com/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=${MIGRATION_USERNAME}&password=${MIGRATION_PASSWORD}" \
  -s | jq -r '.access_token')

if [ "$TOKEN" = "null" ] || [ -z "$TOKEN" ]; then
  echo "❌ Failed to get authentication token"
  exit 1
fi

echo "✅ Authentication successful"
echo ""
echo "🔧 Running MUM client fields migration..."
echo ""

# Run the migration
RESULT=$(curl -X POST "https://app.perenniaai.com/api/v1/migrations/add-mum-client-fields" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -s)

echo "$RESULT" | jq '.'

if echo "$RESULT" | jq -e '.success == true' > /dev/null 2>&1; then
  echo ""
  echo "✅ Migration completed successfully!"
  echo ""
  echo "Added columns:"
  echo "$RESULT" | jq -r '.added_columns[]'
else
  echo ""
  echo "❌ Migration failed or columns already exist"
fi
