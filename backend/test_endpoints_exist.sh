#!/bin/bash

echo "======================================================================"
echo "  MISSION CONTROL - ENDPOINT VERIFICATION (No Auth Required)"
echo "======================================================================"
echo ""

BASE_URL="https://mortgage-crm-production-7a9a.up.railway.app"

endpoints=(
  "/api/v1/ai/mission-control/health"
  "/api/v1/ai/mission-control/actions"
  "/api/v1/ai/mission-control/metrics"
  "/api/v1/ai/smart-chat"
)

for endpoint in "${endpoints[@]}"; do
  echo "Testing: $endpoint"
  status=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL$endpoint")
  
  if [ "$status" = "401" ]; then
    echo "  ✅ ENDPOINT EXISTS (returns 401 - authentication required)"
  elif [ "$status" = "404" ]; then
    echo "  ❌ ENDPOINT NOT FOUND (404)"
  elif [ "$status" = "200" ]; then
    echo "  ✅ ENDPOINT WORKS (returns 200 - no auth required)"
  else
    echo "  ⚠️  Unexpected status: $status"
  fi
  echo ""
done

echo "======================================================================"
echo "Testing if backend is up..."
status=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/docs")
if [ "$status" = "200" ]; then
  echo "✅ Backend is UP - API docs accessible"
else
  echo "❌ Backend might be DOWN - status: $status"
fi
