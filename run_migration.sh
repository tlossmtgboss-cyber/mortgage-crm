#!/bin/bash

echo "🔧 Running database migration to fix email sync..."
echo ""

# Get your auth token from browser
echo "Please follow these steps:"
echo "1. Open https://mortgage-crm-nine.vercel.app in your browser"
echo "2. Press F12 to open Developer Tools"
echo "3. Go to Console tab"
echo "4. Type: localStorage.getItem('token')"
echo "5. Copy the token (without quotes)"
echo ""
read -p "Paste your token here: " TOKEN

echo ""
echo "Running migration..."

curl -X POST \
  https://api.perenniaai.com/api/v1/migrations/add-external-message-id \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  | python3 -m json.tool

echo ""
echo "✅ Migration complete!"
echo ""
echo "Now test by going to Reconciliation tab and clicking 'Sync Emails Now'"
