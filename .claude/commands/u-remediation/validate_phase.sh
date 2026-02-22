#!/bin/bash
# Perennia AI Remediation Validation Script
# Usage: bash scripts/validate_phase.sh <phase-name>
# Phases: testing, architecture, encompass, telephony, frontend, focus, security, ai-agents, all

set -euo pipefail

PHASE="${1:-all}"
PASS=0
FAIL=0
WARN=0

green() { echo -e "\033[32m✓ $1\033[0m"; ((PASS++)); }
red() { echo -e "\033[31m✗ $1\033[0m"; ((FAIL++)); }
yellow() { echo -e "\033[33m⚠ $1\033[0m"; ((WARN++)); }

check() {
    local desc="$1"
    local cmd="$2"
    if eval "$cmd" > /dev/null 2>&1; then
        green "$desc"
    else
        red "$desc"
    fi
}

check_warn() {
    local desc="$1"
    local cmd="$2"
    if eval "$cmd" > /dev/null 2>&1; then
        green "$desc"
    else
        yellow "$desc (non-blocking)"
    fi
}

# ============================================================
# Phase: Testing & CI/CD
# ============================================================
validate_testing() {
    echo ""
    echo "━━━ Testing & CI/CD ━━━"

    check "GitHub Actions CI config exists" \
        "test -f .github/workflows/ci.yml"

    check "pytest configuration exists" \
        "test -f pytest.ini || test -f pyproject.toml && grep -q pytest pyproject.toml"

    check "Test directory exists with test files" \
        "find tests/ -name 'test_*.py' | head -1 | grep -q ."

    check "Auth tests exist" \
        "find tests/ -name '*auth*' -o -name '*login*' | head -1 | grep -q ."

    check "Leads CRUD tests exist" \
        "find tests/ -name '*lead*' | head -1 | grep -q ."

    check "Loans CRUD tests exist" \
        "find tests/ -name '*loan*' | head -1 | grep -q ."

    check_warn "Backend test coverage >5%" \
        "pytest --cov --cov-report=term --cov-fail-under=5 -q 2>/dev/null"

    check_warn "Frontend test runner passes" \
        "cd frontend && npm test -- --watchAll=false --passWithNoTests 2>/dev/null"

    # Count test files
    local test_count=$(find tests/ -name 'test_*.py' 2>/dev/null | wc -l)
    echo "  ℹ  Backend test files: $test_count"

    local fe_test_count=$(find frontend/src -name '*.test.*' -o -name '*.spec.*' 2>/dev/null | wc -l)
    echo "  ℹ  Frontend test files: $fe_test_count"
}

# ============================================================
# Phase: Architecture
# ============================================================
validate_architecture() {
    echo ""
    echo "━━━ Architecture ━━━"

    # main.py dependency count
    local main_imports=$(grep -rn "from main import\|from app.main import" --include="*.py" 2>/dev/null | wc -l)
    if [ "$main_imports" -lt 50 ]; then
        green "main.py imports reduced to $main_imports (target: <50)"
    elif [ "$main_imports" -lt 100 ]; then
        yellow "main.py imports at $main_imports (target: <50, was 157)"
    else
        red "main.py still has $main_imports dependent files (was 157, target: <50)"
    fi

    check "core/database.py exists" \
        "test -f app/core/database.py || test -f core/database.py"

    check "core/security.py exists" \
        "test -f app/core/security.py || test -f core/security.py"

    check "auth/dependencies.py exists" \
        "test -f app/auth/dependencies.py || test -f auth/dependencies.py"

    # Monolithic files
    local big_py=$(find . -name "*.py" -not -path "*/node_modules/*" -not -path "*/.venv/*" -exec wc -l {} + 2>/dev/null | awk '$1 > 2500 {print}' | wc -l)
    if [ "$big_py" -lt 10 ]; then
        green "Python files >2500 lines: $big_py (target: <10, was 24)"
    else
        red "Python files >2500 lines: $big_py (target: <10, was 24)"
    fi

    local big_js=$(find frontend/src -name "*.js" -o -name "*.jsx" -o -name "*.ts" -o -name "*.tsx" 2>/dev/null | xargs wc -l 2>/dev/null | awk '$1 > 3000 {print}' | wc -l)
    if [ "$big_js" -lt 5 ]; then
        green "Frontend files >3000 lines: $big_js (target: <5, was 9)"
    else
        red "Frontend files >3000 lines: $big_js (target: <5, was 9)"
    fi

    # Circular import check
    check_warn "No circular import workarounds" \
        "! grep -rn '_exported_functions' --include='*.py' | grep -q ."

    # API endpoint count
    echo "  ℹ  Run 'python scripts/audit_endpoints.py' for current endpoint count (was ~3,876)"
}

# ============================================================
# Phase: Encompass
# ============================================================
validate_encompass() {
    echo ""
    echo "━━━ Encompass Integration ━━━"

    check "Encompass integration module exists" \
        "test -d app/integrations/encompass || test -d integrations/encompass"

    check "Encompass auth module exists" \
        "find . -path '*/encompass/auth*' | head -1 | grep -q ."

    check "Encompass field mapping module exists" \
        "find . -path '*/encompass/field_mapping*' -o -path '*/encompass/mapping*' | head -1 | grep -q ."

    check "Sync audit log model exists" \
        "grep -rn 'sync_audit' --include='*.py' | head -1 | grep -q ."

    check "Loans table has encompass_loan_number column" \
        "grep -rn 'encompass_loan_number' --include='*.py' | head -1 | grep -q ."

    check_warn "Encompass webhook handler exists" \
        "grep -rn 'webhooks/encompass\|encompass.*webhook' --include='*.py' | head -1 | grep -q ."
}

# ============================================================
# Phase: Telephony
# ============================================================
validate_telephony() {
    echo ""
    echo "━━━ Telephony Consolidation ━━━"

    local telnyx_refs=$(grep -rn "telnyx\|TELNYX" --include="*.py" --include="*.js" --include="*.ts" 2>/dev/null | grep -v node_modules | grep -v ".lock" | wc -l)
    if [ "$telnyx_refs" -eq 0 ]; then
        green "No Telnyx references in codebase"
    else
        red "Still $telnyx_refs Telnyx references in codebase"
    fi

    check_warn "Telnyx not in requirements" \
        "! grep -qi telnyx requirements*.txt 2>/dev/null"

    check "Unified telephony service exists" \
        "find . -path '*/telephony/service*' -o -path '*/telephony_service*' | head -1 | grep -q ."
}

# ============================================================
# Phase: Frontend
# ============================================================
validate_frontend() {
    echo ""
    echo "━━━ Frontend Remediation ━━━"

    check "eslint-plugin-jsx-a11y installed" \
        "grep -q 'jsx-a11y' frontend/package.json 2>/dev/null"

    # ARIA attribute count
    local aria_count=$(grep -rn 'aria-' frontend/src --include="*.jsx" --include="*.tsx" 2>/dev/null | wc -l)
    echo "  ℹ  Components with ARIA attributes: ~$aria_count references (was 8 components)"

    check_warn "Feature-based component directories exist" \
        "test -d frontend/src/features 2>/dev/null"

    check_warn "i18n configuration exists" \
        "grep -q 'i18next\|react-i18next' frontend/package.json 2>/dev/null"

    # Settings.js check
    local settings_lines=$(wc -l < frontend/src/components/Settings.js 2>/dev/null || echo "0")
    if [ "$settings_lines" -lt 1000 ]; then
        green "Settings.js split (now $settings_lines lines, was 6,966)"
    elif [ "$settings_lines" -lt 3000 ]; then
        yellow "Settings.js partially split ($settings_lines lines, was 6,966)"
    else
        red "Settings.js still monolithic ($settings_lines lines)"
    fi
}

# ============================================================
# Phase: Security
# ============================================================
validate_security() {
    echo ""
    echo "━━━ Security & Compliance ━━━"

    check_warn "Dependabot config exists" \
        "test -f .github/dependabot.yml"

    check "Audit log model exists" \
        "grep -rn 'class AuditLog\|audit_log' --include='*.py' | head -1 | grep -q ."

    check_warn "Security policies documented" \
        "find docs/ -name '*security*' -o -name '*policy*' 2>/dev/null | head -1 | grep -q ."

    check_warn "No known critical vulnerabilities" \
        "pip install safety -q && safety check -r requirements.txt --short-report 2>/dev/null"
}

# ============================================================
# Phase: AI Agents
# ============================================================
validate_ai_agents() {
    echo ""
    echo "━━━ AI Agent Remediation ━━━"

    check "Agent metrics model exists" \
        "grep -rn 'agent_execution\|AgentExecution\|agent_metrics' --include='*.py' | head -1 | grep -q ."

    check_warn "Agent metrics API endpoint exists" \
        "grep -rn 'agent.metrics\|agent-metrics' --include='*.py' | head -1 | grep -q ."

    check_warn "Tool bridge exists" \
        "find . -path '*tool_bridge*' -o -path '*tool_loader*' | head -1 | grep -q ."

    # Tool registry vs agent service tool count
    echo "  ℹ  Run tool audit to check registry (206) vs agent service (~22) alignment"
}

# ============================================================
# Phase: Focus Strategy
# ============================================================
validate_focus() {
    echo ""
    echo "━━━ Feature Focus Strategy ━━━"
    echo "  ℹ  This is a strategic decision — manual validation required"
    echo "  ℹ  Check: Are non-core features frozen? (accounting, video, avatar studio)"
    echo "  ℹ  Check: Is 80%+ of engineering time on core/differentiating features?"
    echo "  ℹ  Check: Marketing materials reflect focused value proposition?"
}

# ============================================================
# Run
# ============================================================
echo "╔══════════════════════════════════════════╗"
echo "║  Perennia AI Remediation Validator       ║"
echo "║  Phase: $PHASE"
echo "╚══════════════════════════════════════════╝"

case "$PHASE" in
    testing)      validate_testing ;;
    architecture) validate_architecture ;;
    encompass)    validate_encompass ;;
    telephony)    validate_telephony ;;
    frontend)     validate_frontend ;;
    security)     validate_security ;;
    ai-agents)    validate_ai_agents ;;
    focus)        validate_focus ;;
    all)
        validate_testing
        validate_architecture
        validate_encompass
        validate_telephony
        validate_frontend
        validate_security
        validate_ai_agents
        validate_focus
        ;;
    *)
        echo "Unknown phase: $PHASE"
        echo "Valid phases: testing, architecture, encompass, telephony, frontend, security, ai-agents, focus, all"
        exit 1
        ;;
esac

echo ""
echo "━━━ Summary ━━━"
echo -e "\033[32m✓ Passed: $PASS\033[0m"
echo -e "\033[33m⚠ Warnings: $WARN\033[0m"
echo -e "\033[31m✗ Failed: $FAIL\033[0m"

if [ "$FAIL" -gt 0 ]; then
    exit 1
fi
