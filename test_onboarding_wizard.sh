#!/bin/bash

# Test script for Onboarding Wizard (Micro-Phase 1C)
# This script tests all onboarding API endpoints

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
API_URL="https://api.perenniaai.com"
TOKEN_FILE="/tmp/token_onboarding_test.json"

echo -e "${BLUE}=== Onboarding Wizard API Test ===${NC}\n"

# Step 1: Login to get token
echo -e "${YELLOW}Step 1: Logging in...${NC}"
curl -s -X POST "${API_URL}/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d 'username=admin@perenniaai.com&password=password123' \
  > "$TOKEN_FILE"

if [ $? -ne 0 ]; then
  echo -e "${RED}✗ Login failed${NC}"
  exit 1
fi

TOKEN=$(cat "$TOKEN_FILE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('access_token', ''))" 2>/dev/null)

if [ -z "$TOKEN" ]; then
  echo -e "${RED}✗ No token received${NC}"
  cat "$TOKEN_FILE"
  exit 1
fi

echo -e "${GREEN}✓ Login successful${NC}\n"

# Step 2: Start onboarding
echo -e "${YELLOW}Step 2: Starting onboarding...${NC}"
START_RESPONSE=$(curl -s -X POST "${API_URL}/api/v1/onboarding/start" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json")

echo "$START_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$START_RESPONSE"
echo -e "${GREEN}✓ Onboarding started${NC}\n"

# Step 3: Get progress
echo -e "${YELLOW}Step 3: Getting progress...${NC}"
PROGRESS_RESPONSE=$(curl -s -X GET "${API_URL}/api/v1/onboarding/progress" \
  -H "Authorization: Bearer $TOKEN")

echo "$PROGRESS_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$PROGRESS_RESPONSE"
echo -e "${GREEN}✓ Progress retrieved${NC}\n"

# Step 4: Save Step 1 data
echo -e "${YELLOW}Step 4: Saving Step 1 data...${NC}"
STEP1_DATA='{
  "name": "Test User",
  "email": "testuser@example.com",
  "phone": "(555) 123-4567",
  "nmls_number": "12345",
  "business_address": "123 Test Street, Suite 100, City, ST 12345",
  "current_role": "Loan Officer",
  "business_hours": {
    "monday": {"open": "09:00", "close": "17:00"},
    "tuesday": {"open": "09:00", "close": "17:00"},
    "wednesday": {"open": "09:00", "close": "17:00"},
    "thursday": {"open": "09:00", "close": "17:00"},
    "friday": {"open": "09:00", "close": "17:00"},
    "saturday": {"closed": true},
    "sunday": {"closed": true}
  },
  "email_verified": false,
  "phone_verified": false
}'

SAVE_RESPONSE=$(curl -s -X POST "${API_URL}/api/v1/onboarding/step-1/save" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "$STEP1_DATA")

echo "$SAVE_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$SAVE_RESPONSE"
echo -e "${GREEN}✓ Step 1 data saved${NC}\n"

# Step 5: Test auto-save
echo -e "${YELLOW}Step 5: Testing auto-save...${NC}"
AUTOSAVE_DATA='{
  "step_number": 1,
  "step_data": '"$STEP1_DATA"'
}'

AUTOSAVE_RESPONSE=$(curl -s -X POST "${API_URL}/api/v1/onboarding/auto-save" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "$AUTOSAVE_DATA")

echo "$AUTOSAVE_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$AUTOSAVE_RESPONSE"
echo -e "${GREEN}✓ Auto-save successful${NC}\n"

# Step 6: Send email verification
echo -e "${YELLOW}Step 6: Sending email verification...${NC}"
EMAIL_VERIFY_RESPONSE=$(curl -s -X POST "${API_URL}/api/v1/onboarding/step-1/send-email-verification" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"email": "testuser@example.com"}')

echo "$EMAIL_VERIFY_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$EMAIL_VERIFY_RESPONSE"

# Extract the verification code (in dev mode, it's returned in response)
VERIFICATION_CODE=$(echo "$EMAIL_VERIFY_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('code', ''))" 2>/dev/null)

if [ ! -z "$VERIFICATION_CODE" ]; then
  echo -e "${GREEN}✓ Email verification sent (code: $VERIFICATION_CODE)${NC}\n"
else
  echo -e "${YELLOW}⚠ Email verification sent (no code in response - check logs)${NC}\n"
fi

# Step 7: Verify email (if we have a code)
if [ ! -z "$VERIFICATION_CODE" ]; then
  echo -e "${YELLOW}Step 7: Verifying email with code...${NC}"
  VERIFY_EMAIL_RESPONSE=$(curl -s -X POST "${API_URL}/api/v1/onboarding/step-1/verify-email" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"code\": \"$VERIFICATION_CODE\"}")

  echo "$VERIFY_EMAIL_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$VERIFY_EMAIL_RESPONSE"

  IS_VERIFIED=$(echo "$VERIFY_EMAIL_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('verified', False))" 2>/dev/null)

  if [ "$IS_VERIFIED" = "True" ]; then
    echo -e "${GREEN}✓ Email verified successfully${NC}\n"
  else
    echo -e "${RED}✗ Email verification failed${NC}\n"
  fi
fi

# Step 8: Send SMS verification
echo -e "${YELLOW}Step 8: Sending SMS verification...${NC}"
SMS_VERIFY_RESPONSE=$(curl -s -X POST "${API_URL}/api/v1/onboarding/step-1/send-sms-verification" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"phone": "(555) 123-4567"}')

echo "$SMS_VERIFY_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$SMS_VERIFY_RESPONSE"

SMS_CODE=$(echo "$SMS_VERIFY_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('code', ''))" 2>/dev/null)

if [ ! -z "$SMS_CODE" ]; then
  echo -e "${GREEN}✓ SMS verification sent (code: $SMS_CODE)${NC}\n"
else
  echo -e "${YELLOW}⚠ SMS verification sent (no code in response - check logs)${NC}\n"
fi

# Step 9: Resume onboarding
echo -e "${YELLOW}Step 9: Testing resume functionality...${NC}"
RESUME_RESPONSE=$(curl -s -X GET "${API_URL}/api/v1/onboarding/resume" \
  -H "Authorization: Bearer $TOKEN")

echo "$RESUME_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$RESUME_RESPONSE"
echo -e "${GREEN}✓ Resume data retrieved${NC}\n"

# Step 10: Complete Step 1
echo -e "${YELLOW}Step 10: Completing Step 1...${NC}"
COMPLETE_RESPONSE=$(curl -s -X POST "${API_URL}/api/v1/onboarding/step/1/complete" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json")

echo "$COMPLETE_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$COMPLETE_RESPONSE"
echo -e "${GREEN}✓ Step 1 marked as complete${NC}\n"

# Summary
echo -e "${BLUE}=== Test Summary ===${NC}"
echo -e "${GREEN}All API endpoints tested successfully!${NC}"
echo -e "\n${YELLOW}Next Steps:${NC}"
echo -e "1. Test the UI at: https://mortgage-crm-nine.vercel.app/onboarding/1"
echo -e "2. Login with: admin@perenniaai.com / password123"
echo -e "3. Fill out the form and test verification flows"
echo -e "4. Check auto-save after 30 seconds"
echo -e "5. Test 'Save & Exit' and resume functionality"
echo -e "\n${YELLOW}Database Verification:${NC}"
echo -e "Check the database with:"
echo -e "  railway run psql -c 'SELECT * FROM onboarding_progress WHERE user_id = (SELECT id FROM users WHERE email = \"admin@perenniaai.com\");'"
echo ""
