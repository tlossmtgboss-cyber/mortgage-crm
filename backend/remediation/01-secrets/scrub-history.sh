#!/usr/bin/env bash
# 01-secrets/scrub-history.sh
# Rewrites git history to permanently remove all .env* files and known secret patterns.
# Requires: git-filter-repo (pip install git-filter-repo)
#
# WARNING: This rewrites ALL commits. Every collaborator must re-clone after push.

set -euo pipefail

if ! command -v git-filter-repo &>/dev/null; then
  echo "Installing git-filter-repo..."
  pip install --user git-filter-repo
fi

# Safety: confirm we're in a repo and have a clean working tree
if ! git rev-parse --git-dir &>/dev/null; then
  echo "!! Not in a git repo. Aborting."
  exit 1
fi

if [ -n "$(git status --porcelain)" ]; then
  echo "!! Working tree is dirty. Commit or stash first. Aborting."
  exit 1
fi

# Safety: confirm a pre-remediation tag exists
if ! git rev-parse --verify "pre-remediation-$(date +%Y%m%d)" &>/dev/null 2>&1; then
  echo "Creating safety tag..."
  git tag "pre-remediation-$(date +%Y%m%d)"
fi

# Create a fresh backup clone so we can recover if something goes wrong
BACKUP_DIR="../$(basename $(pwd))-pre-scrub-$(date +%Y%m%d-%H%M%S)"
echo "==> Creating backup clone at ${BACKUP_DIR}"
git clone --mirror . "${BACKUP_DIR}"

# Files to purge from ALL history
cat > /tmp/perennia-paths-to-purge.txt <<'EOF'
.env
.env.test
.env.local
.env.production
.env.development
.env.staging
backend/.env
backend/.env.test
frontend/.env
frontend/.env.local
EOF

echo "==> Purging sensitive files from entire history"
git filter-repo \
  --invert-paths \
  --paths-from-file /tmp/perennia-paths-to-purge.txt \
  --force

# Also redact any stray secret patterns that might be in source files.
# Add more patterns if gitleaks found them in .py, .js, .ts, etc.
cat > /tmp/perennia-secret-patterns.txt <<'EOF'
regex:KEY[0-9A-Za-z_\-]{20,}==>REDACTED_TELNYX_KEY
regex:sk-ant-api03-[A-Za-z0-9_\-]+==>REDACTED_ANTHROPIC_KEY
regex:sk-[A-Za-z0-9]{32,}==>REDACTED_OPENAI_KEY
regex:AC[a-f0-9]{32}==>REDACTED_TWILIO_SID
regex:SG\.[A-Za-z0-9_\-]{22}\.[A-Za-z0-9_\-]{43}==>REDACTED_SENDGRID_KEY
regex:AKIA[0-9A-Z]{16}==>REDACTED_AWS_ACCESS_KEY
EOF

echo "==> Redacting secret patterns from source file history"
git filter-repo \
  --replace-text /tmp/perennia-secret-patterns.txt \
  --force

echo "==> Re-scanning to confirm history is clean"
gitleaks detect --source . --no-banner --log-level warn || {
  echo "!! Gitleaks still found secrets. Review and add patterns to /tmp/perennia-secret-patterns.txt, then re-run."
  exit 1
}

echo ""
echo "==> History scrub complete."
echo "==> Next: git push --force-with-lease origin --all --tags"
echo "==> Every collaborator MUST delete local clones and re-clone."
echo "==> Backup preserved at: ${BACKUP_DIR}"
