#!/usr/bin/env bash
# 01-secrets/scan-leaks.sh
# Run gitleaks across full history to inventory what's been exposed.
# Output feeds the rotation checklist.

set -euo pipefail

if ! command -v gitleaks &>/dev/null; then
  echo "Installing gitleaks..."
  # macOS
  if [[ "$OSTYPE" == "darwin"* ]]; then
    brew install gitleaks
  else
    # Linux
    GITLEAKS_VERSION="8.21.2"
    curl -sSfL "https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}/gitleaks_${GITLEAKS_VERSION}_linux_x64.tar.gz" \
      | tar -xz -C /tmp gitleaks
    sudo mv /tmp/gitleaks /usr/local/bin/
  fi
fi

REPORT="/tmp/perennia-gitleaks-$(date +%Y%m%d-%H%M%S).json"

echo "==> Scanning full git history"
gitleaks detect \
  --source . \
  --report-format json \
  --report-path "${REPORT}" \
  --log-level info \
  --no-banner \
  || true  # gitleaks exits nonzero on findings — expected

FINDINGS=$(jq 'length' "${REPORT}")

echo ""
echo "==> Report: ${REPORT}"
echo "==> Total findings: ${FINDINGS}"
echo ""

if [ "${FINDINGS}" -gt 0 ]; then
  echo "Unique secret types detected:"
  jq -r '.[].RuleID' "${REPORT}" | sort -u | sed 's/^/  - /'
  echo ""
  echo "Unique files involved:"
  jq -r '.[].File' "${REPORT}" | sort -u | sed 's/^/  - /'
  echo ""
  echo "Every credential above must be rotated before proceeding."
fi
