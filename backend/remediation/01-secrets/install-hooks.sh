#!/usr/bin/env bash
# 01-secrets/install-hooks.sh
# Installs pre-commit hooks and initializes secrets baseline.

set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

if ! command -v pre-commit &>/dev/null; then
  pip install --user pre-commit
fi

if ! command -v detect-secrets &>/dev/null; then
  pip install --user detect-secrets
fi

# Copy config to repo root
cp "$(dirname "$0")/.pre-commit-config.yaml" .pre-commit-config.yaml
cp "$(dirname "$0")/.gitleaks.toml" .gitleaks.toml

# Create baseline for detect-secrets (catalogs existing "known" findings so
# only NEW findings fail the commit)
echo "==> Generating secrets baseline (reviews existing code for false positives)"
detect-secrets scan \
  --exclude-files 'package-lock\.json|yarn\.lock|pnpm-lock\.yaml|\.git/' \
  > .secrets.baseline

# Install the hooks
pre-commit install
pre-commit install --hook-type commit-msg

echo "==> Pre-commit hooks installed."
echo "==> Every commit will now be scanned before it's accepted."
echo ""
echo "To run manually: pre-commit run --all-files"
