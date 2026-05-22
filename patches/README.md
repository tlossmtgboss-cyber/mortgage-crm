# Builder Portal Submission Fix

## What broke

Builders completed all 9 review pages and clicked **Submit Packet**, but got:

> No submission token — your application was not sent to the loan officer. Please re-register.

`review.html` reads `localStorage.builderSubmissionToken` and dead-ends if it's missing. That token is only stored when `register.html` is opened with `?lo=<slug>` in the URL. If the builder landed on `register.html` without that param, cleared their cache, switched browsers, or used private mode, the token never made it to localStorage and the final submit always fails.

## Fix

### Backend (this repo — already applied)

New endpoint that returns the existing draft's token given `lo_slug` + `email`:

```
POST /api/v1/builder-portal/recover-token
{ "lo_slug": "...", "email": "..." }
→ { application_id, submission_token, status }
```

Rate-limited per IP via the same limiter as `/register`. Returns 404 when no application exists and 410 when the application is older than 30 days. The endpoint is idempotent and has no side effects, so it's safe to call from public HTML.

### Frontend (`tlossmtgboss-cyber/cmg-builder-portal` — patch in this directory)

`cmg-builder-portal-review.patch` rewires `pushToBackend()` in `review.html` so that, when no token is in localStorage (or the token is rejected with 401), it calls `recover-token` with the stored `builderLOSlug` + `builderAccount.email`, stores the recovered token, and retries the submit once.

Apply with:

```sh
cd cmg-builder-portal
git apply /path/to/cmg-builder-portal-review.patch
git commit -am "fix: recover submission token on submit when localStorage is empty"
git push
```
