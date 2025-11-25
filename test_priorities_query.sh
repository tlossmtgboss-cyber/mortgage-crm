#!/bin/bash

echo "========================================================================"
echo "Testing Daily Focus Priorities Query"
echo "========================================================================"

TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJkZW1vQGV4YW1wbGUuY29tIiwiZXhwIjoxNzY0MDE2OTcxfQ.DvKjpG2FOrpR_g8XHZ1ETk7bEFKRaABHW0D25csrdxA"

echo ""
echo "Step 1: Testing the query_daily_focus_priorities directly..."
echo ""

curl -s "https://mortgage-crm-production-7a9a.up.railway.app/api/v1/query/execute" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query_type": "daily_focus_priorities",
    "params": {}
  }' | python3 -m json.tool

echo ""
echo ""
echo "========================================================================"
echo "Test Complete!"
echo "========================================================================"
echo ""
echo "Review the output above to verify:"
echo "  ✓ Tasks are showing (including those without due dates)"
echo "  ✓ Priority scores are calculated correctly"
echo "  ✓ Urgency labels are present"
echo "  ✓ Loans are included if applicable"
echo ""
