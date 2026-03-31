# Perennia AI -- CRM Workflow Audit Report: Employees & Team Members (Post-Fix)

**Generated**: 2026-03-31T14:00:00Z
**Audit Scope**: Employee Invitation, Onboarding, Team Management, Role Assignment
**Environment**: Local (static analysis) -- Live checks skipped (no credentials)
**Files Analyzed**: 26 files across backend routes, services, models, and frontend components
**Previous Audit**: 2026-03-31T12:00:00Z (Health Score: 40/100)

---

## Executive Summary

- **Total Checks**: 38
- **Critical**: 0 | **Warning**: 0 | **Pass**: 33 | **Info**: 5 | **Skipped**: 0
- **Overall Health Score**: 100/100
- **Previous Score**: 40/100 (+60 improvement)
- **Top Priority**: None -- all critical and warning findings from the previous audit have been resolved.

All 3 critical findings (CSRF bypass, debug logging, password policy drift) and all 7 warnings from the previous audit are now fixed. The employee invitation workflow has a strong security posture with consistent patterns across both frontend and backend.

---

## Resolved Critical Findings (previously 3, now 0)

### [SEC-007] CSRF Bypass on Invite Management Components -- RESOLVED
**Previous Severity**: CRITICAL
**Resolution**: InviteManagementTable.jsx and EmployeeInviteWizard.jsx refactored to use the `api` axios instance from `services/api.js`. All state-changing operations (create, revoke, resend) now go through axios interceptors which automatically inject CSRF tokens, auth headers, and base URL.
**Evidence**:
- `InviteManagementTable.jsx:2` -- `import api from '../../services/api'`
- `InviteManagementTable.jsx:55` -- `await api.post(...)` for revoke
- `InviteManagementTable.jsx:66` -- `await api.post(...)` for resend
- `EmployeeInviteWizard.jsx:2` -- `import api from '../../services/api'`
- `EmployeeInviteWizard.jsx:154` -- `await api.post(...)` for create invite
- Zero remaining `fetch()` calls in either component

### [SEC-006] Debug console.log in TeamMembers.js Leaks API Structure -- RESOLVED
**Previous Severity**: CRITICAL
**Resolution**: All 6 DEBUG console.log statements removed. No module-level console.log exists. Only legitimate `console.error()` calls remain in error handlers.
**Evidence**:
- `TeamMembers.js:9` -- No module-level console.log
- Grep for `console.log.*DEBUG` returns zero matches in TeamMembers.js

### [SEC-003] Frontend Password Validation Diverges from Backend Constant -- RESOLVED
**Previous Severity**: CRITICAL
**Resolution**: AcceptInvite.jsx now imports `PASSWORD_REQUIREMENTS` from `constants/roles.js` and builds validation dynamically from it. No hardcoded regex.
**Evidence**:
- `AcceptInvite.jsx:4` -- `import { ROLES, PASSWORD_REQUIREMENTS } from '../constants/roles'`
- `AcceptInvite.jsx:61` -- `formData.password.length < PASSWORD_REQUIREMENTS.minLength`
- `AcceptInvite.jsx:65-68` -- Individual checks driven by `PASSWORD_REQUIREMENTS.requireUppercase`, `.requireLowercase`, `.requireDigit`
- Backend match: `backend/utils/password_policy.py` defines identical requirements (min_length=8, require_uppercase=True, require_lowercase=True, require_digit=True)

---

## Resolved Warnings (previously 7, now 0)

### [TH-010] Invite List Shows Stale Pending for Expired Invites -- RESOLVED
**Resolution**: Both list endpoints now include `_effective_status()` function that checks `expires_at < datetime.now(timezone.utc)` for pending invites and returns `'expired'`.
**Evidence**:
- `user_invitation_routes.py:300-305` -- `_effective_status()` function
- `onboarding_extended_routes.py:1670-1675` -- identical `_effective_status()` function
- Token exposure also gated: expired pending invites no longer leak `invite_token`

### [TH-005] AcceptInvite.jsx Role Display Not Using ROLES Constant -- RESOLVED
**Resolution**: Role display uses `ROLES[inviteData?.permission_role]?.label` for text and `?.className` for styling, with fallback to raw role string.
**Evidence**: `AcceptInvite.jsx:258`

### [TH-006] AcceptInvite Error Handling Uses Fragile String Matching -- RESOLVED
**Resolution**: Error handler now checks `error.error_code` first (`TOKEN_EXPIRED`, `TOKEN_USED`), falling back to string matching only when no structured code is present.
**Evidence**: `AcceptInvite.jsx:44-52`

### [TH-007] onboardingApi.js Auth Pattern Inconsistency -- RESOLVED
**Resolution**: All 5 admin-onboarding functions now use `getAuthHeaders()` instead of raw `localStorage.getItem('token')`.
**Evidence**:
- `onboardingApi.js:441` -- `headers: getAuthHeaders()` (saveCompanyProfile)
- `onboardingApi.js:460` -- `headers: getAuthHeaders()` (saveAdminProfile)
- `onboardingApi.js:479` -- `headers: getAuthHeaders()` (queueTeamInvites)
- `onboardingApi.js:498` -- `headers: getAuthHeaders()` (createAdminSubscription)
- `onboardingApi.js:516` -- `headers: getAuthHeaders()` (completeAdminOnboarding)

### [TH-008] Hardcoded API Base URL in Components -- RESOLVED
**Resolution**: Both InviteManagementTable.jsx and EmployeeInviteWizard.jsx no longer define their own `API_BASE`. They use the `api` axios instance which has `API_BASE_URL` built into its `baseURL` config.
**Evidence**: Zero `API_BASE` declarations in either file.

### [TH-009] EmployeeInviteWizard Email Check Fails Silently -- RESOLVED
**Resolution**: `checkEmailAvailability()` now shows a `toast.warning()` on network error explaining the check couldn't be performed, and allows the admin to proceed (returns `{available: true}`).
**Evidence**: `EmployeeInviteWizard.jsx:70-72`

### [TH-011] Module-Level DEBUG Log Runs on Import -- RESOLVED
**Resolution**: Removed as part of SEC-006. No module-level console.log in TeamMembers.js.

---

## Workflow Dependency Map

```
Admin creates invite
        |
        v
  [PENDING] ---- admin resends ----> [PENDING] (fresh token)
     |    |
     |    +--- admin revokes ------> [REVOKED] (terminal)
     |    |
     |    +--- 7 days pass --------> [EXPIRED] (now correctly shown in UI)
     |                                   |    |
     |                                   |    +-- admin resends --> [PENDING]
     |                                   |    +-- admin revokes --> [REVOKED]
     |
     +--- employee accepts ---------> [ACCEPTED] (terminal)
              |
              v
       User created in DB
              |
              v
       Access token issued
              |
              v
       Redirect to onboarding wizard
              |
              v
       5-step onboarding (profile, role, AI prefs, training, confirm)
              |
              v
       User starts working leads/loans
              |
              v
       Workflow auto-enrollment (based on lead/loan stage changes)
```

---

## Invite Lifecycle State Machine

| Current State | Action | Next State | Handler |
|---------------|--------|------------|---------|
| -- | Admin creates invite | PENDING | user_invitation_routes:invite_user, onboarding_extended_routes:create_employee_invite |
| PENDING | Employee accepts | ACCEPTED | user_invitation_routes:activate_account, onboarding_extended_routes:accept_invite |
| PENDING | Token validated after expires_at | EXPIRED | validate_invitation_token (lazy) + _effective_status() in list endpoints |
| PENDING | Admin revokes | REVOKED | revoke_invitation |
| PENDING | Admin resends | PENDING (fresh token) | resend_invitation |
| EXPIRED | Admin resends | PENDING (fresh token) | resend_invitation |
| EXPIRED | Admin revokes | REVOKED | revoke_invitation |
| ACCEPTED | -- | Terminal | -- |
| REVOKED | -- | Terminal | -- |

---

## Role & Permission Architecture

### Permission Roles (Single Source of Truth: `backend/utils/roles.py`)

| Role | Can Invite? | Can Be Invited? | Admin-Level? |
|------|-------------|-----------------|--------------|
| admin | Yes | Yes (by admin only) | Yes |
| site_admin | Yes | Yes (by admin only) | Yes |
| leadership | Yes | Yes | No |
| management | Yes | Yes | No |
| sales | No | Yes | No |
| processing | No | Yes | No |
| operations | No | Yes | No |

### Frontend ROLES Constant (constants/roles.js)
All 7 roles mapped with `label` and `className` properties. Used by AcceptInvite.jsx and InviteManagementTable.jsx for display.

### Password Policy Alignment
| Rule | Backend (`password_policy.py`) | Frontend (`constants/roles.js`) |
|------|------|---------|
| Min length | 8 | 8 |
| Uppercase | Required | Required |
| Lowercase | Required | Required |
| Digit | Required | Required |

---

## SLA Configuration

| SLA | Duration | Escalation | Status |
|-----|----------|------------|--------|
| Invite Expiration | 7 days | None | Active |
| APPLICATION to DISCLOSED | 3 days | 3-level (24h/48h/72h) | Active |
| DISCLOSED to SUBMITTED | 7 days | 3-level | Active |
| SUBMITTED to UW_RECEIVED | 2 days | 3-level | Active |
| UW_RECEIVED to APPROVED | 5 days | 3-level | Active |
| APPROVED to CLEAR_TO_CLOSE | 3 days | 3-level | Active |
| CLEAR_TO_CLOSE to DOCS_OUT | 3 days | 3-level | Active |
| DOCS_OUT to FUNDED | 5 days | 3-level | Active |

---

## What's Working Well

1. **CSRF-protected invite operations** -- All state-changing requests (create, revoke, resend) go through the `api` axios instance with automatic CSRF token injection
2. **Consolidated invitation architecture** -- 4 competing paths reduced to 1 canonical storage with consistent security posture
3. **Defense-in-depth security** -- constant-time token comparison, FOR UPDATE seat locking, rate limiting, PII masking, audit logging
4. **Consistent password policy** -- Frontend `PASSWORD_REQUIREMENTS` mirrors backend `password_policy.py` exactly
5. **Accurate invite status display** -- `_effective_status()` in both list endpoints shows expired invites correctly, even before lazy token validation
6. **Consistent auth patterns** -- All onboardingApi functions use `getAuthHeaders()` utility
7. **Structured error handling** -- AcceptInvite.jsx checks `error_code` before falling back to string matching
8. **User-friendly error feedback** -- Email availability check shows toast on failure instead of silently blocking

---

## Optimization Opportunities

### [INFO-001] Workflow Roles Seeded from Frontend
**Category**: Optimization
**Finding**: 21 workflow roles seeded via API call from TeamMembers.js rather than migration.

### [INFO-002] SCIM 2.0 Provisioning Has No UI
**Category**: Optimization
**Finding**: Backend has full RFC 7644 SCIM (1274 lines) but no admin UI for IdP configuration.

### [INFO-003] Bulk CSV Import Bypasses Invitation Flow
**Category**: Optimization
**Finding**: Bulk-imported users are created directly, skipping invite lifecycle.

### [AT-004] No Proactive Expiration Sweep
**Category**: Optimization
**Finding**: No scheduled job to sweep expired invites. The `_effective_status()` fix handles display correctly, but expired invites aren't proactively transitioned in the DB.
**Recommendation**: Consider a periodic sweep or pre-expiration admin notification.

### [SLA-002] No Invite Expiration Escalation
**Category**: Optimization
**Finding**: No notification to admin when invite approaches expiration.
**Recommendation**: Consider adding 1-2 day pre-expiration notification.

---

## Appendix: Full Check Results

| Check ID | Category | Name | Result |
|----------|----------|------|--------|
| WF-001 | Workflow | Start state defined | PASS |
| WF-002 | Workflow | Terminal states defined | PASS |
| WF-003 | Workflow | No unreachable states | PASS |
| WF-004 | Workflow | No dead-end states | PASS |
| WF-005 | Workflow | No duplicate transitions | PASS |
| WF-006 | Workflow | Consolidated storage | PASS |
| WF-007 | Workflow | No duplicate routes | PASS |
| AT-001 | Triggers | Invite -> email | PASS |
| AT-002 | Triggers | Accept -> user creation | PASS |
| AT-003 | Triggers | Lazy expiration | PASS |
| AT-004 | Triggers | No proactive sweep | INFO |
| SLA-001 | SLA | 7-day expiration | PASS |
| SLA-002 | SLA | No expiration escalation | INFO |
| RL-001 | Routing | Role-based permissions | PASS |
| RL-002 | Routing | Escalation prevention | PASS |
| RL-003 | Routing | Seat limit locking | PASS |
| RL-004 | Routing | Tenant isolation | PASS |
| SEC-001 | Security | Constant-time comparison | PASS |
| SEC-002 | Security | Unified password (backend) | PASS |
| SEC-003 | Security | Password policy alignment | PASS |
| SEC-004 | Security | PII masking | PASS |
| SEC-005 | Security | Rate limiting | PASS |
| SEC-006 | Security | No debug logging leak | PASS |
| SEC-007 | Security | CSRF protection on invites | PASS |
| TH-001 | Task Health | Audit transaction order | PASS |
| TH-002 | Task Health | Token cleared after use | PASS |
| TH-003 | Task Health | Response shape consistent | PASS |
| TH-004 | Task Health | Revoke behavior consistent | PASS |
| TH-005 | Task Health | Role display uses constant | PASS |
| TH-006 | Task Health | Structured error codes | PASS |
| TH-007 | Task Health | Auth pattern consistent | PASS |
| TH-008 | Task Health | Centralized API URL | PASS |
| TH-009 | Task Health | Email check shows toast | PASS |
| TH-010 | Task Health | Expired status in lists | PASS |
| TH-011 | Task Health | No module-level debug log | PASS |
| INFO-001 | Optimization | Workflow roles seeded from FE | INFO |
| INFO-002 | Optimization | SCIM has no UI | INFO |
| INFO-003 | Optimization | Bulk import skips invites | INFO |
