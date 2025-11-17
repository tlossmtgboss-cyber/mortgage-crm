#!/bin/bash

echo "=========================================="
echo "CRM CODEBASE SAFETY SCAN"
echo "=========================================="
echo ""

echo "Scanning for potential .map() errors (React #426)..."
echo "=========================================="
echo ""

# Find all .map( calls in pages and components
echo "Files with .map() calls:"
grep -r "\.map(" /Users/timothyloss/my-project/mortgage-crm/frontend/src/pages/*.js \
  /Users/timothyloss/my-project/mortgage-crm/frontend/src/components/*.js 2>/dev/null | \
  cut -d: -f1 | sort | uniq | wc -l

echo ""
echo "Top files with most .map() calls:"
grep -r "\.map(" /Users/timothyloss/my-project/mortgage-crm/frontend/src/pages/*.js \
  /Users/timothyloss/my-project/mortgage-crm/frontend/src/components/*.js 2>/dev/null | \
  cut -d: -f1 | sort | uniq -c | sort -rn | head -10

echo ""
echo "=========================================="
echo "Checking for useState([]) without validation..."
echo "=========================================="
echo ""

# Find useState([]) patterns
grep -r "useState(\[\])" /Users/timothyloss/my-project/mortgage-crm/frontend/src/pages/*.js \
  /Users/timothyloss/my-project/mortgage-crm/frontend/src/components/*.js 2>/dev/null | \
  wc -l
echo "files with useState([]) found"

echo ""
echo "=========================================="
echo "Pages that likely need Array.isArray() safety checks:"
echo "=========================================="
echo ""

# Find pages with both useState([]) and .map()
for file in /Users/timothyloss/my-project/mortgage-crm/frontend/src/pages/*.js; do
  if grep -q "useState(\[\])" "$file" && grep -q "\.map(" "$file"; then
    basename "$file"
  fi
done

echo ""
echo "=========================================="
echo "API service files:"
echo "=========================================="
ls -1 /Users/timothyloss/my-project/mortgage-crm/frontend/src/services/*.js 2>/dev/null | head -15

echo ""
echo "Scan complete!"
