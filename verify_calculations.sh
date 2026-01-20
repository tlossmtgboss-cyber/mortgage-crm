#!/bin/bash

API_URL="https://api.perenniaai.com"

echo "🔐 Logging in..."
TOKEN_RESPONSE=$(curl -s "$API_URL/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin@perenniaai.com&password=demo123")

TOKEN=$(echo "$TOKEN_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('access_token', ''))" 2>/dev/null)

echo "✅ Logged in"
echo ""

echo "📊 DASHBOARD METRICS"
echo "===================="
curl -s "$API_URL/api/v1/dashboard" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool | head -40
echo ""

echo "🎯 LEADS"
echo "========"
curl -s "$API_URL/api/v1/leads" \
  -H "Authorization: Bearer $TOKEN" | python3 -c "import sys, json; data=json.load(sys.stdin); print(f'Total: {len(data)}'); [print(f\"  {l['name']}: {l.get('loan_amount', 0):,.0f} @ {l.get('ltv', 0):.1f}% LTV\") for l in data[:5]]"
echo ""

echo "💰 ACTIVE LOANS"
echo "==============="
curl -s "$API_URL/api/v1/loans" \
  -H "Authorization: Bearer $TOKEN" | python3 -c "import sys, json; data=json.load(sys.stdin); print(f'Total: {len(data)}'); [print(f\"  {l['loan_number']}: \${l['amount']:,.0f} - {l['stage']}\") for l in data[:5]]"
echo ""

echo "🏡 MUM CLIENTS"
echo "=============="
curl -s "$API_URL/api/v1/mum-clients" \
  -H "Authorization: Bearer $TOKEN" | python3 -c "import sys, json; data=json.load(sys.stdin); print(f'Total: {len(data)}'); [print(f\"  {m['name']}: Balance \${m.get('loan_balance', 0):,.0f}\") for m in data[:5]]"
echo ""
