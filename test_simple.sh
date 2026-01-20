#!/bin/bash

API_URL="https://api.perenniaai.com"

TOKEN_RESPONSE=$(curl -s "$API_URL/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin@perenniaai.com&password=demo123")

TOKEN=$(echo "$TOKEN_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('access_token', ''))" 2>/dev/null)

echo "Getting leads count..."
curl -s "$API_URL/api/v1/leads/?limit=100" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Accept: application/json" | python3 -c "import sys, json; d=json.load(sys.stdin); print(f'Leads: {len(d)}'); [print(f'  - {l[\"name\"]}: \${l.get(\"loan_amount\", 0):,.0f}') for l in d[:10]]" 2>&1

echo ""
echo "Getting loans count..."
curl -s "$API_URL/api/v1/loans/?limit=100" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Accept: application/json" | python3 -c "import sys, json; d=json.load(sys.stdin); print(f'Loans: {len(d)}'); [print(f'  - {l[\"loan_number\"]}: \${l.get(\"amount\", 0):,.0f}') for l in d[:10]]" 2>&1

echo ""
echo "Getting dashboard..."
curl -s "$API_URL/api/v1/dashboard" \
  -H "Authorization: Bearer $TOKEN" 2>&1 | head -20
