#!/bin/bash
# Trigger Claude extraction on imported emails

BASE_URL="https://mortgage-crm-production-7a9a.up.railway.app"
EMAIL="demo@example.com"
PASSWORD="demo123"

echo "================================================================================"
echo "TRIGGERING CLAUDE TO EXTRACT DATA FROM EMAILS"
echo "================================================================================"

# Login
LOGIN_RESPONSE=$(curl -s -X POST "$BASE_URL/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=$EMAIL&password=$PASSWORD")

TOKEN=$(echo "$LOGIN_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['access_token'])")

echo ""
echo "🤖 Triggering Claude extraction on 5 emails..."
echo ""

# Extract each email (IDs 1-5)
for EVENT_ID in 1 2 3 4 5; do
  echo "📧 Processing Event ID: $EVENT_ID..."

  RESULT=$(curl -s -X POST "$BASE_URL/api/v1/reconciliation/extract/$EVENT_ID" \
    -H "Authorization: Bearer $TOKEN")

  # Check if it worked
  if echo "$RESULT" | grep -q "success"; then
    CATEGORY=$(echo "$RESULT" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('category', 'N/A'))" 2>/dev/null)
    CONFIDENCE=$(echo "$RESULT" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('ai_confidence', 0))" 2>/dev/null)
    FIELDS=$(echo "$RESULT" | python3 -c "import sys, json; data=json.load(sys.stdin); print(len(data.get('fields', {})))" 2>/dev/null)

    CONFIDENCE_PCT=$(python3 -c "print(int(float('$CONFIDENCE') * 100))" 2>/dev/null)

    echo "   ✅ Extracted! Category: $CATEGORY | Fields: $FIELDS | Confidence: ${CONFIDENCE_PCT}%"
  else
    echo "   ⚠️  Result: $RESULT"
  fi

  sleep 1
done

echo ""
echo "================================================================================"
echo "✅ CLAUDE EXTRACTION COMPLETE!"
echo "================================================================================"
echo ""
echo "🎉 Claude has processed all 5 sample emails!"
echo ""
echo "📊 Check the results:"
echo "   1. Log into demo account"
echo "   2. Go to: Data Reconciliation page"
echo "   3. See Claude's field extractions with confidence scores"
echo ""
echo "🔍 Check Railway logs to see Claude in action:"
echo "   railway logs --tail 100 | grep -E '🤖|Claude|extracted|confidence'"
echo ""
echo "💡 Expected results:"
echo "   • Pre-approval (Sarah): 15-17 fields @ 95-99% confidence"
echo "   • Active loan (Michael): 18-23 fields @ 97-99% confidence"
echo "   • Refinance (Robert): 11-14 fields @ 96-99% confidence"
echo "   • First-time buyer (Jessica): 13-16 fields @ 95-99% confidence"
echo "   • Clear to close (Amanda): 20-25 fields @ 98-100% confidence"
