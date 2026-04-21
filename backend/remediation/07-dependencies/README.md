# 07 — Dependencies

**Findings addressed:**
- #3 (22 npm vulnerabilities, 1 critical)
- Enterprise gap: no automated dependency scanning

## Immediate Fixes

```bash
# Backend (Python)
cd backend
pip install pip-audit
pip-audit --fix --requirement requirements.txt

# Frontend (npm)
cd frontend
npm audit
npm audit fix --force  # --force is fine for a PR branch — review the diff
# For anything that can't auto-fix:
npm audit fix --production
# Remaining must be manually bumped; see audit output for advisories
npm outdated  # review and bump majors with care
```

## Automation

Two layers of defense: GitHub Dependabot for PRs, CI guard for merges.

### Dependabot

Copy `dependabot.yml` to `.github/dependabot.yml`. This opens weekly PRs for:
- Python (backend)
- npm (frontend)
- GitHub Actions
- Docker (if you add it)

### CI guard (rejects merges with new vulnerabilities)

Copy `security-scan.yml` to `.github/workflows/security-scan.yml`. This runs on every PR:
- `pip-audit` — fails on any HIGH/CRITICAL
- `npm audit` — fails on any HIGH/CRITICAL
- Trivy container scan
- Semgrep SAST

### Snyk (optional, paid)

If your SOC 2 auditor requires a named SCA vendor, Snyk is the standard.
Add `SNYK_TOKEN` to repo secrets and the workflow in `snyk.yml` runs on every PR.

## Policy

- **Critical** (CVSS 9.0+): block merge. Fix before PR lands.
- **High** (CVSS 7.0-8.9): block merge unless explicit waiver (reviewed + logged).
- **Medium** (CVSS 4.0-6.9): open an issue, fix within 14 days.
- **Low**: track in issue, fix during normal maintenance.

Waivers live in `.security-waivers.yml` with a date-bound justification.
