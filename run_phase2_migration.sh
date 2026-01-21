#!/bin/bash

# Phase 2 Permission System Migration Runner
# This script logs in and runs the migration endpoint

API_URL="https://app.perenniaai.com"

echo "🔐 Logging in to get auth token..."

# Login with admin credentials
LOGIN_RESPONSE=$(curl -s -X POST "$API_URL/api/v1/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=tloss@cmgfi.com&password=your_password_here")

# Extract token
TOKEN=$(echo $LOGIN_RESPONSE | jq -r '.access_token')

if [ "$TOKEN" == "null" ] || [ -z "$TOKEN" ]; then
  echo "❌ Login failed. Please update the script with correct credentials."
  echo "Response: $LOGIN_RESPONSE"
  exit 1
fi

echo "✅ Login successful!"
echo ""
echo "🚀 Running Phase 2 migration..."
echo ""

# Run migration
MIGRATION_RESPONSE=$(curl -s -X POST "$API_URL/api/v1/migrations/run-phase2-permissions" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN")

echo "$MIGRATION_RESPONSE" | jq '.'

echo ""
echo "✅ Migration completed!"
