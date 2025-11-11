#!/bin/bash
echo "Waiting for Railway deployment..."
sleep 45

echo "Testing Dashboard endpoint..."
curl -s -X POST "https://mortgage-crm-production-7a9a.up.railway.app/token" \
  -d "username=demo@example.com&password=demo123" | \
  python3 -c "import sys, json; data=json.load(sys.stdin); token=data['access_token']; print(f'Token: {token[:20]}...')" 2>/dev/null

echo ""
echo "Testing Dashboard..."
python3 test_all_kpis.py
