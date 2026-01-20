#!/bin/bash

# Phase 3 Permission Filtering Test Script
# Tests that impersonation + permission filtering work together

API_URL="https://api.perenniaai.com"

echo "🧪 Phase 3 Permission Filtering Test"
echo "===================================="
echo ""

# Step 1: Login as demo user (Management role)
echo "Step 1: Login as admin@perenniaai.com (Management role)"
echo "----------------------------------------------------"

LOGIN_RESPONSE=$(curl -s -X POST "$API_URL/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin@perenniaai.com&password=demo123")

MANAGER_TOKEN=$(echo $LOGIN_RESPONSE | jq -r '.access_token')

if [ "$MANAGER_TOKEN" == "null" ] || [ -z "$MANAGER_TOKEN" ]; then
  echo "❌ Login failed for admin@perenniaai.com"
  echo "Response: $LOGIN_RESPONSE"
  exit 1
fi

echo "✅ Login successful as admin@perenniaai.com"
echo ""

# Step 2: Get leads as manager (should see ALL leads)
echo "Step 2: Get leads as manager (should see ALL leads)"
echo "----------------------------------------------------"

MANAGER_LEADS=$(curl -s -X GET "$API_URL/api/v1/leads/" \
  -H "Authorization: Bearer $MANAGER_TOKEN")

MANAGER_LEAD_COUNT=$(echo $MANAGER_LEADS | jq '. | length')

echo "Manager sees $MANAGER_LEAD_COUNT leads"
echo ""

# Step 3: Start impersonation as User 2 (tloss@cmgfi.com - Sales role)
echo "Step 3: Start impersonation as User 2 (Sales role)"
echo "----------------------------------------------------"

IMPERSONATION_RESPONSE=$(curl -s -X POST "$API_URL/api/v1/impersonation/start" \
  -H "Authorization: Bearer $MANAGER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": 2,
    "mode": "full_access",
    "reason": "Testing Phase 3 permission filtering",
    "duration_minutes": 30
  }')

IMPERSONATION_TOKEN=$(echo $IMPERSONATION_RESPONSE | jq -r '.session_token')

if [ "$IMPERSONATION_TOKEN" == "null" ] || [ -z "$IMPERSONATION_TOKEN" ]; then
  echo "❌ Impersonation failed"
  echo "Response: $IMPERSONATION_RESPONSE"
  exit 1
fi

echo "✅ Impersonation started"
echo "Session Token: $IMPERSONATION_TOKEN"
echo ""

# Step 4: Get User 2's permissions to verify they have sales role
echo "Step 4: Verify User 2 has Sales role"
echo "----------------------------------------------------"

USER2_PERMISSIONS=$(curl -s -X GET "$API_URL/api/v1/users/2/permissions" \
  -H "Authorization: Bearer $MANAGER_TOKEN")

USER2_ROLE=$(echo $USER2_PERMISSIONS | jq -r '.permission_role')
USER2_VIEW_ALL=$(echo $USER2_PERMISSIONS | jq -r '.permissions."leads.view_all"')
USER2_VIEW_ASSIGNED=$(echo $USER2_PERMISSIONS | jq -r '.permissions."leads.view_assigned"')

echo "User 2 Role: $USER2_ROLE"
echo "User 2 leads.view_all: $USER2_VIEW_ALL"
echo "User 2 leads.view_assigned: $USER2_VIEW_ASSIGNED"
echo ""

if [ "$USER2_VIEW_ALL" == "true" ]; then
  echo "⚠️  WARNING: Sales user has leads.view_all permission - should be false!"
fi

# Step 5: Get leads while impersonating (should see ONLY assigned leads)
echo "Step 5: Get leads while impersonating User 2 (should see ONLY assigned)"
echo "------------------------------------------------------------------------"

IMPERSONATED_LEADS=$(curl -s -X GET "$API_URL/api/v1/leads/" \
  -H "Authorization: Bearer $MANAGER_TOKEN" \
  -H "X-Impersonation-Token: $IMPERSONATION_TOKEN")

IMPERSONATED_LEAD_COUNT=$(echo $IMPERSONATED_LEADS | jq '. | length')

echo "While impersonating, sees $IMPERSONATED_LEAD_COUNT leads"
echo ""

# Step 6: Compare results
echo "Step 6: Results Comparison"
echo "----------------------------------------------------"
echo ""
echo "📊 RESULTS:"
echo "  Manager (no impersonation): $MANAGER_LEAD_COUNT leads"
echo "  Manager impersonating Sales: $IMPERSONATED_LEAD_COUNT leads"
echo ""

if [ "$IMPERSONATED_LEAD_COUNT" -lt "$MANAGER_LEAD_COUNT" ]; then
  echo "✅ SUCCESS: Permission filtering is working!"
  echo "   The impersonated view shows fewer leads than the manager view."
  echo ""
else
  echo "❌ FAILURE: Permission filtering may not be working"
  echo "   Expected impersonated view to show fewer leads."
  echo ""
fi

# Step 7: Stop impersonation
echo "Step 7: Stop impersonation"
echo "----------------------------------------------------"

STOP_RESPONSE=$(curl -s -X POST "$API_URL/api/v1/impersonation/stop" \
  -H "Authorization: Bearer $MANAGER_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"session_token\": \"$IMPERSONATION_TOKEN\"}")

echo "✅ Impersonation stopped"
echo ""

# Step 8: Verify leads count returns to normal
echo "Step 8: Verify manager view restored"
echo "----------------------------------------------------"

RESTORED_LEADS=$(curl -s -X GET "$API_URL/api/v1/leads/" \
  -H "Authorization: Bearer $MANAGER_TOKEN")

RESTORED_LEAD_COUNT=$(echo $RESTORED_LEADS | jq '. | length')

echo "After stopping impersonation: $RESTORED_LEAD_COUNT leads"
echo ""

if [ "$RESTORED_LEAD_COUNT" -eq "$MANAGER_LEAD_COUNT" ]; then
  echo "✅ SUCCESS: Manager view restored correctly"
else
  echo "⚠️  WARNING: Lead count changed after stopping impersonation"
fi

echo ""
echo "===================================="
echo "Test Complete!"
echo "===================================="
