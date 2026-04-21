# ci/BRANCH_PROTECTION.md

Configure GitHub branch protection on `main` with these required checks. Set via
Settings → Branches → Branch protection rules → `main`:

## Required status checks (all must pass)

- `Backend lint (ruff)`
- `Backend typecheck (mypy)`
- `Backend tests (pytest)`
- `Frontend lint`
- `Frontend tests (vitest)`
- `Frontend build + size budget`
- `Alembic up + down round-trip`
- `Playwright critical paths`
- `Gitleaks`
- `detect-secrets (baseline audit)`
- `Reject committed .env files`
- `pip-audit (backend SCA)`
- `npm audit (frontend SCA)`
- `Semgrep SAST`
- `Trivy container scan`

## Required rules

- [x] Require a pull request before merging
- [x] Require approvals: **1** (raise to 2 once team > 1)
- [x] Dismiss stale pull request approvals when new commits are pushed
- [x] Require review from Code Owners
- [x] Require status checks to pass before merging
- [x] Require branches to be up to date before merging
- [x] Require conversation resolution before merging
- [x] Require signed commits
- [x] Require linear history
- [x] Do not allow bypassing the above settings
- [x] Restrict who can push to matching branches — only admins + CI

## CODEOWNERS (place at .github/CODEOWNERS)

```
# Global default
*                              @tim

# Security-sensitive paths require extra eyes once team grows
backend/app/auth/**            @tim
backend/app/security/**        @tim
backend/alembic/**             @tim
.github/workflows/**           @tim
.gitleaks.toml                 @tim
.pre-commit-config.yaml        @tim
```

## Repo-wide settings

- Settings → General → "Automatically delete head branches" — on
- Settings → Actions → "Allow GitHub Actions to create and approve pull requests" — off
- Settings → Code security → Dependency graph — on
- Settings → Code security → Dependabot alerts — on
- Settings → Code security → Dependabot security updates — on
- Settings → Code security → Secret scanning — on
- Settings → Code security → Push protection for secrets — on
