#!/usr/bin/env bash
# compute-stats.sh — Generates overview/data/stats.json from the repo
# Called by GitHub Actions on every push to main, or manually.
set -eu

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
OUT="$REPO_ROOT/overview/data/stats.json"

cd "$REPO_ROOT"

# --- Codebase ---
# Build file list once, reuse for counts
TMPFILE=$(mktemp)
find . -type f \( -name "*.py" -o -name "*.js" -o -name "*.jsx" -o -name "*.ts" -o -name "*.tsx" -o -name "*.html" -o -name "*.css" -o -name "*.sql" -o -name "*.json" \) \
  -not -name "package-lock.json" \
  -not -path "./.venv/*" -not -path "*/node_modules/*" -not -path "./.git/*" \
  -not -path "*/__pycache__/*" -not -path "*/build/*" -not -path "*/dist/*" \
  -not -path "./.next/*" -not -name "*.min.js" -not -name "*.map" \
  > "$TMPFILE" 2>/dev/null || true

# Count LOC using xargs in batches to avoid arg-list-too-long
LOC=$(xargs wc -l < "$TMPFILE" 2>/dev/null | awk '/total$/{s+=$1} END{print s+0}')
if [ -z "$LOC" ] || [ "$LOC" = "0" ]; then
  # Fallback: single total line
  LOC=$(xargs wc -l < "$TMPFILE" 2>/dev/null | tail -1 | awk '{print $1+0}')
fi
LOC=${LOC:-0}

SOURCE_FILES=$(wc -l < "$TMPFILE" | tr -d ' ')
BACKEND_FILES=$(grep -c '\.py$' "$TMPFILE" || echo 0)
FRONTEND_FILES=$(grep -cE '\.(js|jsx|ts|tsx|css)$' "$TMPFILE" || echo 0)
rm -f "$TMPFILE"

# Human-readable LOC display (pure bash, no bc dependency)
if [ "$LOC" -ge 1000000 ]; then
  LOC_MAJOR=$((LOC / 1000000))
  LOC_MINOR=$(( (LOC % 1000000) / 10000 ))
  LOC_DISPLAY="${LOC_MAJOR}.${LOC_MINOR}M"
elif [ "$LOC" -ge 1000 ]; then
  LOC_DISPLAY="$((LOC / 1000))K"
else
  LOC_DISPLAY="$LOC"
fi

# --- Repo ---
TOTAL_COMMITS=$(git rev-list --count HEAD)
FIRST_COMMIT=$(git log --reverse --format="%ad" --date=short | head -1)
LATEST_COMMIT=$(git log -1 --format="%ad" --date=short)
COMMIT_SHA=$(git rev-parse --short HEAD)

# --- Velocity ---
COMMITS_7D=$(git rev-list --count --since="7 days ago" HEAD)
COMMITS_30D=$(git rev-list --count --since="30 days ago" HEAD)

# --- Architecture (curated values, preserved from existing stats.json) ---
if [ -f "$OUT" ]; then
  API_ROUTES=$(python3 -c "import json; print(json.load(open('$OUT'))['architecture']['api_routes'])" 2>/dev/null || echo 140)
  BACKEND_SERVICES=$(python3 -c "import json; print(json.load(open('$OUT'))['architecture']['backend_services'])" 2>/dev/null || echo 177)
  AI_AGENTS=$(python3 -c "import json; print(json.load(open('$OUT'))['architecture']['ai_agents'])" 2>/dev/null || echo 22)
  AI_TOOLS=$(python3 -c "import json; print(json.load(open('$OUT'))['architecture']['ai_tools'])" 2>/dev/null || echo 160)
  FRONTEND_PAGES=$(python3 -c "import json; print(json.load(open('$OUT'))['architecture']['frontend_pages'])" 2>/dev/null || echo 164)
  UI_COMPONENTS=$(python3 -c "import json; print(json.load(open('$OUT'))['architecture']['ui_components'])" 2>/dev/null || echo 250)
  INTEGRATIONS=$(python3 -c "import json; print(json.load(open('$OUT'))['architecture']['integrations'])" 2>/dev/null || echo 27)
  DATA_MODELS=$(python3 -c "import json; print(json.load(open('$OUT'))['architecture']['data_models'])" 2>/dev/null || echo 55)
else
  API_ROUTES=140; BACKEND_SERVICES=177; AI_AGENTS=22; AI_TOOLS=160
  FRONTEND_PAGES=164; UI_COMPONENTS=250; INTEGRATIONS=27; DATA_MODELS=55
fi

GENERATED_AT=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

cat > "$OUT" <<ENDJSON
{
  "codebase": {
    "lines_of_code": $LOC,
    "lines_of_code_display": "$LOC_DISPLAY",
    "source_files": $SOURCE_FILES,
    "backend_files": $BACKEND_FILES,
    "frontend_files": $FRONTEND_FILES
  },
  "repo": {
    "total_commits": $TOTAL_COMMITS,
    "first_commit_date": "$FIRST_COMMIT",
    "latest_commit_date": "$LATEST_COMMIT"
  },
  "architecture": {
    "api_routes": $API_ROUTES,
    "backend_services": $BACKEND_SERVICES,
    "ai_agents": $AI_AGENTS,
    "ai_tools": $AI_TOOLS,
    "frontend_pages": $FRONTEND_PAGES,
    "ui_components": $UI_COMPONENTS,
    "integrations": $INTEGRATIONS,
    "data_models": $DATA_MODELS
  },
  "velocity": {
    "commits_last_7d": $COMMITS_7D,
    "commits_last_30d": $COMMITS_30D
  },
  "generated_at": "$GENERATED_AT",
  "commit_sha": "$COMMIT_SHA"
}
ENDJSON

echo "Stats written to $OUT"
echo "  LOC: $LOC ($LOC_DISPLAY) | Files: $SOURCE_FILES | Commits: $TOTAL_COMMITS | SHA: $COMMIT_SHA"
