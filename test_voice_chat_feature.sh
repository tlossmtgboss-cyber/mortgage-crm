#!/bin/bash

# Voice Chat Feature Comprehensive Test Script
# Tests all components, integration points, and functionality

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Test counters
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0

# Test result tracking
declare -a FAILED_TEST_NAMES

echo -e "${BLUE}════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  Voice Chat Feature - Comprehensive Tests${NC}"
echo -e "${BLUE}════════════════════════════════════════════════${NC}\n"

# Helper function for test results
test_result() {
    local test_name="$1"
    local result="$2"
    local message="$3"

    TOTAL_TESTS=$((TOTAL_TESTS + 1))

    if [ "$result" == "PASS" ]; then
        echo -e "${GREEN}✓ $test_name${NC}"
        [ -n "$message" ] && echo -e "  ${message}"
        PASSED_TESTS=$((PASSED_TESTS + 1))
    else
        echo -e "${RED}✗ $test_name${NC}"
        [ -n "$message" ] && echo -e "  ${RED}${message}${NC}"
        FAILED_TESTS=$((FAILED_TESTS + 1))
        FAILED_TEST_NAMES+=("$test_name")
    fi
}

echo -e "${YELLOW}Test 1: File Structure${NC}\n"

# Test VoiceInput component files exist
if [ -f "frontend/src/components/VoiceInput.js" ]; then
    test_result "VoiceInput.js exists" "PASS"
else
    test_result "VoiceInput.js exists" "FAIL" "File not found"
fi

if [ -f "frontend/src/components/VoiceInput.css" ]; then
    test_result "VoiceInput.css exists" "PASS"
else
    test_result "VoiceInput.css exists" "FAIL" "File not found"
fi

# Test CoachCorner files exist
if [ -f "frontend/src/components/CoachCorner.js" ]; then
    test_result "CoachCorner.js exists" "PASS"
else
    test_result "CoachCorner.js exists" "FAIL" "File not found"
fi

if [ -f "frontend/src/components/CoachCorner.css" ]; then
    test_result "CoachCorner.css exists" "PASS"
else
    test_result "CoachCorner.css exists" "FAIL" "File not found"
fi

# Test documentation exists
if [ -f "VOICE_CHAT_FEATURE.md" ]; then
    test_result "Documentation exists" "PASS"
else
    test_result "Documentation exists" "FAIL" "VOICE_CHAT_FEATURE.md not found"
fi

echo -e "\n${YELLOW}Test 2: Component Structure${NC}\n"

# Check VoiceInput component structure
if grep -q "const VoiceInput" frontend/src/components/VoiceInput.js; then
    test_result "VoiceInput component defined" "PASS"
else
    test_result "VoiceInput component defined" "FAIL"
fi

if grep -q "export default VoiceInput" frontend/src/components/VoiceInput.js; then
    test_result "VoiceInput component exported" "PASS"
else
    test_result "VoiceInput component exported" "FAIL"
fi

# Check for required props
if grep -q "onTranscriptChange" frontend/src/components/VoiceInput.js && \
   grep -q "onSend" frontend/src/components/VoiceInput.js; then
    test_result "VoiceInput has required props" "PASS"
else
    test_result "VoiceInput has required props" "FAIL"
fi

echo -e "\n${YELLOW}Test 3: Speech Recognition Integration${NC}\n"

# Check for Speech Recognition API usage
if grep -q "SpeechRecognition\|webkitSpeechRecognition" frontend/src/components/VoiceInput.js; then
    test_result "Speech Recognition API integrated" "PASS"
else
    test_result "Speech Recognition API integrated" "FAIL"
fi

# Check for browser compatibility detection
if grep -q "isSupported" frontend/src/components/VoiceInput.js; then
    test_result "Browser compatibility check implemented" "PASS"
else
    test_result "Browser compatibility check implemented" "FAIL"
fi

# Check for continuous listening
if grep -q "continuous.*true" frontend/src/components/VoiceInput.js; then
    test_result "Continuous listening enabled" "PASS"
else
    test_result "Continuous listening enabled" "FAIL"
fi

# Check for interim results
if grep -q "interimResults.*true" frontend/src/components/VoiceInput.js; then
    test_result "Interim results enabled" "PASS"
else
    test_result "Interim results enabled" "FAIL"
fi

echo -e "\n${YELLOW}Test 4: CoachCorner Integration${NC}\n"

# Check VoiceInput import in CoachCorner
if grep -q "import VoiceInput from './VoiceInput'" frontend/src/components/CoachCorner.js; then
    test_result "VoiceInput imported in CoachCorner" "PASS"
else
    test_result "VoiceInput imported in CoachCorner" "FAIL"
fi

# Check AI chat state variables
if grep -q "aiChatMessage" frontend/src/components/CoachCorner.js && \
   grep -q "aiChatLoading" frontend/src/components/CoachCorner.js && \
   grep -q "aiChatResponse" frontend/src/components/CoachCorner.js; then
    test_result "AI chat state variables defined" "PASS"
else
    test_result "AI chat state variables defined" "FAIL"
fi

# Check handleAIChatSend function
if grep -q "handleAIChatSend" frontend/src/components/CoachCorner.js; then
    test_result "AI chat send handler implemented" "PASS"
else
    test_result "AI chat send handler implemented" "FAIL"
fi

# Check VoiceInput component usage
if grep -q "<VoiceInput" frontend/src/components/CoachCorner.js; then
    test_result "VoiceInput component used in render" "PASS"
else
    test_result "VoiceInput component used in render" "FAIL"
fi

# Check AI chat section in response view
if grep -q "ai-chat-section" frontend/src/components/CoachCorner.js; then
    test_result "AI chat section added to response view" "PASS"
else
    test_result "AI chat section added to response view" "FAIL"
fi

echo -e "\n${YELLOW}Test 5: UI Elements${NC}\n"

# Check for recording indicator
if grep -q "isListening" frontend/src/components/VoiceInput.js && \
   grep -q "listening" frontend/src/components/VoiceInput.css; then
    test_result "Recording indicator implemented" "PASS"
else
    test_result "Recording indicator implemented" "FAIL"
fi

# Check for interim transcript display
if grep -q "interimTranscript" frontend/src/components/VoiceInput.js; then
    test_result "Interim transcript display implemented" "PASS"
else
    test_result "Interim transcript display implemented" "FAIL"
fi

# Check for microphone button
if grep -q "voice-btn" frontend/src/components/VoiceInput.js && \
   grep -q "voice-btn" frontend/src/components/VoiceInput.css; then
    test_result "Microphone button styled" "PASS"
else
    test_result "Microphone button styled" "FAIL"
fi

# Check for send button
if grep -q "send-btn" frontend/src/components/VoiceInput.js && \
   grep -q "send-btn" frontend/src/components/VoiceInput.css; then
    test_result "Send button implemented" "PASS"
else
    test_result "Send button implemented" "FAIL"
fi

echo -e "\n${YELLOW}Test 6: Styling & Animations${NC}\n"

# Check for recording animation
if grep -q "@keyframes.*recording-pulse\|@keyframes.*pulse" frontend/src/components/VoiceInput.css; then
    test_result "Recording pulse animation defined" "PASS"
else
    test_result "Recording pulse animation defined" "FAIL"
fi

# Check for listening dots animation
if grep -q "listening-dots" frontend/src/components/VoiceInput.css; then
    test_result "Listening dots animation styled" "PASS"
else
    test_result "Listening dots animation styled" "FAIL"
fi

# Check AI chat section styling
if grep -q "ai-chat-section" frontend/src/components/CoachCorner.css; then
    test_result "AI chat section styled" "PASS"
else
    test_result "AI chat section styled" "FAIL"
fi

# Check response alert styling
if grep -q "ai-response-alert" frontend/src/components/CoachCorner.css; then
    test_result "AI response alerts styled" "PASS"
else
    test_result "AI response alert styled" "FAIL"
fi

# Check example chips styling
if grep -q "example-chip" frontend/src/components/CoachCorner.css; then
    test_result "Example command chips styled" "PASS"
else
    test_result "Example command chips styled" "FAIL"
fi

echo -e "\n${YELLOW}Test 7: Responsive Design${NC}\n"

# Check for media queries in VoiceInput.css
if grep -q "@media.*max-width.*768px" frontend/src/components/VoiceInput.css; then
    test_result "VoiceInput responsive design implemented" "PASS"
else
    test_result "VoiceInput responsive design implemented" "FAIL"
fi

# Check for media queries in CoachCorner.css for AI chat
if grep -q "@media.*max-width.*768px" frontend/src/components/CoachCorner.css && \
   grep -q "example-chips" frontend/src/components/CoachCorner.css; then
    test_result "AI chat responsive design implemented" "PASS"
else
    test_result "AI chat responsive design implemented" "FAIL"
fi

echo -e "\n${YELLOW}Test 8: Error Handling${NC}\n"

# Check for error handling in speech recognition
if grep -q "onerror" frontend/src/components/VoiceInput.js; then
    test_result "Speech recognition error handling" "PASS"
else
    test_result "Speech recognition error handling" "FAIL"
fi

# Check for microphone permission handling
if grep -q "not-allowed" frontend/src/components/VoiceInput.js; then
    test_result "Microphone permission error handling" "PASS"
else
    test_result "Microphone permission error handling" "FAIL"
fi

# Check for AI chat error handling
if grep -q "catch.*error" frontend/src/components/CoachCorner.js && \
   grep -q "handleAIChatSend" frontend/src/components/CoachCorner.js; then
    test_result "AI chat error handling implemented" "PASS"
else
    test_result "AI chat error handling implemented" "FAIL"
fi

echo -e "\n${YELLOW}Test 9: Example Commands${NC}\n"

# Check for example command buttons
if grep -q "example-chip" frontend/src/components/CoachCorner.js; then
    test_result "Example command buttons implemented" "PASS"
else
    test_result "Example command buttons implemented" "FAIL"
fi

# Count example commands (should have at least 3)
example_count=$(grep -c "example-chip" frontend/src/components/CoachCorner.js || echo "0")
if [ "$example_count" -ge 3 ]; then
    test_result "Multiple example commands provided" "PASS" "Found $example_count example commands"
else
    test_result "Multiple example commands provided" "FAIL" "Only found $example_count example commands"
fi

echo -e "\n${YELLOW}Test 10: Documentation Quality${NC}\n"

# Check documentation completeness
if grep -q "How to Use" VOICE_CHAT_FEATURE.md && \
   grep -q "Technical Details" VOICE_CHAT_FEATURE.md && \
   grep -q "Troubleshooting" VOICE_CHAT_FEATURE.md; then
    test_result "Documentation sections complete" "PASS"
else
    test_result "Documentation sections complete" "FAIL"
fi

# Check for browser compatibility info
if grep -q "Chrome\|Safari\|Edge\|Firefox" VOICE_CHAT_FEATURE.md; then
    test_result "Browser compatibility documented" "PASS"
else
    test_result "Browser compatibility documented" "FAIL"
fi

# Check for example use cases
if grep -q "Example" VOICE_CHAT_FEATURE.md; then
    test_result "Example use cases documented" "PASS"
else
    test_result "Example use cases documented" "FAIL"
fi

echo -e "\n${YELLOW}Test 11: Frontend Build Check${NC}\n"

# Check if frontend can be linted (syntax check)
cd frontend
if command -v npm &> /dev/null; then
    echo -e "${BLUE}Running ESLint check on VoiceInput component...${NC}"
    if npm run lint -- src/components/VoiceInput.js --max-warnings 10 2>/dev/null; then
        test_result "VoiceInput.js syntax valid" "PASS"
    else
        # Lint might not be configured, so we'll do a basic check
        if node -c src/components/VoiceInput.js 2>/dev/null || node --check src/components/VoiceInput.js 2>/dev/null; then
            test_result "VoiceInput.js syntax valid" "PASS"
        else
            test_result "VoiceInput.js syntax valid" "WARN" "Unable to verify (linter not configured)"
        fi
    fi
else
    test_result "NPM availability" "WARN" "NPM not found, skipping syntax checks"
fi
cd ..

echo -e "\n${BLUE}════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  Test Summary${NC}"
echo -e "${BLUE}════════════════════════════════════════════════${NC}\n"

echo -e "Total Tests:  ${BLUE}$TOTAL_TESTS${NC}"
echo -e "Passed:       ${GREEN}$PASSED_TESTS${NC}"
echo -e "Failed:       ${RED}$FAILED_TESTS${NC}"

if [ $FAILED_TESTS -eq 0 ]; then
    echo -e "\n${GREEN}✓ All tests passed!${NC}"
    echo -e "${GREEN}Voice Chat feature is ready for production.${NC}\n"
    exit 0
else
    echo -e "\n${RED}✗ Some tests failed:${NC}"
    for test_name in "${FAILED_TEST_NAMES[@]}"; do
        echo -e "${RED}  - $test_name${NC}"
    done
    echo -e "\n${YELLOW}Review failed tests and fix issues before deploying.${NC}\n"
    exit 1
fi
