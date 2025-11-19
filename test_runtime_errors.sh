#!/bin/bash

# Runtime Error Detection Script
# Checks for common React runtime errors and anti-patterns

echo "======================================"
echo "Runtime Error Analysis"
echo "======================================"
echo ""

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

ISSUES_FOUND=0
WARNINGS_FOUND=0

cd /Users/timothyloss/my-project/mortgage-crm/frontend

echo "Checking for common runtime error patterns..."
echo ""

# 1. Check for missing return statements in components
echo "1. Checking for missing return statements in components..."
for file in src/pages/*.js; do
    if [ -f "$file" ]; then
        # Check if function component doesn't have a return
        filename=$(basename "$file")

        # Check for function components without return
        if grep -q "^function\|^export.*function\|^const.*=.*=>.*{" "$file"; then
            if ! grep -q "return" "$file"; then
                echo -e "${YELLOW}Warning: $filename may be missing return statement${NC}"
                ((WARNINGS_FOUND++))
            fi
        fi
    fi
done
echo -e "${GREEN}✓ Return statement check complete${NC}"
echo ""

# 2. Check for incorrect hook usage (hooks inside conditions/loops)
echo "2. Checking for incorrect hook usage..."
HOOK_ISSUES=$(grep -n "if.*useState\|while.*useState\|for.*useState\|if.*useEffect\|while.*useEffect\|for.*useEffect" src/pages/*.js 2>/dev/null | wc -l || echo "0")
if [ "$HOOK_ISSUES" -gt 0 ]; then
    echo -e "${RED}Found $HOOK_ISSUES potential hook rule violations${NC}"
    grep -n "if.*useState\|while.*useState\|for.*useState\|if.*useEffect\|while.*useEffect\|for.*useEffect" src/pages/*.js 2>/dev/null | head -10
    ((ISSUES_FOUND++))
else
    echo -e "${GREEN}✓ No hook rule violations found${NC}"
fi
echo ""

# 3. Check for missing dependency arrays in useEffect
echo "3. Checking for missing useEffect dependencies..."
MISSING_DEPS=$(grep -B2 "useEffect.*=>" src/pages/*.js 2>/dev/null | grep -c "}, );" || echo "0")
if [ "$MISSING_DEPS" -gt 0 ]; then
    echo -e "${YELLOW}Warning: Found $MISSING_DEPS useEffect calls with potentially missing dependencies${NC}"
    ((WARNINGS_FOUND++))
fi
echo -e "${GREEN}✓ Dependency check complete${NC}"
echo ""

# 4. Check for potential null reference errors
echo "4. Checking for potential null reference errors..."
NULL_REFS=0
for file in src/pages/*.js; do
    if [ -f "$file" ]; then
        filename=$(basename "$file")
        # Look for common patterns that might cause null reference errors
        if grep -q "\\.[a-zA-Z]*(" "$file"; then
            # Check if there's optional chaining or null checks
            if ! grep -q "?\\." "$file" && ! grep -q "!= null" "$file" && ! grep -q "!== null" "$file"; then
                # This might be a false positive, so just warn
                NULL_REFS=$((NULL_REFS + 1))
            fi
        fi
    fi
done
if [ "$NULL_REFS" -gt 0 ]; then
    echo -e "${YELLOW}Info: Some files may benefit from optional chaining for safety${NC}"
fi
echo -e "${GREEN}✓ Null reference check complete${NC}"
echo ""

# 5. Check for missing key props in list rendering
echo "5. Checking for missing 'key' props in map functions..."
MISSING_KEYS=0
for file in src/pages/*.js; do
    if [ -f "$file" ]; then
        filename=$(basename "$file")
        # Look for .map( but no key= within the next few lines
        if grep -q "\\.map(" "$file"; then
            # This is a simplified check - would need more sophisticated parsing for accuracy
            maps=$(grep -c "\\.map(" "$file")
            keys=$(grep -c "key=" "$file")
            if [ "$maps" -gt "$keys" ]; then
                echo -e "${YELLOW}Warning: $filename may have map operations missing key props${NC}"
                ((WARNINGS_FOUND++))
                MISSING_KEYS=$((MISSING_KEYS + 1))
            fi
        fi
    fi
done
if [ "$MISSING_KEYS" -eq 0 ]; then
    echo -e "${GREEN}✓ No obvious missing key props${NC}"
fi
echo ""

# 6. Check for state updates in render
echo "6. Checking for state updates during render..."
STATE_IN_RENDER=$(grep -n "setState.*{" src/pages/*.js 2>/dev/null | grep -v "useEffect\|onClick\|onChange\|onSubmit\|callback" | wc -l || echo "0")
if [ "$STATE_IN_RENDER" -gt 0 ]; then
    echo -e "${RED}Warning: Found $STATE_IN_RENDER potential state updates during render${NC}"
    ((WARNINGS_FOUND++))
else
    echo -e "${GREEN}✓ No state updates during render detected${NC}"
fi
echo ""

# 7. Check for async/await error handling
echo "7. Checking for async error handling..."
ASYNC_NO_CATCH=0
for file in src/pages/*.js; do
    if [ -f "$file" ]; then
        filename=$(basename "$file")
        # Count async functions
        async_count=$(grep -c "async.*=>\|async function" "$file" || echo "0")
        # Count try-catch blocks
        catch_count=$(grep -c "catch" "$file" || echo "0")

        if [ "$async_count" -gt 0 ] && [ "$catch_count" -eq 0 ]; then
            echo -e "${YELLOW}Info: $filename has async operations without try-catch${NC}"
            ASYNC_NO_CATCH=$((ASYNC_NO_CATCH + 1))
        fi
    fi
done
echo -e "${GREEN}✓ Async error handling check complete${NC}"
echo ""

# 8. Check for potential memory leaks (missing cleanup in useEffect)
echo "8. Checking for potential memory leaks..."
POTENTIAL_LEAKS=0
for file in src/pages/*.js; do
    if [ -f "$file" ]; then
        filename=$(basename "$file")
        # Check for setInterval or addEventListener without cleanup
        if grep -q "setInterval\|addEventListener" "$file"; then
            if ! grep -q "clearInterval\|removeEventListener\|return.*=>" "$file"; then
                echo -e "${YELLOW}Warning: $filename may have memory leaks (missing cleanup)${NC}"
                ((WARNINGS_FOUND++))
                POTENTIAL_LEAKS=$((POTENTIAL_LEAKS + 1))
            fi
        fi
    fi
done
if [ "$POTENTIAL_LEAKS" -eq 0 ]; then
    echo -e "${GREEN}✓ No obvious memory leaks detected${NC}"
fi
echo ""

# 9. Check for console.log statements (should be removed in production)
echo "9. Checking for console.log statements..."
LOG_COUNT=$(grep -r "console\\.log" src/pages/*.js 2>/dev/null | wc -l || echo "0")
if [ "$LOG_COUNT" -gt 0 ]; then
    echo -e "${YELLOW}Info: Found $LOG_COUNT console.log statements (should remove for production)${NC}"
fi
echo ""

# 10. Check for hardcoded API URLs
echo "10. Checking for hardcoded API URLs..."
HARDCODED_URLS=$(grep -n "http://\|https://" src/pages/*.js 2>/dev/null | grep -v "API_BASE_URL\|process.env" | wc -l || echo "0")
if [ "$HARDCODED_URLS" -gt 0 ]; then
    echo -e "${YELLOW}Warning: Found $HARDCODED_URLS hardcoded URLs${NC}"
    grep -n "http://\|https://" src/pages/*.js 2>/dev/null | grep -v "API_BASE_URL\|process.env" | head -5
    ((WARNINGS_FOUND++))
else
    echo -e "${GREEN}✓ No hardcoded URLs found${NC}"
fi
echo ""

# 11. Check for localStorage usage without error handling
echo "11. Checking for localStorage usage..."
LOCALSTORAGE_COUNT=$(grep -n "localStorage\\." src/pages/*.js 2>/dev/null | wc -l || echo "0")
if [ "$LOCALSTORAGE_COUNT" -gt 0 ]; then
    echo -e "${YELLOW}Info: Found $LOCALSTORAGE_COUNT localStorage operations (ensure error handling)${NC}"
fi
echo ""

# 12. Check for fetch calls without error handling
echo "12. Checking fetch error handling..."
for file in src/pages/*.js; do
    if [ -f "$file" ]; then
        filename=$(basename "$file")
        if grep -q "fetch(" "$file"; then
            if ! grep -q "\\.catch\|try.*catch" "$file"; then
                echo -e "${YELLOW}Warning: $filename has fetch calls without error handling${NC}"
                ((WARNINGS_FOUND++))
            fi
        fi
    fi
done
echo -e "${GREEN}✓ Fetch error handling check complete${NC}"
echo ""

echo "======================================"
echo "SUMMARY"
echo "======================================"
echo ""

if [ $ISSUES_FOUND -eq 0 ]; then
    echo -e "${GREEN}✓ No critical runtime issues detected${NC}"
else
    echo -e "${RED}✗ Found $ISSUES_FOUND critical issue(s)${NC}"
fi

if [ $WARNINGS_FOUND -gt 0 ]; then
    echo -e "${YELLOW}⚠ Found $WARNINGS_FOUND warning(s) - review recommended${NC}"
else
    echo -e "${GREEN}✓ No warnings${NC}"
fi

echo ""
echo "Note: This is a static analysis. Some issues may be false positives."
echo "For complete testing, run the application and check browser console."
echo ""

exit 0
