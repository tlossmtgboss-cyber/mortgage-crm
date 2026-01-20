#!/bin/bash

echo "=========================================="
echo "PROCESS COACH TEST SUITE"
echo "=========================================="
echo ""

# Login and get token
echo "Step 1: Logging in as demo user..."
LOGIN_RESPONSE=$(curl -s -X POST https://api.perenniaai.com/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin@perenniaai.com&password=demo123")

TOKEN=$(echo $LOGIN_RESPONSE | grep -o '"access_token":"[^"]*' | sed 's/"access_token":"//')

if [ -z "$TOKEN" ]; then
  echo "❌ Login failed!"
  echo "Response: $LOGIN_RESPONSE"
  exit 1
fi

echo "✅ Login successful"
echo ""

# Test 1: Daily Briefing
echo "=========================================="
echo "TEST 1: Daily Briefing (Should include CRM data)"
echo "=========================================="

DAILY_BRIEFING_RESPONSE=$(curl -s -X POST https://api.perenniaai.com/api/v1/ai/smart-chat \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Act as a high-performance business coach for mortgage professionals. Give me my top 3 priorities for today based on my current pipeline, leads, and performance metrics. Be direct and actionable. Focus on what will move the needle.",
    "include_context": true,
    "coaching_mode": "daily_briefing",
    "context_type": "coaching"
  }')

echo "Response:"
echo "$DAILY_BRIEFING_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$DAILY_BRIEFING_RESPONSE"
echo ""

# Check if response contains the phrase "I don't have access"
if echo "$DAILY_BRIEFING_RESPONSE" | grep -qi "don't have access"; then
  echo "❌ FAIL: Coach is still asking for data!"
else
  echo "✅ PASS: Coach is not asking for data"
fi

# Check if response contains actual numbers
if echo "$DAILY_BRIEFING_RESPONSE" | grep -qE "[0-9]+ (leads?|loans?|deals?|tasks?)"; then
  echo "✅ PASS: Response contains specific numbers"
else
  echo "⚠️  WARNING: Response may not contain specific metrics"
fi

echo ""

# Test 2: Pipeline Audit
echo "=========================================="
echo "TEST 2: Pipeline Audit (Should identify stuck deals)"
echo "=========================================="

PIPELINE_AUDIT_RESPONSE=$(curl -s -X POST https://api.perenniaai.com/api/v1/ai/smart-chat \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Act as a high-performance business coach. Audit my mortgage pipeline and identify bottlenecks, stalled deals, and areas where I am losing money. Be brutally honest about inefficiencies.",
    "include_context": true,
    "coaching_mode": "pipeline_audit",
    "context_type": "coaching"
  }')

echo "Response:"
echo "$PIPELINE_AUDIT_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$PIPELINE_AUDIT_RESPONSE"
echo ""

# Check for stuck deals mention
if echo "$PIPELINE_AUDIT_RESPONSE" | grep -qi "stuck\|stalled\|bottleneck"; then
  echo "✅ PASS: Response mentions pipeline issues"
else
  echo "⚠️  WARNING: Response may not identify pipeline bottlenecks"
fi

echo ""

# Test 3: Priority Guidance
echo "=========================================="
echo "TEST 3: Priority Guidance (Should use task data)"
echo "=========================================="

PRIORITY_RESPONSE=$(curl -s -X POST https://api.perenniaai.com/api/v1/ai/smart-chat \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Act as a high-performance business coach. Look at my current situation and tell me exactly what I should do next. What is the highest-leverage activity I can do right now?",
    "include_context": true,
    "coaching_mode": "priority_guidance",
    "context_type": "coaching"
  }')

echo "Response:"
echo "$PRIORITY_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$PRIORITY_RESPONSE"
echo ""

# Check for actionable priorities
if echo "$PRIORITY_RESPONSE" | grep -qiE "(first|next|immediately|priority|urgent)"; then
  echo "✅ PASS: Response contains actionable priorities"
else
  echo "⚠️  WARNING: Response may lack specific priorities"
fi

echo ""

# Test 4: Memory Stats
echo "=========================================="
echo "TEST 4: Memory Stats"
echo "=========================================="

MEMORY_STATS=$(curl -s -X GET https://api.perenniaai.com/api/v1/ai/memory-stats \
  -H "Authorization: Bearer $TOKEN")

echo "Memory Stats:"
echo "$MEMORY_STATS" | python3 -m json.tool 2>/dev/null || echo "$MEMORY_STATS"
echo ""

echo "=========================================="
echo "TEST SUMMARY"
echo "=========================================="
echo ""
echo "All tests completed!"
echo "Review the responses above to verify:"
echo "  ✅ Coach provides specific numbers (leads, loans, tasks)"
echo "  ✅ Coach identifies actual stuck deals by name"
echo "  ✅ Coach does NOT ask for data"
echo "  ✅ Coach provides actionable, data-driven guidance"
echo ""
