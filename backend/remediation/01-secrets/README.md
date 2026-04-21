# 01 — Secrets Rotation & Git History Scrub

**Findings addressed:** #1 (hardcoded secrets), #13 (committed .env.test)

This step is the one-way door. Once rotated, the old credentials are dead. Do this first and do it carefully.

## What Gets Rotated

Every credential that has ever been committed to git history. Assume everything in any `.env*` file anywhere in the repo's history is compromised.

Checklist — generate NEW values for each, then paste into Railway env vars:

- [ ] `TELNYX_API_KEY` (dashboard → API Keys → issue new → revoke old)
- [ ] `TWILIO_AUTH_TOKEN` (console → Account → API keys & tokens → rotate)
- [ ] `SMTP_PASSWORD` / `GMAIL_APP_PASSWORD` (Google account → App passwords → revoke + regenerate)
- [ ] `ANTHROPIC_API_KEY` (console → revoke + regenerate)
- [ ] `OPENAI_API_KEY` if present
- [ ] `SALESFORCE_CLIENT_SECRET`
- [ ] `MICROSOFT_GRAPH_CLIENT_SECRET`
- [ ] `VAPI_API_KEY`
- [ ] `CARTESIA_API_KEY`
- [ ] `DEEPGRAM_API_KEY`
- [ ] `STRIPE_SECRET_KEY` if present
- [ ] `SENDGRID_API_KEY`
- [ ] `JWT_SECRET_KEY` / `SECRET_KEY` (forces session invalidation — intentional)
- [ ] `PII_ENCRYPTION_KEY` → **see step 02, this requires data re-encryption**
- [ ] `DATABASE_URL` password (optional but recommended)
- [ ] `REDIS_URL` password
- [ ] AWS access keys (S3 for docs) — issue new, revoke old
- [ ] Any webhook signing secrets (Twilio, Telnyx, Stripe)

## Execution

```bash
# 1. Scan current state — confirm what's been leaked
./scan-leaks.sh

# 2. Rotate in provider dashboards per checklist above.
#    Paste new values into Railway. Do NOT commit them.

# 3. Scrub git history of all .env* files that ever existed
./scrub-history.sh

# 4. Force-push (requires collaborator coordination)
git push --force-with-lease origin main

# 5. Install pre-commit hook so this never happens again
./install-hooks.sh

# 6. Re-scan to confirm history is clean
gitleaks detect --source . --log-level info
```

## Why force-push and not just delete the files

Deleting `.env.test` in a new commit leaves the old credentials in git history forever. Anyone with repo read access (contractors, acquirers, CI runners, a leaked SSH key) can `git log -p` and retrieve them. `git-filter-repo` rewrites history so the secrets are genuinely gone.

After force-push, every local clone of the repo has stale history. All collaborators must delete their clones and re-clone. No rebasing out of it.
