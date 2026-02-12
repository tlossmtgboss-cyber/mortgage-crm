# Environment Configuration

## Required Environment Variables

```bash
# ============================================================
# PORTAL SKILL CHALLENGE - Environment Configuration
# ============================================================
# Copy this to .env and fill in values before running validation

# --- Application URLs ---
PERENNIA_BASE_URL=https://app.perennia.ai          # Frontend base URL
PERENNIA_API_URL=https://api.perennia.ai            # Backend API base URL

# --- Database (read-only access sufficient) ---
DATABASE_URL=postgresql://validator:****@host:5432/perennia?sslmode=require

# --- Authentication Tokens ---
# Admin JWT for CRM-side operations
ADMIN_JWT=eyJhbGciOiJIUzI1NiIs...

# Test borrower PURL tokens (generate via admin API before running)
BORROWER_READ_TOKEN=purl_live_read_test_...
BORROWER_WRITE_TOKEN=purl_live_write_test_...
EXPIRED_TEST_TOKEN=purl_live_expired_...

# Cross-tenant test tokens (for isolation checks)
ORG_A_TOKEN=purl_live_orga_...
ORG_B_TOKEN=purl_live_orgb_...

# Role-specific tokens for RBAC checks
ROLE_TOKEN_JR_LO=eyJ...
ROLE_TOKEN_CONCIERGE=eyJ...
ROLE_TOKEN_MANAGER=eyJ...
ROLE_TOKEN_APP_ANALYSIS=eyJ...

# --- Test Entity IDs ---
TEST_ORG_ID=uuid-of-test-org
TEST_USER_ID=uuid-of-test-user
TEST_WORKSPACE_ID=uuid-of-test-workspace
TEST_PURL_SLUG=test-borrower-portal
TEST_PARTNER_SLUG=test-partner-portal
TEST_LO_SLUG=test-lo-portal
TEST_DOCUMENT_ID=uuid-of-test-document

# Cross-tenant test entities
ORG_A_ID=uuid-of-org-a
ORG_B_ID=uuid-of-org-b
USER_A_ID=uuid-of-user-a
ORG_B_WORKSPACE_SLUG=org-b-workspace

# Document test entities
BORROWER_A_DOCUMENT_ID=uuid-of-borrower-a-doc
BORROWER_A_TOKEN=purl_live_borrowera_...
BORROWER_B_TOKEN=purl_live_borrowerb_...

# --- Salesforce Integration ---
SF_CLIENT_ID=3MVG9...
SF_CLIENT_SECRET=****
SF_TOKEN_URL=https://login.salesforce.com/services/oauth2/token
SF_INSTANCE_URL=https://yourorg.my.salesforce.com

# --- AWS S3 (for document checks) ---
AWS_REGION=us-east-1
S3_BUCKET=perennia-documents

# --- Expected Origins (for CORS check) ---
EXPECTED_ORIGIN=https://app.perennia.ai

# --- Validation Settings ---
VALIDATION_MODE=full                    # full | portal-only | sync-only | security-only | targeted
VALIDATION_OUTPUT=both                  # json | report | both
TARGETED_PORTAL=                        # borrower | partner | lo (only for targeted mode)
TARGETED_DOMAIN=                        # setup | access | security | crm-sync | doc-sync (only for targeted mode)
```

## Security Notes

1. **Never commit `.env` to version control** — Add to `.gitignore`
2. **Use read-only database credentials** — The validator should not modify production data
3. **Test tokens should be short-lived** — Generate fresh tokens before each validation run
4. **Cross-tenant tokens** — Use dedicated test organizations, never production orgs
5. **Salesforce sandbox** — Use sandbox credentials for sync checks when possible
6. **Rotate after use** — Revoke test tokens after validation completes

## Pre-Run Checklist

```bash
# 1. Generate test tokens
curl -X POST $PERENNIA_API_URL/api/v1/purl-admin/tokens \
  -H "Authorization: Bearer $ADMIN_JWT" \
  -H "Content-Type: application/json" \
  -d '{"workspace_id": "'$TEST_WORKSPACE_ID'", "scope": "read", "expires_in_hours": 1}'

# 2. Verify database connectivity
psql $DATABASE_URL -c "SELECT 1"

# 3. Verify Salesforce connectivity
curl -H "Authorization: Bearer $SF_ACCESS_TOKEN" \
  "$SF_INSTANCE_URL/services/oauth2/userinfo"

# 4. Verify API health
curl $PERENNIA_API_URL/api/v1/health
```
