# Portal Skill Challenge — Validation Report

**Generated:** 2026-02-13T11:01:46.254486+00:00
**Mode:** full

## Executive Summary

| Metric | Value |
|--------|-------|
| **Security Score** | **70/100** 🟠 Needs Attention |
| Total Checks | 18 |
| Passed | 5 |
| Failed | 4 |
| Skipped | 9 |
| Errors | 0 |
| Critical Failures | 2 |

## Domain: setup

### ✅ PS-001: Portal routes resolve
- **Severity:** CRITICAL
- **Status:** PASSED
- **Duration:** 221.0ms
- **Applies to:** borrower, partner, lo
- **Details:** `{"borrower": {"status_code": 200, "passed": true, "url": "https://app.perenniaai.com/portal/test-borrower"}, "partner": {"status_code": 200, "passed": true, "url": "https://app.perenniaai.com/partners/test-partner"}, "lo": {"status_code": 200, "passed": true, "url": "https://app.perenniaai.com/lo/test-lo"}}`

### ✅ PS-006: SSL/TLS certificate valid (>30 days)
- **Severity:** CRITICAL
- **Status:** PASSED
- **Duration:** 84.3ms
- **Applies to:** borrower, partner, lo
- **Details:** `{"days_remaining": 76, "expiry_date": "2026-05-01T07:02:53", "hostname": "app.perenniaai.com"}`

### ✅ PS-007: CORS configuration restricts origins
- **Severity:** HIGH
- **Status:** PASSED
- **Duration:** 807.0ms
- **Applies to:** borrower, partner, lo
- **Details:** `{"expected_origin_allowed": "", "malicious_origin_allowed": "", "no_wildcard": true, "rejected_evil": true, "ssl_warning": "SSL verification bypassed \u2014 API certificate has hostname mismatch"}`

### ✅ PS-010: HTTPS enforced (HTTP → HTTPS redirect)
- **Severity:** CRITICAL
- **Status:** PASSED
- **Duration:** 68.3ms
- **Applies to:** borrower, partner, lo
- **Details:** `{"status_code": 308, "redirect_location": "https://app.perenniaai.com/", "redirects_to_https": true}`

## Domain: access

### ❌ UA-001: PURL token generation and authentication
- **Severity:** CRITICAL
- **Status:** FAILED
- **Duration:** 0.0ms
- **Applies to:** borrower
- **Details:** `{"error": "admin_jwt or test_workspace_id not configured"}`
- **Remediation:** Check purl_token_service.py. Verify purl_access_tokens table. Check admin auth.

### ⏭️ UA-002: Expired tokens rejected (HTTP 401)
- **Severity:** CRITICAL
- **Status:** SKIPPED
- **Duration:** 0.0ms
- **Applies to:** borrower, partner, lo
- **Details:** `{"skipped": "expired_test_token not configured"}`

### ⏭️ UA-006: Read-only token cannot write (HTTP 403)
- **Severity:** CRITICAL
- **Status:** SKIPPED
- **Duration:** 0.0ms
- **Applies to:** borrower
- **Details:** `{"skipped": "borrower_read_token not configured"}`

### ⏭️ UA-011: Multi-tenant isolation via API
- **Severity:** CRITICAL
- **Status:** SKIPPED
- **Duration:** 0.0ms
- **Applies to:** borrower, partner, lo
- **Details:** `{"skipped": "Cross-tenant tokens not configured"}`

## Domain: security

### ⏭️ SEC-006: SQL injection protection
- **Severity:** CRITICAL
- **Status:** SKIPPED
- **Duration:** 0.0ms
- **Applies to:** borrower, partner, lo
- **Details:** `{"skipped": "borrower_read_token not configured"}`

### ❌ SEC-007: Security headers present (CSP, X-Content-Type, etc.)
- **Severity:** HIGH
- **Status:** FAILED
- **Duration:** 222.6ms
- **Applies to:** borrower, partner, lo
- **Details:** `{"header_checks": {"x-content-type-options": false, "x-frame-options": false, "strict-transport-security": false, "referrer-policy": false}, "headers_found": {"x-content-type-options": "MISSING", "x-frame-options": "MISSING", "strict-transport-security": "MISSING", "referrer-policy": "MISSING", "content-security-policy": "MISSING", "permissions-policy": "MISSING"}, "ssl_warning": "SSL verification bypassed \u2014 API certificate has hostname mismatch"}`
- **Remediation:** Add security headers in middleware or reverse proxy configuration.

### ✅ SEC-008: No API keys exposed in client bundles
- **Severity:** CRITICAL
- **Status:** PASSED
- **Duration:** 144.8ms
- **Applies to:** borrower, partner, lo
- **Details:** `{"bundles_scanned": 1, "leaks_found": 0, "leak_details": []}`

### ❌ SEC-013: OWASP security headers check
- **Severity:** HIGH
- **Status:** FAILED
- **Duration:** 430.7ms
- **Applies to:** borrower, partner, lo
- **Details:** `{"results_by_target": {"frontend": {"owasp_headers": {"X-Frame-Options": false, "X-Content-Type-Options": false, "Referrer-Policy": false, "Content-Security-Policy": false, "Permissions-Policy": false, "Strict-Transport-Security": true}, "passed_count": 1}, "api": {"owasp_headers": {"X-Frame-Options": false, "X-Content-Type-Options": false, "Referrer-Policy": false, "Content-Security-Policy": false, "Permissions-Policy": false, "Strict-Transport-Security": false}, "passed_count": 0}}, "best_pass`
- **Remediation:** Configure OWASP recommended headers in middleware or reverse proxy.

### ❌ SEC-015: Admin endpoints require elevated privileges
- **Severity:** CRITICAL
- **Status:** FAILED
- **Duration:** 182.2ms
- **Applies to:** borrower, partner, lo
- **Details:** `{"admin_checks": [{"endpoint": "https://api.perenniaai.com/api/v1/purl-admin/workspaces/1/tokens", "no_auth_status": 404, "protected": false}, {"endpoint": "https://api.perenniaai.com/api/v1/purl-admin/workspaces/1", "no_auth_status": 404, "protected": false}], "ssl_warning": "SSL verification bypassed \u2014 API certificate has hostname mismatch"}`
- **Remediation:** Verify admin route middleware. Check role requirements on admin endpoints.

## Domain: crm-sync

### ⏭️ SYNC-001: Salesforce OAuth token valid
- **Severity:** CRITICAL
- **Status:** SKIPPED
- **Duration:** 0.0ms
- **Applies to:** borrower, partner, lo
- **Details:** `{"skipped": "Salesforce credentials not configured"}`

### ⏭️ SYNC-002: Field mapping configuration complete
- **Severity:** CRITICAL
- **Status:** SKIPPED
- **Duration:** 0.0ms
- **Applies to:** borrower, partner, lo
- **Details:** `{"skipped": "admin_jwt not configured"}`

### ⏭️ SYNC-013: Sync watermark advancing (not stalled)
- **Severity:** CRITICAL
- **Status:** SKIPPED
- **Duration:** 0.0ms
- **Applies to:** borrower, partner, lo
- **Details:** `{"skipped": "admin_jwt not configured"}`

## Domain: doc-sync

### ⏭️ DOC-005: Disallowed file types rejected
- **Severity:** HIGH
- **Status:** SKIPPED
- **Duration:** 0.0ms
- **Applies to:** borrower, partner, lo
- **Details:** `{"skipped": "borrower_write_token or test_workspace_id not configured"}`

### ⏭️ DOC-008: Document download authorization enforced
- **Severity:** CRITICAL
- **Status:** SKIPPED
- **Duration:** 0.0ms
- **Applies to:** borrower, partner, lo
- **Details:** `{"skipped": "borrower_a_document_id not configured"}`

## Remediation Plan

- **[CRITICAL] UA-001:** Check purl_token_service.py. Verify purl_access_tokens table. Check admin auth.
- **[CRITICAL] SEC-015:** Verify admin route middleware. Check role requirements on admin endpoints.
- **[HIGH] SEC-007:** Add security headers in middleware or reverse proxy configuration.
- **[HIGH] SEC-013:** Configure OWASP recommended headers in middleware or reverse proxy.
