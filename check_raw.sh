#!/bin/bash

API_URL="https://app.perenniaai.com"

TOKEN_RESPONSE=$(curl -s "$API_URL/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin@perenniaai.com&password=demo123")

TOKEN=$(echo "$TOKEN_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('access_token', ''))" 2>/dev/null)

echo "=== DASHBOARD RAW ==="
curl -s "$API_URL/api/v1/dashboard" -H "Authorization: Bearer $TOKEN"
echo ""
echo ""

echo "=== LEADS RAW ==="
curl -s "$API_URL/api/v1/leads/" -H "Authorization: Bearer $TOKEN"
echo ""
echo ""

echo "=== LOANS RAW ==="
curl -s "$API_URL/api/v1/loans/" -H "Authorization: Bearer $TOKEN"
echo ""
