#!/bin/bash
# Run Estimate Parser Cache Migration

API_URL="https://mortgage-crm-production-7a9a.up.railway.app"
CRON_API_KEY="crm-gmail-sync-9eaa215d30bd40968e0abe180474f4fc"

echo "🚀 Running estimate_parser_cache migration..."
echo ""

RESPONSE=$(curl -s -X POST "$API_URL/api/v1/admin/run-migration?migration_name=003_estimate_parser_cache" \
  -H "X-API-Key: $CRON_API_KEY" \
  -H "Content-Type: application/json")

echo "$RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$RESPONSE"
echo ""
echo "✅ Done!"
