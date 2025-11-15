#!/bin/bash

echo "Testing BOTH Mission Control route prefixes..."
echo ""

BASE_URL="https://mortgage-crm-production-7a9a.up.railway.app"

echo "=== Testing /api/mission-control/* (mission_control_routes.py) ==="
for endpoint in "/summary" "/integrations" "/ai-metrics" "/alerts"; do
  status=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/api/mission-control$endpoint")
  echo "$endpoint -> HTTP $status"
done

echo ""
echo "=== Testing /api/v1/ai/mission-control/* (main.py endpoints) ==="  
for endpoint in "/health" "/metrics" "/actions"; do
  status=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/api/v1/ai/mission-control$endpoint")
  echo "$endpoint -> HTTP $status"
done

echo ""
echo "=== Testing Smart AI Chat ==="
status=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/api/v1/ai/smart-chat")
echo "POST /api/v1/ai/smart-chat -> HTTP $status"
