#!/bin/bash
# Run Estimate Parser Cache Migration

API_URL="https://api.perenniaai.com"

echo "🚀 Running estimate parser cache migration..."
echo ""

RESPONSE=$(curl -s -X POST "$API_URL/admin/run-estimate-parser-migration" \
  -H "Content-Type: application/json" \
  -d '{"secret": "migrate-ai-2024"}')

echo "$RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$RESPONSE"
echo ""
echo "✅ Done!"
