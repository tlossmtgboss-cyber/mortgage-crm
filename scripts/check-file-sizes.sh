#!/bin/bash
# check-file-sizes.sh — Enforce file size limits
# Backend Python files: 500 lines max (excluding tests, migrations, venv, __pycache__, alembic)
# Frontend component files (JS/JSX/TS/TSX): 400 lines max
# Exit 1 if any violations found.

set -euo pipefail

BACKEND_LIMIT=500
FRONTEND_LIMIT=400
violations=0

echo "=== File Size Check ==="
echo ""

# --- Backend Python files ---
echo "Checking backend Python files (limit: ${BACKEND_LIMIT} lines)..."
backend_violations=""

while IFS= read -r file; do
    lines=$(wc -l < "$file" | tr -d ' ')
    if [ "$lines" -gt "$BACKEND_LIMIT" ]; then
        backend_violations="${backend_violations}  ${file} (${lines} lines)\n"
        violations=$((violations + 1))
    fi
done < <(find backend/ -name '*.py' -type f \
    ! -path 'backend/tests/*' \
    ! -path 'backend/migrations/*' \
    ! -path 'backend/alembic/*' \
    ! -path 'backend/.venv/*' \
    ! -path 'backend/venv/*' \
    ! -path '*/__pycache__/*' \
    2>/dev/null || true)

if [ -n "$backend_violations" ]; then
    echo "WARN: Backend files exceeding ${BACKEND_LIMIT} lines:"
    printf "$backend_violations"
    echo ""
else
    echo "  All backend files within limit."
    echo ""
fi

# --- Frontend component files ---
echo "Checking frontend files (limit: ${FRONTEND_LIMIT} lines)..."
frontend_violations=""

while IFS= read -r file; do
    lines=$(wc -l < "$file" | tr -d ' ')
    if [ "$lines" -gt "$FRONTEND_LIMIT" ]; then
        frontend_violations="${frontend_violations}  ${file} (${lines} lines)\n"
        violations=$((violations + 1))
    fi
done < <(find frontend/src/ -type f \( -name '*.js' -o -name '*.jsx' -o -name '*.ts' -o -name '*.tsx' \) \
    ! -path '*/__tests__/*' \
    ! -path '*/test/*' \
    ! -path '*/*.test.*' \
    ! -path '*/*.spec.*' \
    ! -path '*/node_modules/*' \
    2>/dev/null || true)

if [ -n "$frontend_violations" ]; then
    echo "WARN: Frontend files exceeding ${FRONTEND_LIMIT} lines:"
    printf "$frontend_violations"
    echo ""
else
    echo "  All frontend files within limit."
    echo ""
fi

# --- Summary ---
echo "=== Summary ==="
if [ "$violations" -gt 0 ]; then
    echo "Found ${violations} file(s) exceeding size limits."
    echo "See CONTRIBUTING.md for decomposition guidelines."
    exit 1
else
    echo "All files within size limits."
    exit 0
fi
