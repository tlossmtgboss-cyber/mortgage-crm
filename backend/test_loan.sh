#!/bin/bash

# Get token
TOKEN_RESP=$(curl -s -X POST "https://mortgage-crm-production-7a9a.up.railway.app/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=demo@example.com&password=demo123")

TOKEN=$(echo "$TOKEN_RESP" | grep -o '"access_token":"[^"]*"' | cut -d'"' -f4)
echo "Token: ${TOKEN:0:30}..."

# Get loan 90 full response
echo ""
echo "=== Full loan 90 response ==="
curl -s "https://mortgage-crm-production-7a9a.up.railway.app/api/v1/loans/90" \
  -H "Authorization: Bearer $TOKEN"
