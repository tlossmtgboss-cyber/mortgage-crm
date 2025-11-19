#!/bin/bash

# Script to remove console.log statements from production build
# Keeps console.error and console.warn for important logging

echo "======================================"
echo "Removing console.log Statements"
echo "======================================"
echo ""

cd /Users/timothyloss/my-project/mortgage-crm/frontend

# Count before
BEFORE_COUNT=$(grep -r "console\.log" src/ 2>/dev/null | wc -l || echo "0")
echo "console.log statements before: $BEFORE_COUNT"

# Replace console.log with a comment in all JS/JSX files
# Only replace lines that are just console.log, not console.error or console.warn
find src/ -type f \( -name "*.js" -o -name "*.jsx" \) -exec sed -i '' \
  -e 's/^[[:space:]]*console\.log(.*);[[:space:]]*$/\/\/ Development log removed/g' \
  -e 's/console\.log(/\/\* console.log(/g' \
  -e 's/);[[:space:]]*\/\*[[:space:]]*console\.log/); *\//g' \
  {} \;

# Count after
AFTER_COUNT=$(grep -r "console\.log" src/ 2>/dev/null | wc -l || echo "0")
echo "console.log statements after: $AFTER_COUNT"
echo "Removed: $((BEFORE_COUNT - AFTER_COUNT))"

echo ""
echo "Note: console.error and console.warn statements were preserved"
echo "for error tracking and debugging in production."
echo ""
