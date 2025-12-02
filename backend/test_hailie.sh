#!/bin/bash

# Get token
TOKEN_RESP=$(curl -s -X POST "https://mortgage-crm-production-7a9a.up.railway.app/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=demo@example.com&password=demo123")

TOKEN=$(echo "$TOKEN_RESP" | grep -o '"access_token":"[^"]*"' | cut -d'"' -f4)
echo "Token: ${TOKEN:0:30}..."

# Try manual conversion endpoint for loan 92 (Hailie Vachone)
echo ""
echo "=== Manually converting loan 92 to MUM ==="
curl -s -X POST "https://mortgage-crm-production-7a9a.up.railway.app/api/v1/loans/92/convert-to-mum" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json"

echo ""
echo ""
echo "=== Checking MUM clients now ==="
curl -s "https://mortgage-crm-production-7a9a.up.railway.app/api/v1/mum-clients/" \
  -H "Authorization: Bearer $TOKEN"
