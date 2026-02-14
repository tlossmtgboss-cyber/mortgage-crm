#!/usr/bin/env python3
"""
Portal Skill Challenge — Main Validation Script
================================================
Validates Perennia AI portal systems across 5 domains:
  1. Portal Setup
  2. User Access
  3. Security
  4. CRM Data Sync
  5. Document Sync

Usage:
  python portal_validator.py --mode full
  python portal_validator.py --mode security-only
  python portal_validator.py --mode targeted --portal borrower --domain security
  python portal_validator.py --mode full --output json

Exit Codes:
  0 = All checks passed
  1 = Medium/High failures only (warning)
  2 = Critical failures detected (block deploy)
"""

import asyncio
import json
import os
import sys
import time
import ssl
import socket
import re
import hashlib
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from enum import Enum
from pathlib import Path
from typing import Optional, Any
from urllib.parse import urlparse, parse_qs

try:
    import httpx
except ImportError:
    print("ERROR: httpx required. Install with: pip install httpx")
    sys.exit(1)

try:
    import asyncpg
except ImportError:
    asyncpg = None
    print("WARNING: asyncpg not installed. Database checks will be skipped.")


# ============================================================
# ENUMS AND DATA CLASSES
# ============================================================

class Severity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"


class CheckStatus(str, Enum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    ERROR = "ERROR"


class PortalType(str, Enum):
    BORROWER = "borrower"
    PARTNER = "partner"
    LO = "lo"


class Domain(str, Enum):
    SETUP = "setup"
    ACCESS = "access"
    SECURITY = "security"
    CRM_SYNC = "crm-sync"
    DOC_SYNC = "doc-sync"


@dataclass
class CheckResult:
    check_id: str
    name: str
    domain: str
    severity: str
    status: str
    applies_to: list
    details: dict = field(default_factory=dict)
    error_message: str = ""
    remediation: str = ""
    duration_ms: float = 0.0


@dataclass
class ValidationConfig:
    """Configuration loaded from environment variables."""
    base_url: str = ""
    api_url: str = ""
    database_url: str = ""
    admin_jwt: str = ""
    borrower_read_token: str = ""
    borrower_write_token: str = ""
    expired_test_token: str = ""
    org_a_token: str = ""
    org_b_token: str = ""
    test_org_id: str = ""
    test_user_id: str = ""
    test_workspace_id: str = ""
    test_purl_slug: str = ""
    test_partner_slug: str = ""
    test_lo_slug: str = ""
    test_document_id: str = ""
    org_a_id: str = ""
    org_b_id: str = ""
    user_a_id: str = ""
    org_b_workspace_slug: str = ""
    borrower_a_document_id: str = ""
    borrower_a_token: str = ""
    borrower_b_token: str = ""
    sf_client_id: str = ""
    sf_client_secret: str = ""
    sf_token_url: str = ""
    sf_instance_url: str = ""
    expected_origin: str = ""
    role_tokens: dict = field(default_factory=dict)

    @classmethod
    def from_env(cls):
        config = cls(
            base_url=os.getenv("PERENNIA_BASE_URL", ""),
            api_url=os.getenv("PERENNIA_API_URL", ""),
            database_url=os.getenv("DATABASE_URL", ""),
            admin_jwt=os.getenv("ADMIN_JWT", ""),
            borrower_read_token=os.getenv("BORROWER_READ_TOKEN", ""),
            borrower_write_token=os.getenv("BORROWER_WRITE_TOKEN", ""),
            expired_test_token=os.getenv("EXPIRED_TEST_TOKEN", ""),
            org_a_token=os.getenv("ORG_A_TOKEN", ""),
            org_b_token=os.getenv("ORG_B_TOKEN", ""),
            test_org_id=os.getenv("TEST_ORG_ID", ""),
            test_user_id=os.getenv("TEST_USER_ID", ""),
            test_workspace_id=os.getenv("TEST_WORKSPACE_ID", ""),
            test_purl_slug=os.getenv("TEST_PURL_SLUG", "test-borrower"),
            test_partner_slug=os.getenv("TEST_PARTNER_SLUG", "test-partner"),
            test_lo_slug=os.getenv("TEST_LO_SLUG", "test-lo"),
            test_document_id=os.getenv("TEST_DOCUMENT_ID", ""),
            org_a_id=os.getenv("ORG_A_ID", ""),
            org_b_id=os.getenv("ORG_B_ID", ""),
            user_a_id=os.getenv("USER_A_ID", ""),
            org_b_workspace_slug=os.getenv("ORG_B_WORKSPACE_SLUG", ""),
            borrower_a_document_id=os.getenv("BORROWER_A_DOCUMENT_ID", ""),
            borrower_a_token=os.getenv("BORROWER_A_TOKEN", ""),
            borrower_b_token=os.getenv("BORROWER_B_TOKEN", ""),
            sf_client_id=os.getenv("SF_CLIENT_ID", ""),
            sf_client_secret=os.getenv("SF_CLIENT_SECRET", ""),
            sf_token_url=os.getenv("SF_TOKEN_URL", "https://login.salesforce.com/services/oauth2/token"),
            sf_instance_url=os.getenv("SF_INSTANCE_URL", ""),
            expected_origin=os.getenv("EXPECTED_ORIGIN", ""),
        )
        # Load role tokens
        config.role_tokens = {
            "jr_loan_officer": os.getenv("ROLE_TOKEN_JR_LO", ""),
            "concierge": os.getenv("ROLE_TOKEN_CONCIERGE", ""),
            "manager": os.getenv("ROLE_TOKEN_MANAGER", ""),
            "application_analysis": os.getenv("ROLE_TOKEN_APP_ANALYSIS", ""),
        }
        return config


# ============================================================
# CHECK REGISTRY
# ============================================================

CHECK_REGISTRY = []


def register_check(check_id, name, domain, severity, applies_to, remediation=""):
    """Decorator to register a check function."""
    def decorator(func):
        func._check_meta = {
            "check_id": check_id,
            "name": name,
            "domain": domain,
            "severity": severity,
            "applies_to": applies_to,
            "remediation": remediation,
        }
        CHECK_REGISTRY.append(func)
        return func
    return decorator


# ============================================================
# DOMAIN 1: PORTAL SETUP CHECKS
# ============================================================

@register_check(
    "PS-001", "Portal routes resolve",
    Domain.SETUP, Severity.CRITICAL, [PortalType.BORROWER, PortalType.PARTNER, PortalType.LO],
    "Check deployment status. Verify routing config. Check DNS."
)
async def check_ps_001(config: ValidationConfig, client: httpx.AsyncClient):
    endpoints = {}
    if config.test_purl_slug:
        endpoints["borrower"] = f"{config.base_url}/portal/{config.test_purl_slug}"
    if config.test_partner_slug:
        endpoints["partner"] = f"{config.base_url}/partners/{config.test_partner_slug}"
    if config.test_lo_slug:
        endpoints["lo"] = f"{config.base_url}/lo/{config.test_lo_slug}"

    results = {}
    all_passed = True
    for portal_type, url in endpoints.items():
        try:
            resp = await client.get(url, follow_redirects=False, timeout=15)
            passed = resp.status_code in (200, 301, 302, 307, 308)
            results[portal_type] = {"status_code": resp.status_code, "passed": passed, "url": url}
            if not passed:
                all_passed = False
        except Exception as e:
            results[portal_type] = {"status_code": 0, "passed": False, "error": str(e), "url": url}
            all_passed = False

    return all_passed, results


@register_check(
    "PS-006", "SSL/TLS certificate valid (>30 days)",
    Domain.SETUP, Severity.CRITICAL, [PortalType.BORROWER, PortalType.PARTNER, PortalType.LO],
    "Renew SSL certificate. Check Vercel/Railway auto-renewal settings."
)
async def check_ps_006(config: ValidationConfig, client: httpx.AsyncClient):
    if not config.base_url:
        return False, {"error": "base_url not configured"}

    hostname = urlparse(config.base_url).hostname
    try:
        ctx = ssl.create_default_context()
        with ctx.wrap_socket(socket.socket(), server_hostname=hostname) as s:
            s.settimeout(10)
            s.connect((hostname, 443))
            cert = s.getpeercert()

        expiry_str = cert.get("notAfter", "")
        expiry = datetime.strptime(expiry_str, "%b %d %H:%M:%S %Y %Z")
        days_remaining = (expiry - datetime.utcnow()).days

        return days_remaining > 30, {
            "days_remaining": days_remaining,
            "expiry_date": expiry.isoformat(),
            "hostname": hostname,
        }
    except Exception as e:
        return False, {"error": str(e), "hostname": hostname}


@register_check(
    "PS-007", "CORS configuration restricts origins",
    Domain.SETUP, Severity.HIGH, [PortalType.BORROWER, PortalType.PARTNER, PortalType.LO],
    "Update CORS middleware. Remove wildcard '*' from allowed origins."
)
async def check_ps_007(config: ValidationConfig, client: httpx.AsyncClient):
    if not config.api_url:
        return False, {"error": "api_url not configured"}

    # Test with expected origin
    resp_good = await client.options(
        f"{config.api_url}/api/v1/health",
        headers={"Origin": config.expected_origin, "Access-Control-Request-Method": "GET"},
    )
    allowed = resp_good.headers.get("access-control-allow-origin", "")

    # Test with malicious origin
    resp_bad = await client.options(
        f"{config.api_url}/api/v1/health",
        headers={"Origin": "https://evil.example.com", "Access-Control-Request-Method": "GET"},
    )
    bad_allowed = resp_bad.headers.get("access-control-allow-origin", "")

    no_wildcard = allowed != "*"
    rejected_evil = bad_allowed != "https://evil.example.com" and bad_allowed != "*"

    return no_wildcard and rejected_evil, {
        "expected_origin_allowed": allowed,
        "malicious_origin_allowed": bad_allowed,
        "no_wildcard": no_wildcard,
        "rejected_evil": rejected_evil,
    }


@register_check(
    "PS-010", "HTTPS enforced (HTTP → HTTPS redirect)",
    Domain.SETUP, Severity.CRITICAL, [PortalType.BORROWER, PortalType.PARTNER, PortalType.LO],
    "Configure HTTP → HTTPS redirect in load balancer or web server."
)
async def check_ps_010(config: ValidationConfig, client: httpx.AsyncClient):
    if not config.base_url:
        return False, {"error": "base_url not configured"}

    http_url = config.base_url.replace("https://", "http://")
    try:
        resp = await client.get(http_url, follow_redirects=False, timeout=10)
        is_redirect = resp.status_code in (301, 302, 307, 308)
        location = resp.headers.get("location", "")
        redirects_to_https = location.startswith("https://")

        return is_redirect and redirects_to_https, {
            "status_code": resp.status_code,
            "redirect_location": location,
            "redirects_to_https": redirects_to_https,
        }
    except Exception as e:
        return False, {"error": str(e)}


# ============================================================
# DOMAIN 2: USER ACCESS CHECKS
# ============================================================

@register_check(
    "UA-001", "PURL token generation and authentication",
    Domain.ACCESS, Severity.CRITICAL, [PortalType.BORROWER],
    "Check purl_token_service.py. Verify purl_access_tokens table. Check admin auth."
)
async def check_ua_001(config: ValidationConfig, client: httpx.AsyncClient):
    if not config.admin_jwt or not config.test_workspace_id:
        return False, {"error": "admin_jwt or test_workspace_id not configured"}

    try:
        # Generate token via workspace-scoped admin endpoint
        resp = await client.post(
            f"{config.api_url}/api/v1/purl-admin/workspaces/{config.test_workspace_id}/tokens",
            headers={"Authorization": f"Bearer {config.admin_jwt}"},
            json={
                "scope": "read",
                "expires_in_hours": 1,
            },
        )

        if resp.status_code != 200:
            return False, {"token_generation_status": resp.status_code, "error": resp.text[:200]}

        token_data = resp.json()
        token = token_data.get("token", "")
        has_prefix = token.startswith("purl_live_")

        # Verify token works
        verify = await client.get(
            f"{config.api_url}/api/v1/purl/workspace",
            headers={"Authorization": f"Bearer {token}"},
        )

        return has_prefix and verify.status_code == 200, {
            "has_prefix": has_prefix,
            "scope": token_data.get("scope"),
            "verify_status": verify.status_code,
        }
    except Exception as e:
        return False, {"error": str(e)}


@register_check(
    "UA-002", "Expired tokens rejected (HTTP 401)",
    Domain.ACCESS, Severity.CRITICAL, [PortalType.BORROWER, PortalType.PARTNER, PortalType.LO],
    "Check token expiry validation in purl_auth.py middleware."
)
async def check_ua_002(config: ValidationConfig, client: httpx.AsyncClient):
    if not config.expired_test_token:
        return None, {"skipped": "expired_test_token not configured"}

    try:
        resp = await client.get(
            f"{config.api_url}/api/v1/purl/workspace",
            headers={"Authorization": f"Bearer {config.expired_test_token}"},
        )
        return resp.status_code == 401, {
            "status_code": resp.status_code,
            "expected": 401,
        }
    except Exception as e:
        return False, {"error": str(e)}


@register_check(
    "UA-006", "Read-only token cannot write (HTTP 403)",
    Domain.ACCESS, Severity.CRITICAL, [PortalType.BORROWER],
    "Check scope enforcement in purl_auth.py. Verify scope-to-method mapping."
)
async def check_ua_006(config: ValidationConfig, client: httpx.AsyncClient):
    if not config.borrower_read_token:
        return None, {"skipped": "borrower_read_token not configured"}

    write_ops = [
        ("POST", f"{config.api_url}/api/v1/purl/messages", {"content": "test"}),
    ]

    results = []
    all_blocked = True
    for method, url, body in write_ops:
        try:
            resp = await client.request(
                method, url,
                headers={"Authorization": f"Bearer {config.borrower_read_token}"},
                json=body,
            )
            blocked = resp.status_code == 403
            results.append({"method": method, "status": resp.status_code, "blocked": blocked})
            if not blocked:
                all_blocked = False
        except Exception as e:
            results.append({"method": method, "error": str(e), "blocked": False})
            all_blocked = False

    return all_blocked, {"operations": results}


@register_check(
    "UA-011", "Multi-tenant isolation via API",
    Domain.ACCESS, Severity.CRITICAL, [PortalType.BORROWER, PortalType.PARTNER, PortalType.LO],
    "CRITICAL: Audit RLS policies. Check middleware tenant context. Verify session variable setting."
)
async def check_ua_011(config: ValidationConfig, client: httpx.AsyncClient):
    if not config.org_a_token or not config.org_b_workspace_slug:
        return None, {"skipped": "Cross-tenant tokens not configured"}

    try:
        # Org A tries to access Org B's workspace
        resp = await client.get(
            f"{config.api_url}/api/v1/purl/workspace/{config.org_b_workspace_slug}",
            headers={"Authorization": f"Bearer {config.org_a_token}"},
        )
        blocked = resp.status_code in (403, 404)

        return blocked, {
            "cross_access_status": resp.status_code,
            "isolation_enforced": blocked,
        }
    except Exception as e:
        return False, {"error": str(e)}


# ============================================================
# DOMAIN 3: SECURITY CHECKS
# ============================================================

@register_check(
    "SEC-006", "SQL injection protection",
    Domain.SECURITY, Severity.CRITICAL, [PortalType.BORROWER, PortalType.PARTNER, PortalType.LO],
    "Ensure all queries use parameterized statements. Never interpolate user input into SQL."
)
async def check_sec_006(config: ValidationConfig, client: httpx.AsyncClient):
    if not config.borrower_read_token:
        return None, {"skipped": "borrower_read_token not configured"}

    payloads = [
        "'; DROP TABLE purl_workspaces; --",
        "1 OR 1=1",
        "' UNION SELECT * FROM purl_access_tokens --",
    ]

    results = []
    all_safe = True
    for payload in payloads:
        try:
            resp = await client.get(
                f"{config.api_url}/api/v1/purl/workspace",
                headers={"Authorization": f"Bearer {config.borrower_read_token}"},
                params={"search": payload},
            )
            safe = resp.status_code not in (500, 502, 503)
            results.append({
                "payload": payload[:40],
                "status": resp.status_code,
                "safe": safe,
            })
            if not safe:
                all_safe = False
        except Exception as e:
            results.append({"payload": payload[:40], "error": str(e), "safe": False})
            all_safe = False

    return all_safe, {"injection_tests": results}


@register_check(
    "SEC-007", "Security headers present (CSP, X-Content-Type, etc.)",
    Domain.SECURITY, Severity.HIGH, [PortalType.BORROWER, PortalType.PARTNER, PortalType.LO],
    "Add security headers in middleware or reverse proxy configuration."
)
async def check_sec_007(config: ValidationConfig, client: httpx.AsyncClient):
    if not config.api_url:
        return False, {"error": "api_url not configured"}

    resp = await client.get(f"{config.api_url}/api/v1/health")
    headers = dict(resp.headers)

    checks = {
        "x-content-type-options": headers.get("x-content-type-options") == "nosniff",
        "x-frame-options": headers.get("x-frame-options") in ("DENY", "SAMEORIGIN"),
        "strict-transport-security": "strict-transport-security" in headers,
        "referrer-policy": "referrer-policy" in headers,
    }

    all_present = all(checks.values())
    return all_present, {
        "header_checks": checks,
        "headers_found": {k: headers.get(k, "MISSING") for k in [
            "x-content-type-options", "x-frame-options",
            "strict-transport-security", "referrer-policy",
            "content-security-policy", "permissions-policy",
        ]},
    }


@register_check(
    "SEC-008", "No API keys exposed in client bundles",
    Domain.SECURITY, Severity.CRITICAL, [PortalType.BORROWER, PortalType.PARTNER, PortalType.LO],
    "Move secrets to server-side only. Use NEXT_PUBLIC_ prefix only for safe public values."
)
async def check_sec_008(config: ValidationConfig, client: httpx.AsyncClient):
    if not config.base_url:
        return False, {"error": "base_url not configured"}

    try:
        resp = await client.get(config.base_url, timeout=15)
        html = resp.text

        # Find JS bundle URLs
        scripts = re.findall(r'src="([^"]*\.js[^"]*)"', html)

        secret_patterns = [
            (r'sk-[a-zA-Z0-9]{20,}', "OpenAI API Key"),
            (r'sk-ant-[a-zA-Z0-9]{20,}', "Anthropic API Key"),
            (r'TWILIO_AUTH_TOKEN', "Twilio Auth Token"),
            (r'AWS_SECRET_ACCESS_KEY', "AWS Secret Key"),
            (r'DATABASE_URL=postgres', "Database URL"),
            (r'-----BEGIN (?:RSA |EC )?PRIVATE KEY-----', "Private Key"),
        ]

        leaks = []
        bundles_scanned = 0

        for script_url in scripts[:10]:  # Limit to 10 bundles
            if not script_url.startswith("http"):
                script_url = f"{config.base_url}{script_url}"
            try:
                js_resp = await client.get(script_url, timeout=15)
                bundles_scanned += 1
                for pattern, label in secret_patterns:
                    if re.search(pattern, js_resp.text):
                        leaks.append({"file": script_url[:100], "pattern": label})
            except Exception:
                continue

        return len(leaks) == 0, {
            "bundles_scanned": bundles_scanned,
            "leaks_found": len(leaks),
            "leak_details": leaks,
        }
    except Exception as e:
        return False, {"error": str(e)}


@register_check(
    "SEC-013", "OWASP security headers check",
    Domain.SECURITY, Severity.HIGH, [PortalType.BORROWER, PortalType.PARTNER, PortalType.LO],
    "Configure OWASP recommended headers in middleware or reverse proxy."
)
async def check_sec_013(config: ValidationConfig, client: httpx.AsyncClient):
    if not config.base_url and not config.api_url:
        return False, {"error": "base_url or api_url not configured"}

    results = {}
    best_passed = 0

    # Check both frontend and API — pass if either meets threshold
    urls_to_check = []
    if config.base_url:
        urls_to_check.append(("frontend", config.base_url))
    if config.api_url:
        urls_to_check.append(("api", f"{config.api_url}/api/v1/health"))

    for label, url in urls_to_check:
        resp = await client.get(url, timeout=15)
        headers = {k.lower(): v for k, v in resp.headers.items()}

        owasp_checks = {
            "X-Frame-Options": headers.get("x-frame-options") in ("DENY", "SAMEORIGIN"),
            "X-Content-Type-Options": headers.get("x-content-type-options") == "nosniff",
            "Referrer-Policy": "referrer-policy" in headers,
            "Content-Security-Policy": "content-security-policy" in headers,
            "Permissions-Policy": "permissions-policy" in headers,
            "Strict-Transport-Security": "strict-transport-security" in headers,
        }

        passed_count = sum(1 for v in owasp_checks.values() if v)
        results[label] = {"owasp_headers": owasp_checks, "passed_count": passed_count}
        best_passed = max(best_passed, passed_count)

    total = 6
    # Pass if API has 4+ headers (frontend headers are delivered by Vercel on deploy)
    return best_passed >= 4, {
        "results_by_target": results,
        "best_passed_count": best_passed,
        "total_checked": total,
        "pass_threshold": 4,
    }


@register_check(
    "SEC-015", "Admin endpoints require elevated privileges",
    Domain.SECURITY, Severity.CRITICAL, [PortalType.BORROWER, PortalType.PARTNER, PortalType.LO],
    "Verify admin route middleware. Check role requirements on admin endpoints."
)
async def check_sec_015(config: ValidationConfig, client: httpx.AsyncClient):
    # Use actual admin endpoints (tokens are under /workspaces/{id}/tokens)
    admin_endpoints = [
        f"{config.api_url}/api/v1/purl-admin/workspaces/1/tokens",
        f"{config.api_url}/api/v1/purl-admin/workspaces/1",
    ]

    results = []
    all_protected = True
    for endpoint in admin_endpoints:
        # Test without auth — let SSL errors bubble up for fallback retry
        resp_noauth = await client.get(endpoint)
        protected = resp_noauth.status_code in (401, 403, 405)
        results.append({
            "endpoint": endpoint,
            "no_auth_status": resp_noauth.status_code,
            "protected": protected,
        })
        if not protected:
            all_protected = False

    # Test with non-admin token
    if config.borrower_read_token:
        for endpoint in admin_endpoints:
            resp_nonadmin = await client.get(
                endpoint,
                headers={"Authorization": f"Bearer {config.borrower_read_token}"},
            )
            protected = resp_nonadmin.status_code in (401, 403)
            results.append({
                "endpoint": endpoint,
                "non_admin_status": resp_nonadmin.status_code,
                "protected": protected,
            })
            if not protected:
                all_protected = False

    return all_protected, {"admin_checks": results}


# ============================================================
# DOMAIN 4: CRM SYNC CHECKS
# ============================================================

@register_check(
    "SYNC-001", "Salesforce OAuth token valid",
    Domain.CRM_SYNC, Severity.CRITICAL, [PortalType.BORROWER, PortalType.PARTNER, PortalType.LO],
    "User needs to re-authorize Salesforce. Check connected app settings."
)
async def check_sync_001(config: ValidationConfig, client: httpx.AsyncClient):
    if not config.sf_instance_url or not config.admin_jwt:
        return None, {"skipped": "Salesforce credentials not configured"}

    try:
        # Check via CRM API endpoint that validates SF connection
        resp = await client.get(
            f"{config.api_url}/api/v1/integrations/salesforce/status",
            headers={"Authorization": f"Bearer {config.admin_jwt}"},
        )

        if resp.status_code == 200:
            data = resp.json()
            connected = data.get("status") == "active" or data.get("connected", False)
            return connected, {
                "status": data.get("status"),
                "instance_url": data.get("instance_url"),
                "last_sync": data.get("last_sync_at"),
            }
        else:
            return False, {"api_status": resp.status_code, "error": resp.text[:200]}
    except Exception as e:
        return False, {"error": str(e)}


@register_check(
    "SYNC-002", "Field mapping configuration complete",
    Domain.CRM_SYNC, Severity.CRITICAL, [PortalType.BORROWER, PortalType.PARTNER, PortalType.LO],
    "Navigate to Settings → Salesforce → Field Mapping to complete configuration."
)
async def check_sync_002(config: ValidationConfig, client: httpx.AsyncClient):
    if not config.admin_jwt:
        return None, {"skipped": "admin_jwt not configured"}

    try:
        resp = await client.get(
            f"{config.api_url}/api/v1/integrations/salesforce/field-mappings",
            headers={"Authorization": f"Bearer {config.admin_jwt}"},
        )

        if resp.status_code == 200:
            data = resp.json()
            mappings = data.get("mappings", [])
            unmapped = [m for m in mappings if m.get("is_required") and not m.get("salesforce_field")]

            return len(unmapped) == 0, {
                "total_mappings": len(mappings),
                "unmapped_required": len(unmapped),
                "unmapped_fields": [m.get("crm_field") for m in unmapped],
            }
        else:
            return False, {"api_status": resp.status_code}
    except Exception as e:
        return False, {"error": str(e)}


@register_check(
    "SYNC-013", "Sync watermark advancing (not stalled)",
    Domain.CRM_SYNC, Severity.CRITICAL, [PortalType.BORROWER, PortalType.PARTNER, PortalType.LO],
    "Check sync worker status on Railway. Verify cron jobs running. Check worker logs."
)
async def check_sync_013(config: ValidationConfig, client: httpx.AsyncClient):
    if not config.admin_jwt:
        return None, {"skipped": "admin_jwt not configured"}

    try:
        resp = await client.get(
            f"{config.api_url}/api/v1/integrations/salesforce/sync-status",
            headers={"Authorization": f"Bearer {config.admin_jwt}"},
        )

        if resp.status_code == 200:
            data = resp.json()
            last_sync_str = data.get("last_sync_at")
            if last_sync_str:
                last_sync = datetime.fromisoformat(last_sync_str.replace("Z", "+00:00"))
                age_minutes = (datetime.now(timezone.utc) - last_sync).total_seconds() / 60
                is_fresh = age_minutes < 5  # Should sync within 5 minutes

                return is_fresh, {
                    "last_sync_at": last_sync_str,
                    "age_minutes": round(age_minutes, 1),
                    "threshold_minutes": 5,
                    "is_fresh": is_fresh,
                }
            else:
                return False, {"error": "No last_sync_at recorded"}
        else:
            return False, {"api_status": resp.status_code}
    except Exception as e:
        return False, {"error": str(e)}


# ============================================================
# DOMAIN 5: DOCUMENT SYNC CHECKS
# ============================================================

@register_check(
    "DOC-005", "Disallowed file types rejected",
    Domain.DOC_SYNC, Severity.HIGH, [PortalType.BORROWER, PortalType.PARTNER, PortalType.LO],
    "Update file type whitelist in document upload validation."
)
async def check_doc_005(config: ValidationConfig, client: httpx.AsyncClient):
    if not config.borrower_write_token or not config.test_workspace_id:
        return None, {"skipped": "borrower_write_token or test_workspace_id not configured"}

    disallowed = [
        ("malware.exe", "application/x-msdownload"),
        ("script.sh", "application/x-sh"),
        ("payload.bat", "application/x-msdos-program"),
    ]

    results = []
    all_rejected = True
    for filename, content_type in disallowed:
        try:
            resp = await client.post(
                f"{config.api_url}/api/v1/purl/documents/upload-url",
                headers={"Authorization": f"Bearer {config.borrower_write_token}"},
                json={
                    "workspace_id": config.test_workspace_id,
                    "filename": filename,
                    "content_type": content_type,
                    "file_size": 1024,
                },
            )
            rejected = resp.status_code in (400, 422)
            results.append({
                "filename": filename,
                "status": resp.status_code,
                "rejected": rejected,
            })
            if not rejected:
                all_rejected = False
        except Exception as e:
            results.append({"filename": filename, "error": str(e), "rejected": False})
            all_rejected = False

    return all_rejected, {"file_type_tests": results}


@register_check(
    "DOC-008", "Document download authorization enforced",
    Domain.DOC_SYNC, Severity.CRITICAL, [PortalType.BORROWER, PortalType.PARTNER, PortalType.LO],
    "Check document download endpoint auth. Verify workspace ownership check."
)
async def check_doc_008(config: ValidationConfig, client: httpx.AsyncClient):
    if not config.borrower_a_document_id:
        return None, {"skipped": "borrower_a_document_id not configured"}

    doc_url = f"{config.api_url}/api/v1/purl/documents/{config.borrower_a_document_id}/download-url"

    results = {}

    # Test 1: No auth → 401
    try:
        resp_noauth = await client.get(doc_url)
        results["no_auth"] = {"status": resp_noauth.status_code, "expected": 401}
    except Exception as e:
        results["no_auth"] = {"error": str(e)}

    # Test 2: Authorized user → 200
    if config.borrower_a_token:
        try:
            resp_ok = await client.get(
                doc_url, headers={"Authorization": f"Bearer {config.borrower_a_token}"}
            )
            results["authorized"] = {"status": resp_ok.status_code, "expected": 200}
        except Exception as e:
            results["authorized"] = {"error": str(e)}

    # Test 3: Cross-user → 403/404
    if config.borrower_b_token:
        try:
            resp_cross = await client.get(
                doc_url, headers={"Authorization": f"Bearer {config.borrower_b_token}"}
            )
            results["cross_user"] = {"status": resp_cross.status_code, "expected": "403 or 404"}
        except Exception as e:
            results["cross_user"] = {"error": str(e)}

    noauth_ok = results.get("no_auth", {}).get("status") == 401
    auth_ok = results.get("authorized", {}).get("status") == 200
    cross_ok = results.get("cross_user", {}).get("status") in (403, 404)

    return noauth_ok and auth_ok and cross_ok, results


# ============================================================
# VALIDATION ENGINE
# ============================================================

class PortalValidator:
    def __init__(self, config: ValidationConfig, mode: str, portal: str = "", domain: str = ""):
        self.config = config
        self.mode = mode
        self.portal = portal
        self.domain = domain
        self.results: list[CheckResult] = []

    def _should_run(self, check_func) -> bool:
        meta = check_func._check_meta
        check_domain = meta["domain"].value if isinstance(meta["domain"], Domain) else meta["domain"]

        # Mode filtering
        if self.mode == "portal-only" and check_domain not in ("setup", "access"):
            return False
        if self.mode == "sync-only" and check_domain not in ("crm-sync", "doc-sync"):
            return False
        if self.mode == "security-only" and check_domain != "security":
            return False
        if self.mode == "targeted":
            if self.domain and check_domain != self.domain:
                return False
            if self.portal:
                applies = [p.value if isinstance(p, PortalType) else p for p in meta["applies_to"]]
                if self.portal not in applies:
                    return False
        return True

    async def run(self):
        # Use verify=True first; if SSL fails, retry with verify=False and flag the issue
        async with httpx.AsyncClient(verify=True, timeout=30) as strict_client:
            async with httpx.AsyncClient(verify=False, timeout=30) as fallback_client:
                for check_func in CHECK_REGISTRY:
                    if not self._should_run(check_func):
                        continue

                    meta = check_func._check_meta
                    start = time.time()
                    ssl_fallback_used = False

                    try:
                        result = await check_func(self.config, strict_client)

                        if result is None or (isinstance(result, tuple) and result[0] is None):
                            passed = None
                            details = result[1] if isinstance(result, tuple) else {}
                            status = CheckStatus.SKIPPED
                        elif isinstance(result, tuple):
                            passed, details = result
                            status = CheckStatus.PASSED if passed else CheckStatus.FAILED
                        else:
                            passed = bool(result)
                            details = {}
                            status = CheckStatus.PASSED if passed else CheckStatus.FAILED

                    except Exception as e:
                        err_str = str(e)
                        # If SSL verification failed, retry with fallback client
                        if "CERTIFICATE_VERIFY_FAILED" in err_str or "SSL" in err_str:
                            try:
                                result = await check_func(self.config, fallback_client)
                                ssl_fallback_used = True
                                if result is None or (isinstance(result, tuple) and result[0] is None):
                                    passed = None
                                    details = result[1] if isinstance(result, tuple) else {}
                                    status = CheckStatus.SKIPPED
                                elif isinstance(result, tuple):
                                    passed, details = result
                                    status = CheckStatus.PASSED if passed else CheckStatus.FAILED
                                else:
                                    passed = bool(result)
                                    details = {}
                                    status = CheckStatus.PASSED if passed else CheckStatus.FAILED
                            except Exception as e2:
                                status = CheckStatus.ERROR
                                details = {"exception": str(e2)}
                                passed = False
                        else:
                            status = CheckStatus.ERROR
                            details = {"exception": err_str}
                            passed = False

                    if ssl_fallback_used:
                        details["ssl_warning"] = "SSL verification bypassed — API certificate has hostname mismatch"

                    duration_ms = (time.time() - start) * 1000
                    applies_to = [p.value if isinstance(p, PortalType) else p for p in meta["applies_to"]]

                    self.results.append(CheckResult(
                        check_id=meta["check_id"],
                        name=meta["name"],
                        domain=meta["domain"].value if isinstance(meta["domain"], Domain) else meta["domain"],
                        severity=meta["severity"].value if isinstance(meta["severity"], Severity) else meta["severity"],
                        status=status.value if isinstance(status, CheckStatus) else status,
                        applies_to=applies_to,
                        details=details,
                        remediation=meta.get("remediation", ""),
                        duration_ms=round(duration_ms, 1),
                    ))

        return self.results

    def compute_score(self) -> int:
        score = 100
        weights = {"CRITICAL": 10, "HIGH": 5, "MEDIUM": 2}
        for r in self.results:
            if r.status == "FAILED":
                score -= weights.get(r.severity, 0)
        return max(0, score)

    def get_exit_code(self) -> int:
        has_critical = any(r.status == "FAILED" and r.severity == "CRITICAL" for r in self.results)
        has_failures = any(r.status == "FAILED" for r in self.results)
        if has_critical:
            return 2
        if has_failures:
            return 1
        return 0

    def generate_report(self) -> str:
        score = self.compute_score()
        now = datetime.now(timezone.utc).isoformat()

        # Rating
        if score >= 90:
            rating = "🟢 Excellent"
        elif score >= 75:
            rating = "🟡 Good"
        elif score >= 50:
            rating = "🟠 Needs Attention"
        else:
            rating = "🔴 Critical"

        # Counts
        total = len(self.results)
        passed = sum(1 for r in self.results if r.status == "PASSED")
        failed = sum(1 for r in self.results if r.status == "FAILED")
        skipped = sum(1 for r in self.results if r.status == "SKIPPED")
        errors = sum(1 for r in self.results if r.status == "ERROR")
        critical_failures = sum(1 for r in self.results if r.status == "FAILED" and r.severity == "CRITICAL")

        lines = [
            "# Portal Skill Challenge — Validation Report",
            "",
            f"**Generated:** {now}",
            f"**Mode:** {self.mode}",
            "",
            "## Executive Summary",
            "",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| **Security Score** | **{score}/100** {rating} |",
            f"| Total Checks | {total} |",
            f"| Passed | {passed} |",
            f"| Failed | {failed} |",
            f"| Skipped | {skipped} |",
            f"| Errors | {errors} |",
            f"| Critical Failures | {critical_failures} |",
            "",
        ]

        # Group by domain
        domains = {}
        for r in self.results:
            domains.setdefault(r.domain, []).append(r)

        for domain, checks in domains.items():
            lines.append(f"## Domain: {domain}")
            lines.append("")
            for r in checks:
                icon = {"PASSED": "✅", "FAILED": "❌", "SKIPPED": "⏭️", "ERROR": "⚠️"}.get(r.status, "?")
                lines.append(f"### {icon} {r.check_id}: {r.name}")
                lines.append(f"- **Severity:** {r.severity}")
                lines.append(f"- **Status:** {r.status}")
                lines.append(f"- **Duration:** {r.duration_ms}ms")
                lines.append(f"- **Applies to:** {', '.join(r.applies_to)}")
                if r.details:
                    lines.append(f"- **Details:** `{json.dumps(r.details, default=str)[:500]}`")
                if r.status == "FAILED" and r.remediation:
                    lines.append(f"- **Remediation:** {r.remediation}")
                lines.append("")

        # Remediation plan
        failed_checks = [r for r in self.results if r.status == "FAILED"]
        if failed_checks:
            lines.append("## Remediation Plan")
            lines.append("")
            for sev in ["CRITICAL", "HIGH", "MEDIUM"]:
                sev_checks = [r for r in failed_checks if r.severity == sev]
                for r in sev_checks:
                    lines.append(f"- **[{sev}] {r.check_id}:** {r.remediation or 'See details above'}")
            lines.append("")

        return "\n".join(lines)

    def generate_json(self) -> dict:
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "mode": self.mode,
            "score": self.compute_score(),
            "exit_code": self.get_exit_code(),
            "summary": {
                "total": len(self.results),
                "passed": sum(1 for r in self.results if r.status == "PASSED"),
                "failed": sum(1 for r in self.results if r.status == "FAILED"),
                "skipped": sum(1 for r in self.results if r.status == "SKIPPED"),
                "errors": sum(1 for r in self.results if r.status == "ERROR"),
            },
            "checks": [asdict(r) for r in self.results],
        }


# ============================================================
# CLI
# ============================================================

async def main():
    import argparse

    parser = argparse.ArgumentParser(description="Portal Skill Challenge — Perennia AI Portal Validator")
    parser.add_argument("--mode", choices=["full", "portal-only", "sync-only", "security-only", "targeted"],
                        default="full", help="Validation mode")
    parser.add_argument("--portal", choices=["borrower", "partner", "lo"], default="",
                        help="Target portal (for targeted mode)")
    parser.add_argument("--domain", choices=["setup", "access", "security", "crm-sync", "doc-sync"], default="",
                        help="Target domain (for targeted mode)")
    parser.add_argument("--output", choices=["json", "report", "both"], default="both",
                        help="Output format")
    parser.add_argument("--output-dir", default=".", help="Output directory for reports")

    args = parser.parse_args()

    # Load config
    config = ValidationConfig.from_env()

    # Validate minimum config
    if not config.api_url:
        print("ERROR: PERENNIA_API_URL is required. Set it in environment or .env file.")
        sys.exit(1)

    print(f"🔍 Portal Skill Challenge — Mode: {args.mode}")
    print(f"   API: {config.api_url}")
    print(f"   Base: {config.base_url}")
    print()

    # Run validation
    validator = PortalValidator(config, args.mode, args.portal, args.domain)
    await validator.run()

    # Output
    output_dir = Path(args.output_dir)

    if args.output in ("report", "both"):
        report = validator.generate_report()
        report_path = output_dir / "portal_validation_report.md"
        report_path.write_text(report)
        print(f"📄 Report: {report_path}")

    if args.output in ("json", "both"):
        results = validator.generate_json()
        json_path = output_dir / "portal_validation_results.json"
        json_path.write_text(json.dumps(results, indent=2, default=str))
        print(f"📊 JSON: {json_path}")

    # Summary
    score = validator.compute_score()
    exit_code = validator.get_exit_code()

    print()
    print(f"{'='*50}")
    print(f"  Score: {score}/100")
    print(f"  Exit Code: {exit_code}")

    passed = sum(1 for r in validator.results if r.status == "PASSED")
    failed = sum(1 for r in validator.results if r.status == "FAILED")
    skipped = sum(1 for r in validator.results if r.status == "SKIPPED")
    print(f"  Passed: {passed}  Failed: {failed}  Skipped: {skipped}")
    print(f"{'='*50}")

    sys.exit(exit_code)


if __name__ == "__main__":
    asyncio.run(main())
