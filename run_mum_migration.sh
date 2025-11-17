#!/bin/bash

# Script to run MUM client fields migration on Railway

echo "🔑 Getting authentication token..."
TOKEN=$(curl -X POST "https://mortgage-crm-production-7a9a.up.railway.app/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=tloss@cmgfi.com&password=Up2024!" \
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
RESULT=$(curl -X POST "https://mortgage-crm-production-7a9a.up.railway.app/api/v1/migrations/add-mum-client-fields" \
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
