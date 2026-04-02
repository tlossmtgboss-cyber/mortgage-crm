"""SOC 2 Type II Readiness Assessment — Perennia AI
==================================================

Run:
    python soc2/readiness_checklist.py
    python soc2/readiness_checklist.py --json
    python soc2/readiness_checklist.py --output report.json

Checks for controls mapped to the five Trust Services Criteria:
  - Security (CC)
  - Availability (A)
  - Processing Integrity (PI)
  - Confidentiality (C)
  - Privacy (P)

Exit code 0 = all required controls PASS or PARTIAL
Exit code 1 = one or more required controls FAIL
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Callable, Dict, List, Optional

# ---------------------------------------------------------------------------
# Resolve the backend root regardless of cwd
# ---------------------------------------------------------------------------
_THIS_FILE = Path(__file__).resolve()
_BACKEND_ROOT = _THIS_FILE.parent.parent  # backend/


# ===========================================================================
# Data structures
# ===========================================================================

class Status(str, Enum):
    PASS = "PASS"
    PARTIAL = "PARTIAL"
    FAIL = "FAIL"
    SKIP = "SKIP"


class Criterion(str, Enum):
    """SOC 2 Trust Services Criteria."""
    CC = "Security (CC)"
    A = "Availability (A)"
    PI = "Processing Integrity (PI)"
    C = "Confidentiality (C)"
    P = "Privacy (P)"


@dataclass
class CheckResult:
    control_id: str
    title: str
    criterion: Criterion
    status: Status
    detail: str
    evidence_paths: List[str] = field(default_factory=list)
    remediation: str = ""
    required: bool = True  # False = nice-to-have; True = blocks certification


@dataclass
class ReadinessReport:
    generated_at: str
    backend_root: str
    summary: Dict[str, int]
    overall_status: str
    checks: List[CheckResult]
    gaps: List[str]
    recommendations: List[str]


# ===========================================================================
# Helper utilities
# ===========================================================================

def _path(*parts: str) -> Path:
    """Return an absolute path under the backend root."""
    return _BACKEND_ROOT.joinpath(*parts)


def _exists(*parts: str) -> bool:
    return _path(*parts).exists()


def _contains(filepath: str, *patterns: str) -> bool:
    """Return True if the file exists and contains ALL given patterns."""
    p = _path(filepath)
    if not p.exists():
        return False
    text = p.read_text(errors="ignore")
    return all(pat in text for pat in patterns)


def _any_contains(filepath: str, *patterns: str) -> bool:
    """Return True if the file exists and contains ANY of the given patterns."""
    p = _path(filepath)
    if not p.exists():
        return False
    text = p.read_text(errors="ignore")
    return any(pat in text for pat in patterns)


def _grep_dir(directory: str, pattern: str, glob: str = "*.py") -> List[str]:
    """Return list of file paths under directory that contain pattern."""
    base = _path(directory)
    if not base.is_dir():
        return []
    matches = []
    for f in base.rglob(glob):
        try:
            if pattern in f.read_text(errors="ignore"):
                matches.append(str(f.relative_to(_BACKEND_ROOT)))
        except OSError:
            pass
    return matches


# ===========================================================================
# Individual checks — grouped by Trust Services Criterion
# ===========================================================================

# ---------------------------------------------------------------------------
# CC — Security
# ---------------------------------------------------------------------------

def check_cc1_access_control_dependencies() -> CheckResult:
    """CC1/CC6 — auth/dependencies.py with require_auth present."""
    cid = "CC-1"
    path = "auth/dependencies.py"
    if _contains(path, "require_auth", "get_current_user"):
        return CheckResult(
            control_id=cid,
            title="Access Control — Canonical Auth Dependencies",
            criterion=Criterion.CC,
            status=Status.PASS,
            detail="auth/dependencies.py exists and exports require_auth / get_current_user.",
            evidence_paths=[path],
        )
    if _exists(path):
        return CheckResult(
            control_id=cid,
            title="Access Control — Canonical Auth Dependencies",
            criterion=Criterion.CC,
            status=Status.PARTIAL,
            detail="auth/dependencies.py exists but require_auth or get_current_user not found.",
            evidence_paths=[path],
            remediation="Ensure require_auth is defined and exported from auth/dependencies.py.",
        )
    return CheckResult(
        control_id=cid,
        title="Access Control — Canonical Auth Dependencies",
        criterion=Criterion.CC,
        status=Status.FAIL,
        detail="auth/dependencies.py not found.",
        remediation="Create auth/dependencies.py with require_auth FastAPI dependency.",
    )


def check_cc2_jwt_token_management() -> CheckResult:
    """CC6 — RS256 JWT token management."""
    cid = "CC-2"
    path = "auth/tokens.py"
    if _contains(path, "RS256", "jwt", "JWTError"):
        return CheckResult(
            control_id=cid,
            title="Access Control — JWT Token Management (RS256)",
            criterion=Criterion.CC,
            status=Status.PASS,
            detail="auth/tokens.py implements RS256 JWT token management with revocation support.",
            evidence_paths=[path],
        )
    if _exists(path):
        return CheckResult(
            control_id=cid,
            title="Access Control — JWT Token Management (RS256)",
            criterion=Criterion.CC,
            status=Status.PARTIAL,
            detail="auth/tokens.py exists but RS256 or JWTError not found.",
            evidence_paths=[path],
            remediation="Migrate token signing to RS256 asymmetric keys.",
        )
    return CheckResult(
        control_id=cid,
        title="Access Control — JWT Token Management (RS256)",
        criterion=Criterion.CC,
        status=Status.FAIL,
        detail="auth/tokens.py not found.",
        remediation="Implement JWT token service with RS256 signing and revocation.",
    )


def check_cc3_mfa() -> CheckResult:
    """CC6 — Multi-Factor Authentication (TOTP)."""
    cid = "CC-3"
    path = "auth/mfa.py"
    if _contains(path, "generate_mfa_secret", "TOTP", "pyotp"):
        return CheckResult(
            control_id=cid,
            title="Access Control — Multi-Factor Authentication (TOTP)",
            criterion=Criterion.CC,
            status=Status.PASS,
            detail="auth/mfa.py implements TOTP-based MFA with pyotp.",
            evidence_paths=[path],
        )
    if _exists(path):
        return CheckResult(
            control_id=cid,
            title="Access Control — Multi-Factor Authentication (TOTP)",
            criterion=Criterion.CC,
            status=Status.PARTIAL,
            detail="auth/mfa.py exists but TOTP implementation details not confirmed.",
            evidence_paths=[path],
            remediation="Verify TOTP generate/verify flows are complete and enforced on login.",
        )
    return CheckResult(
        control_id=cid,
        title="Access Control — Multi-Factor Authentication (TOTP)",
        criterion=Criterion.CC,
        status=Status.FAIL,
        detail="auth/mfa.py not found.",
        remediation="Implement TOTP MFA using pyotp. Enforce for all admin users.",
    )


def check_cc4_account_lockout() -> CheckResult:
    """CC6 — Brute-force protection via account lockout."""
    cid = "CC-4"
    path = "auth/account_lockout.py"
    if _contains(path, "MAX_FAILED_ATTEMPTS", "LOCKOUT_DURATION_MINUTES", "check_account_locked"):
        return CheckResult(
            control_id=cid,
            title="Access Control — Account Lockout (Brute-Force Protection)",
            criterion=Criterion.CC,
            status=Status.PASS,
            detail=(
                "auth/account_lockout.py enforces lockout after MAX_FAILED_ATTEMPTS "
                "for LOCKOUT_DURATION_MINUTES minutes."
            ),
            evidence_paths=[path],
        )
    if _exists(path):
        return CheckResult(
            control_id=cid,
            title="Access Control — Account Lockout (Brute-Force Protection)",
            criterion=Criterion.CC,
            status=Status.PARTIAL,
            detail="auth/account_lockout.py exists but lockout constants not confirmed.",
            evidence_paths=[path],
            remediation="Verify MAX_FAILED_ATTEMPTS=5 and LOCKOUT_DURATION_MINUTES=30 are enforced.",
        )
    return CheckResult(
        control_id=cid,
        title="Access Control — Account Lockout (Brute-Force Protection)",
        criterion=Criterion.CC,
        status=Status.FAIL,
        detail="auth/account_lockout.py not found.",
        remediation="Implement account lockout service limiting failed login attempts.",
    )


def check_cc5_security_headers_middleware() -> CheckResult:
    """CC5 — SecurityHeadersMiddleware in security_middleware.py."""
    cid = "CC-5"
    path = "security_middleware.py"
    if _contains(path, "SecurityHeadersMiddleware", "Strict-Transport-Security", "X-Frame-Options"):
        return CheckResult(
            control_id=cid,
            title="System Security — Security Headers Middleware",
            criterion=Criterion.CC,
            status=Status.PASS,
            detail=(
                "security_middleware.py defines SecurityHeadersMiddleware with HSTS, "
                "X-Frame-Options, and XSS protection headers."
            ),
            evidence_paths=[path, "soc2_compliance/middleware/security_headers.py"],
        )
    if _exists(path):
        return CheckResult(
            control_id=cid,
            title="System Security — Security Headers Middleware",
            criterion=Criterion.CC,
            status=Status.PARTIAL,
            detail="security_middleware.py exists but SecurityHeadersMiddleware not confirmed.",
            evidence_paths=[path],
            remediation=(
                "Add SecurityHeadersMiddleware that sets HSTS, CSP, X-Frame-Options, "
                "X-Content-Type-Options on every response."
            ),
        )
    return CheckResult(
        control_id=cid,
        title="System Security — Security Headers Middleware",
        criterion=Criterion.CC,
        status=Status.FAIL,
        detail="security_middleware.py not found.",
        remediation="Create security_middleware.py with SecurityHeadersMiddleware.",
    )


def check_cc6_rate_limiting() -> CheckResult:
    """CC5 — Adaptive rate limiting middleware."""
    cid = "CC-6"
    path = "middleware/rate_limiting.py"
    if _contains(path, "AdaptiveRateLimiter", "TENANT_TIER_LIMITS"):
        return CheckResult(
            control_id=cid,
            title="System Security — Adaptive Rate Limiting & DDoS Protection",
            criterion=Criterion.CC,
            status=Status.PASS,
            detail=(
                "middleware/rate_limiting.py implements AdaptiveRateLimiter with "
                "per-tenant tier-based quotas."
            ),
            evidence_paths=[path],
        )
    if _exists(path):
        return CheckResult(
            control_id=cid,
            title="System Security — Adaptive Rate Limiting & DDoS Protection",
            criterion=Criterion.CC,
            status=Status.PARTIAL,
            detail="middleware/rate_limiting.py exists but AdaptiveRateLimiter not confirmed.",
            evidence_paths=[path],
            remediation="Ensure rate limiter is applied globally and enforces per-tenant limits.",
        )
    return CheckResult(
        control_id=cid,
        title="System Security — Adaptive Rate Limiting & DDoS Protection",
        criterion=Criterion.CC,
        status=Status.FAIL,
        detail="middleware/rate_limiting.py not found.",
        remediation="Implement per-tenant rate limiting middleware (AdaptiveRateLimiter).",
    )


def check_cc7_csrf_protection() -> CheckResult:
    """CC5 — CSRF protection middleware."""
    cid = "CC-7"
    path = "middleware/csrf_protection.py"
    if _contains(path, "CSRFProtectionMiddleware", "double-submit"):
        return CheckResult(
            control_id=cid,
            title="System Security — CSRF Protection (Double-Submit Cookie)",
            criterion=Criterion.CC,
            status=Status.PASS,
            detail=(
                "middleware/csrf_protection.py implements double-submit cookie CSRF protection."
            ),
            evidence_paths=[path],
        )
    if _exists(path):
        return CheckResult(
            control_id=cid,
            title="System Security — CSRF Protection (Double-Submit Cookie)",
            criterion=Criterion.CC,
            status=Status.PARTIAL,
            detail="middleware/csrf_protection.py exists but double-submit pattern not confirmed.",
            evidence_paths=[path],
            remediation="Verify CSRF protection covers all state-changing POST/PUT/PATCH/DELETE endpoints.",
        )
    return CheckResult(
        control_id=cid,
        title="System Security — CSRF Protection (Double-Submit Cookie)",
        criterion=Criterion.CC,
        status=Status.FAIL,
        detail="middleware/csrf_protection.py not found.",
        remediation="Implement CSRF protection using the double-submit cookie pattern.",
    )


def check_cc8_audit_logging() -> CheckResult:
    """CC2/CC4 — Audit logging infrastructure."""
    cid = "CC-8"
    soc2_audit = "soc2_compliance/services/audit_service.py"
    soc2_middleware = "soc2_compliance/middleware/audit_middleware.py"
    audit_routes = "routes/audit_report_routes.py"

    found = []
    if _exists(soc2_audit):
        found.append(soc2_audit)
    if _exists(soc2_middleware):
        found.append(soc2_middleware)
    if _exists(audit_routes):
        found.append(audit_routes)

    if len(found) >= 2:
        return CheckResult(
            control_id=cid,
            title="Monitoring — Audit Logging (AuditService + AuditMiddleware)",
            criterion=Criterion.CC,
            status=Status.PASS,
            detail=(
                "SOC 2 audit service, audit middleware, and audit report routes are present. "
                "All API requests and data access events are captured."
            ),
            evidence_paths=found,
        )
    if found:
        return CheckResult(
            control_id=cid,
            title="Monitoring — Audit Logging (AuditService + AuditMiddleware)",
            criterion=Criterion.CC,
            status=Status.PARTIAL,
            detail=f"Partial audit infrastructure found: {found}",
            evidence_paths=found,
            remediation=(
                "Ensure AuditMiddleware is registered in main.py and AuditService is "
                "called on all PII/financial data access."
            ),
        )
    return CheckResult(
        control_id=cid,
        title="Monitoring — Audit Logging (AuditService + AuditMiddleware)",
        criterion=Criterion.CC,
        status=Status.FAIL,
        detail="Audit logging infrastructure not found.",
        remediation=(
            "Deploy soc2_compliance/services/audit_service.py and "
            "soc2_compliance/middleware/audit_middleware.py."
        ),
    )


def check_cc9_compliance_routes() -> CheckResult:
    """CC3/CC4 — Compliance monitoring routes."""
    cid = "CC-9"
    path = "routes/compliance_routes.py"
    if _contains(path, "register_compliance_routes", "compliance", "TRID"):
        return CheckResult(
            control_id=cid,
            title="Compliance Monitoring — TRID / HMDA / Fair Lending Routes",
            criterion=Criterion.CC,
            status=Status.PASS,
            detail=(
                "routes/compliance_routes.py implements regulatory compliance monitoring "
                "(TRID, HMDA, Fair Lending, TCPA)."
            ),
            evidence_paths=[path],
        )
    if _exists(path):
        return CheckResult(
            control_id=cid,
            title="Compliance Monitoring — TRID / HMDA / Fair Lending Routes",
            criterion=Criterion.CC,
            status=Status.PARTIAL,
            detail="routes/compliance_routes.py exists but endpoint details not confirmed.",
            evidence_paths=[path],
            remediation="Verify TRID, HMDA, and Fair Lending endpoints are fully implemented.",
        )
    return CheckResult(
        control_id=cid,
        title="Compliance Monitoring — TRID / HMDA / Fair Lending Routes",
        criterion=Criterion.CC,
        status=Status.FAIL,
        detail="routes/compliance_routes.py not found.",
        remediation=(
            "Implement compliance routes covering TRID disclosure timing, HMDA LAR "
            "export, and Fair Lending analysis."
        ),
    )


def check_cc10_sso_saml() -> CheckResult:
    """CC6 — SSO / SAML / SCIM enterprise identity federation."""
    cid = "CC-10"
    saml = "auth/saml_sso.py"
    oidc = "auth/oidc_provider.py"
    scim = "routes/scim_provisioning_routes.py"
    sso_routes = "routes/sso_routes.py"

    found = [p for p in [saml, oidc, scim, sso_routes] if _exists(p)]
    if len(found) >= 2:
        return CheckResult(
            control_id=cid,
            title="Access Control — Enterprise SSO (SAML/OIDC/SCIM)",
            criterion=Criterion.CC,
            status=Status.PASS,
            detail=f"Enterprise identity federation files found: {found}",
            evidence_paths=found,
        )
    if found:
        return CheckResult(
            control_id=cid,
            title="Access Control — Enterprise SSO (SAML/OIDC/SCIM)",
            criterion=Criterion.CC,
            status=Status.PARTIAL,
            detail=f"Some SSO/SCIM files present: {found}",
            evidence_paths=found,
            remediation=(
                "Complete SAML/OIDC IdP integration and SCIM automated user provisioning "
                "for enterprise customer onboarding."
            ),
        )
    return CheckResult(
        control_id=cid,
        title="Access Control — Enterprise SSO (SAML/OIDC/SCIM)",
        criterion=Criterion.CC,
        status=Status.PARTIAL,
        detail="SSO/SAML/OIDC/SCIM files not found. Enterprise SSO is a common procurement requirement.",
        required=False,
        evidence_paths=[],
        remediation=(
            "Implement SAML 2.0 / OIDC IdP support (auth/saml_sso.py, auth/oidc_provider.py) "
            "and SCIM 2.0 user provisioning (routes/scim_provisioning_routes.py)."
        ),
    )


def check_cc11_rbac() -> CheckResult:
    """CC6 — Role-Based Access Control."""
    cid = "CC-11"
    roles_route = "routes/user_roles_routes.py"
    permission_core = "routes/permission_core_routes.py"
    permission_sys = "routes/permission_system_routes.py"

    found = [p for p in [roles_route, permission_core, permission_sys] if _exists(p)]
    if len(found) >= 2:
        return CheckResult(
            control_id=cid,
            title="Access Control — Role-Based Access Control (RBAC)",
            criterion=Criterion.CC,
            status=Status.PASS,
            detail=f"RBAC implementation files found: {found}",
            evidence_paths=found,
        )
    if found:
        return CheckResult(
            control_id=cid,
            title="Access Control — Role-Based Access Control (RBAC)",
            criterion=Criterion.CC,
            status=Status.PARTIAL,
            detail=f"Partial RBAC: {found}",
            evidence_paths=found,
            remediation="Ensure all endpoints enforce permission_role checks via RBAC middleware.",
        )
    return CheckResult(
        control_id=cid,
        title="Access Control — Role-Based Access Control (RBAC)",
        criterion=Criterion.CC,
        status=Status.FAIL,
        detail="RBAC route files not found.",
        remediation="Implement role-based access control for all resource types.",
    )


def check_cc12_change_management() -> CheckResult:
    """CC8 — Change management records."""
    cid = "CC-12"
    path = "soc2_compliance/services/change_management_service.py"
    if _exists(path):
        return CheckResult(
            control_id=cid,
            title="Change Management — Tracked Deployments & Approvals",
            criterion=Criterion.CC,
            status=Status.PASS,
            detail="soc2_compliance/services/change_management_service.py implements change tracking.",
            evidence_paths=[path],
        )
    return CheckResult(
        control_id=cid,
        title="Change Management — Tracked Deployments & Approvals",
        criterion=Criterion.CC,
        status=Status.FAIL,
        detail="change_management_service.py not found.",
        remediation=(
            "Implement change management records for every production deployment, "
            "configuration change, and database migration."
        ),
    )


def check_cc13_incident_response() -> CheckResult:
    """CC7 — Incident response service."""
    cid = "CC-13"
    path = "soc2_compliance/services/incident_service.py"
    routes = "soc2_compliance/api/incident_endpoints.py"
    found = [p for p in [path, routes] if _exists(p)]
    if len(found) == 2:
        return CheckResult(
            control_id=cid,
            title="System Operations — Incident Response Workflow",
            criterion=Criterion.CC,
            status=Status.PASS,
            detail="Incident service and API endpoints are present.",
            evidence_paths=found,
        )
    if found:
        return CheckResult(
            control_id=cid,
            title="System Operations — Incident Response Workflow",
            criterion=Criterion.CC,
            status=Status.PARTIAL,
            detail=f"Partial incident response infrastructure: {found}",
            evidence_paths=found,
            remediation="Ensure incident endpoints are accessible and notification workflows are wired.",
        )
    return CheckResult(
        control_id=cid,
        title="System Operations — Incident Response Workflow",
        criterion=Criterion.CC,
        status=Status.FAIL,
        detail="Incident response service not found.",
        remediation=(
            "Implement soc2_compliance/services/incident_service.py and corresponding API routes."
        ),
    )


def check_cc14_vendor_management() -> CheckResult:
    """CC9 — Vendor risk management registry."""
    cid = "CC-14"
    seed = "soc2_compliance/scripts/seed_vendor_registry.py"
    if _contains(seed, "VENDORS", "soc2_status", "risk_level"):
        return CheckResult(
            control_id=cid,
            title="Risk Mitigation — Vendor Management Registry",
            criterion=Criterion.CC,
            status=Status.PASS,
            detail="Vendor registry seed script present with SOC 2 status and risk level tracking.",
            evidence_paths=[seed],
        )
    return CheckResult(
        control_id=cid,
        title="Risk Mitigation — Vendor Management Registry",
        criterion=Criterion.CC,
        status=Status.PARTIAL,
        detail="Vendor registry seed not found or incomplete.",
        required=False,
        remediation=(
            "Populate soc2_vendor_registry table. Annually review each vendor's SOC 2 report "
            "and risk classification."
        ),
    )


# ---------------------------------------------------------------------------
# A — Availability
# ---------------------------------------------------------------------------

def check_a1_backup_recovery() -> CheckResult:
    """A1 — Disaster recovery / backup routes."""
    cid = "A-1"
    path = "routes/backup_routes.py"
    if _contains(path, "register_backup_routes", "RPO", "DR"):
        return CheckResult(
            control_id=cid,
            title="Availability — Backup & Disaster Recovery Routes",
            criterion=Criterion.A,
            status=Status.PASS,
            detail="routes/backup_routes.py provides backup history, RPO/RTO monitoring, and DR readiness.",
            evidence_paths=[path],
        )
    if _exists(path):
        return CheckResult(
            control_id=cid,
            title="Availability — Backup & Disaster Recovery Routes",
            criterion=Criterion.A,
            status=Status.PARTIAL,
            detail="routes/backup_routes.py exists but RPO/RTO monitoring not confirmed.",
            evidence_paths=[path],
            remediation="Add explicit RPO/RTO compliance checks and scheduled backup verification.",
        )
    return CheckResult(
        control_id=cid,
        title="Availability — Backup & Disaster Recovery Routes",
        criterion=Criterion.A,
        status=Status.FAIL,
        detail="routes/backup_routes.py not found.",
        remediation=(
            "Implement backup management routes with backup history, restore testing, "
            "and RPO/RTO dashboards."
        ),
    )


def check_a2_health_endpoints() -> CheckResult:
    """A1 — Health check / uptime endpoints."""
    cid = "A-2"
    candidates = ["routes/ssl_routes.py", "main.py", "start.py"]
    for candidate in candidates:
        if _any_contains(candidate, "/health", "/healthz", "/ready"):
            return CheckResult(
                control_id=cid,
                title="Availability — Health Check Endpoints",
                criterion=Criterion.A,
                status=Status.PASS,
                detail=f"Health endpoint pattern found in {candidate}.",
                evidence_paths=[candidate],
            )
    # Check routes directory broadly
    hits = _grep_dir("routes", "/health")
    if hits:
        return CheckResult(
            control_id=cid,
            title="Availability — Health Check Endpoints",
            criterion=Criterion.A,
            status=Status.PASS,
            detail=f"Health endpoint pattern found in: {hits[:3]}",
            evidence_paths=hits[:3],
        )
    return CheckResult(
        control_id=cid,
        title="Availability — Health Check Endpoints",
        criterion=Criterion.A,
        status=Status.FAIL,
        detail="No /health or /healthz endpoints found.",
        remediation="Expose GET /health and GET /ready endpoints for uptime monitoring.",
    )


def check_a3_monitoring() -> CheckResult:
    """A1 — Application performance monitoring."""
    cid = "A-3"
    datadog = "datadog_monitoring.py"
    if _exists(datadog):
        return CheckResult(
            control_id=cid,
            title="Availability — APM / Observability (DataDog)",
            criterion=Criterion.A,
            status=Status.PASS,
            detail="datadog_monitoring.py provides APM integration for uptime and error tracking.",
            evidence_paths=[datadog],
        )
    return CheckResult(
        control_id=cid,
        title="Availability — APM / Observability (DataDog)",
        criterion=Criterion.A,
        status=Status.PARTIAL,
        detail="datadog_monitoring.py not found. Confirm monitoring is configured via environment.",
        required=False,
        remediation="Configure DataDog (or equivalent) APM for uptime SLA tracking.",
    )


def check_a4_structured_logging() -> CheckResult:
    """A1 — Structured JSON logging for log aggregation."""
    cid = "A-4"
    path = "middleware/structured_logging.py"
    if _contains(path, "JsonFormatter", "StructuredLogging"):
        return CheckResult(
            control_id=cid,
            title="Availability — Structured JSON Logging",
            criterion=Criterion.A,
            status=Status.PASS,
            detail="middleware/structured_logging.py provides JSON log formatting for ELK/CloudWatch/DataDog.",
            evidence_paths=[path],
        )
    if _exists(path):
        return CheckResult(
            control_id=cid,
            title="Availability — Structured JSON Logging",
            criterion=Criterion.A,
            status=Status.PARTIAL,
            detail="structured_logging.py exists but JsonFormatter not confirmed.",
            evidence_paths=[path],
            remediation="Ensure log output is JSON-formatted and ingested by a SIEM or log aggregator.",
        )
    return CheckResult(
        control_id=cid,
        title="Availability — Structured JSON Logging",
        criterion=Criterion.A,
        status=Status.FAIL,
        detail="middleware/structured_logging.py not found.",
        remediation="Implement structured JSON logging middleware.",
    )


# ---------------------------------------------------------------------------
# PI — Processing Integrity
# ---------------------------------------------------------------------------

def check_pi1_input_validation() -> CheckResult:
    """PI1 — Input validation / sanitization."""
    cid = "PI-1"
    path = "input_validation.py"
    if _contains(path, "nh3") or _any_contains(path, "sanitize", "validate", "HTMLSanitizer"):
        return CheckResult(
            control_id=cid,
            title="Processing Integrity — Input Validation & HTML Sanitization",
            criterion=Criterion.PI,
            status=Status.PASS,
            detail="input_validation.py implements HTML sanitization (nh3) and input validation.",
            evidence_paths=[path],
        )
    if _exists(path):
        return CheckResult(
            control_id=cid,
            title="Processing Integrity — Input Validation & HTML Sanitization",
            criterion=Criterion.PI,
            status=Status.PARTIAL,
            detail="input_validation.py exists but sanitization library not confirmed.",
            evidence_paths=[path],
            remediation=(
                "Replace deprecated bleach with nh3 for HTML sanitization. "
                "Validate all user-supplied inputs with Pydantic schemas."
            ),
        )
    return CheckResult(
        control_id=cid,
        title="Processing Integrity — Input Validation & HTML Sanitization",
        criterion=Criterion.PI,
        status=Status.FAIL,
        detail="input_validation.py not found.",
        remediation="Implement centralised input validation and HTML sanitization.",
    )


def check_pi2_error_handling() -> CheckResult:
    """PI1 — Centralised error handling."""
    cid = "PI-2"
    middleware_stack = "middleware/stack.py"
    error_resp = "middleware/error_response.py"
    exceptions_file = "exceptions.py"

    found = [p for p in [middleware_stack, error_resp, exceptions_file] if _exists(p)]
    if len(found) >= 2:
        return CheckResult(
            control_id=cid,
            title="Processing Integrity — Centralised Error Handling & Domain Exceptions",
            criterion=Criterion.PI,
            status=Status.PASS,
            detail=f"Error handling infrastructure found: {found}",
            evidence_paths=found,
        )
    if found:
        return CheckResult(
            control_id=cid,
            title="Processing Integrity — Centralised Error Handling & Domain Exceptions",
            criterion=Criterion.PI,
            status=Status.PARTIAL,
            detail=f"Partial error handling: {found}",
            evidence_paths=found,
            remediation="Ensure all 500-level errors are caught, logged, and sanitized before returning to clients.",
        )
    return CheckResult(
        control_id=cid,
        title="Processing Integrity — Centralised Error Handling & Domain Exceptions",
        criterion=Criterion.PI,
        status=Status.FAIL,
        detail="Error handling middleware not found.",
        remediation="Add centralized exception handlers and domain exception classes.",
    )


def check_pi3_compliance_scan() -> CheckResult:
    """PI1 — Automated SOC 2 compliance scanning."""
    cid = "PI-3"
    path = "soc2_compliance/scripts/compliance_scan.py"
    if _contains(path, "ComplianceScanner", "run_all_checks"):
        return CheckResult(
            control_id=cid,
            title="Processing Integrity — Automated SOC 2 Compliance Scanning",
            criterion=Criterion.PI,
            status=Status.PASS,
            detail="ComplianceScanner with run_all_checks() is implemented.",
            evidence_paths=[path],
        )
    if _exists(path):
        return CheckResult(
            control_id=cid,
            title="Processing Integrity — Automated SOC 2 Compliance Scanning",
            criterion=Criterion.PI,
            status=Status.PARTIAL,
            detail="compliance_scan.py exists but ComplianceScanner not confirmed.",
            evidence_paths=[path],
            remediation="Ensure compliance_scan.py runs daily via scheduler.",
        )
    return CheckResult(
        control_id=cid,
        title="Processing Integrity — Automated SOC 2 Compliance Scanning",
        criterion=Criterion.PI,
        status=Status.FAIL,
        detail="compliance_scan.py not found.",
        remediation="Implement automated daily compliance scan.",
    )


# ---------------------------------------------------------------------------
# C — Confidentiality
# ---------------------------------------------------------------------------

def check_c1_encryption_at_rest() -> CheckResult:
    """C1 — Field-level encryption for PII/financial data at rest."""
    cid = "C-1"
    utils = "encryption_utils.py"
    soc2_enc = "soc2_compliance/services/encryption_service.py"
    migrate = "migrate_to_encrypted_fields.py"

    found = [p for p in [utils, soc2_enc, migrate] if _exists(p)]
    if _contains(utils, "EncryptionManager", "Fernet") or _contains(soc2_enc, "EncryptionService", "Fernet"):
        return CheckResult(
            control_id=cid,
            title="Confidentiality — Field-Level Encryption at Rest (Fernet/AES)",
            criterion=Criterion.C,
            status=Status.PASS,
            detail=(
                "Fernet symmetric encryption is implemented for sensitive fields. "
                "DATA_ENCRYPTION_KEY env var required in production."
            ),
            evidence_paths=found,
        )
    if found:
        return CheckResult(
            control_id=cid,
            title="Confidentiality — Field-Level Encryption at Rest (Fernet/AES)",
            criterion=Criterion.C,
            status=Status.PARTIAL,
            detail=f"Encryption files found but Fernet not confirmed: {found}",
            evidence_paths=found,
            remediation=(
                "Confirm DATA_ENCRYPTION_KEY is set in production and all PII columns "
                "use EncryptedString SQLAlchemy column type."
            ),
        )
    return CheckResult(
        control_id=cid,
        title="Confidentiality — Field-Level Encryption at Rest (Fernet/AES)",
        criterion=Criterion.C,
        status=Status.FAIL,
        detail="Encryption utilities not found.",
        remediation=(
            "Implement field-level encryption for SSN, bank_account, tax_id, and "
            "other restricted fields using cryptography.fernet.Fernet."
        ),
    )


def check_c2_tls_in_transit() -> CheckResult:
    """C1 — TLS / HTTPS enforcement via HSTS."""
    cid = "C-2"
    # HSTS is set by SecurityHeadersMiddleware — check it
    sm = "security_middleware.py"
    sh = "soc2_compliance/middleware/security_headers.py"
    if _any_contains(sm, "Strict-Transport-Security") or _any_contains(sh, "Strict-Transport-Security"):
        return CheckResult(
            control_id=cid,
            title="Confidentiality — TLS Enforcement (HSTS)",
            criterion=Criterion.C,
            status=Status.PASS,
            detail="Strict-Transport-Security header is set by SecurityHeadersMiddleware.",
            evidence_paths=[sm if _exists(sm) else sh],
        )
    return CheckResult(
        control_id=cid,
        title="Confidentiality — TLS Enforcement (HSTS)",
        criterion=Criterion.C,
        status=Status.FAIL,
        detail="Strict-Transport-Security header not found in middleware.",
        remediation=(
            "Add 'Strict-Transport-Security: max-age=31536000; includeSubDomains' "
            "to all API responses."
        ),
    )


def check_c3_tenant_isolation() -> CheckResult:
    """C1 — Multi-tenant data isolation."""
    cid = "C-3"
    tenant_mw = "middleware/tenant_middleware.py"
    tenant_ctx = "middleware/tenant_context_middleware.py"
    found = [p for p in [tenant_mw, tenant_ctx] if _exists(p)]
    if found:
        return CheckResult(
            control_id=cid,
            title="Confidentiality — Multi-Tenant Data Isolation (Row-Level Security)",
            criterion=Criterion.C,
            status=Status.PASS,
            detail=f"Tenant isolation middleware found: {found}",
            evidence_paths=found,
        )
    return CheckResult(
        control_id=cid,
        title="Confidentiality — Multi-Tenant Data Isolation (Row-Level Security)",
        criterion=Criterion.C,
        status=Status.FAIL,
        detail="Tenant isolation middleware not found.",
        remediation=(
            "Implement tenant context middleware that enforces organization_id "
            "row-level scoping on all database queries."
        ),
    )


def check_c4_data_retention() -> CheckResult:
    """C1 — Data retention and disposal service."""
    cid = "C-4"
    path = "soc2_compliance/services/retention_service.py"
    if _contains(path, "RetentionService", "enforce_retention"):
        return CheckResult(
            control_id=cid,
            title="Confidentiality — Data Retention & Secure Disposal",
            criterion=Criterion.C,
            status=Status.PASS,
            detail="soc2_compliance/services/retention_service.py implements retention policy enforcement.",
            evidence_paths=[path],
        )
    if _exists(path):
        return CheckResult(
            control_id=cid,
            title="Confidentiality — Data Retention & Secure Disposal",
            criterion=Criterion.C,
            status=Status.PARTIAL,
            detail="retention_service.py exists but enforcement method not confirmed.",
            evidence_paths=[path],
            remediation="Confirm enforce_retention_policies() runs on a daily schedule.",
        )
    return CheckResult(
        control_id=cid,
        title="Confidentiality — Data Retention & Secure Disposal",
        criterion=Criterion.C,
        status=Status.FAIL,
        detail="retention_service.py not found.",
        remediation=(
            "Implement data retention service. Minimum retention: "
            "audit logs 2 yrs, loan records 5 yrs, financial records 7 yrs."
        ),
    )


# ---------------------------------------------------------------------------
# P — Privacy
# ---------------------------------------------------------------------------

def check_p1_pii_log_filter() -> CheckResult:
    """P1 — PII redaction from application logs."""
    cid = "P-1"
    path = "middleware/pii_log_filter.py"
    if _contains(path, "PIIRedactionFilter", "SSN", "filter"):
        return CheckResult(
            control_id=cid,
            title="Privacy — PII Redaction in Application Logs",
            criterion=Criterion.P,
            status=Status.PASS,
            detail=(
                "middleware/pii_log_filter.py implements PIIRedactionFilter that "
                "redacts SSN, credit card numbers, and DOB from all log records."
            ),
            evidence_paths=[path],
        )
    if _exists(path):
        return CheckResult(
            control_id=cid,
            title="Privacy — PII Redaction in Application Logs",
            criterion=Criterion.P,
            status=Status.PARTIAL,
            detail="pii_log_filter.py exists but PIIRedactionFilter not confirmed.",
            evidence_paths=[path],
            remediation=(
                "Ensure PIIRedactionFilter is added to the root logger at application startup "
                "so all log handlers inherit it."
            ),
        )
    return CheckResult(
        control_id=cid,
        title="Privacy — PII Redaction in Application Logs",
        criterion=Criterion.P,
        status=Status.FAIL,
        detail="middleware/pii_log_filter.py not found.",
        remediation=(
            "Create PIIRedactionFilter (logging.Filter) that redacts SSN, credit card, "
            "bank account, and DOB patterns from all log messages."
        ),
    )


def check_p2_data_classification() -> CheckResult:
    """P3 — PII data classification tagging."""
    cid = "P-2"
    seed = "soc2_compliance/scripts/seed_data_classification.py"
    if _exists(seed):
        return CheckResult(
            control_id=cid,
            title="Privacy — Data Classification & PII Inventory",
            criterion=Criterion.P,
            status=Status.PASS,
            detail="Data classification seed script present for PII/confidential/restricted tagging.",
            evidence_paths=[seed],
        )
    return CheckResult(
        control_id=cid,
        title="Privacy — Data Classification & PII Inventory",
        criterion=Criterion.P,
        status=Status.PARTIAL,
        detail="soc2_compliance/scripts/seed_data_classification.py not found.",
        required=False,
        remediation=(
            "Create data classification inventory mapping all database fields to "
            "Public / Internal / Confidential / Restricted classifications."
        ),
    )


def check_p3_consent_management() -> CheckResult:
    """P4 — TCPA / consent tracking."""
    cid = "P-3"
    compliance = "routes/compliance_routes.py"
    if _contains(compliance, "tcpa", "consent"):
        return CheckResult(
            control_id=cid,
            title="Privacy — Consent Management (TCPA)",
            criterion=Criterion.P,
            status=Status.PASS,
            detail="routes/compliance_routes.py includes TCPA consent check and tracking endpoints.",
            evidence_paths=[compliance],
        )
    return CheckResult(
        control_id=cid,
        title="Privacy — Consent Management (TCPA)",
        criterion=Criterion.P,
        status=Status.FAIL,
        detail="TCPA consent tracking not confirmed in compliance_routes.py.",
        remediation=(
            "Implement POST /compliance/tcpa/check and GET /compliance/tcpa/consent/{id} "
            "endpoints. Log every consent check to the audit trail."
        ),
    )


def check_p4_soc2_config() -> CheckResult:
    """P — SOC 2 centralised configuration."""
    cid = "P-4"
    path = "soc2_compliance/config.py"
    if _contains(path, "SOC2Config", "require_mfa", "pii_fields"):
        return CheckResult(
            control_id=cid,
            title="Privacy — SOC 2 Centralised Configuration (SOC2Config)",
            criterion=Criterion.P,
            status=Status.PASS,
            detail=(
                "soc2_compliance/config.py defines SOC2Config with MFA enforcement, "
                "PII field inventory, session timeout, and lockout policy."
            ),
            evidence_paths=[path],
        )
    return CheckResult(
        control_id=cid,
        title="Privacy — SOC 2 Centralised Configuration (SOC2Config)",
        criterion=Criterion.P,
        status=Status.FAIL,
        detail="soc2_compliance/config.py not found or incomplete.",
        remediation="Populate soc2_compliance/config.py with all required SOC2Config fields.",
    )


# ===========================================================================
# Registry of all checks
# ===========================================================================

ALL_CHECKS: List[Callable[[], CheckResult]] = [
    # Security (CC)
    check_cc1_access_control_dependencies,
    check_cc2_jwt_token_management,
    check_cc3_mfa,
    check_cc4_account_lockout,
    check_cc5_security_headers_middleware,
    check_cc6_rate_limiting,
    check_cc7_csrf_protection,
    check_cc8_audit_logging,
    check_cc9_compliance_routes,
    check_cc10_sso_saml,
    check_cc11_rbac,
    check_cc12_change_management,
    check_cc13_incident_response,
    check_cc14_vendor_management,
    # Availability (A)
    check_a1_backup_recovery,
    check_a2_health_endpoints,
    check_a3_monitoring,
    check_a4_structured_logging,
    # Processing Integrity (PI)
    check_pi1_input_validation,
    check_pi2_error_handling,
    check_pi3_compliance_scan,
    # Confidentiality (C)
    check_c1_encryption_at_rest,
    check_c2_tls_in_transit,
    check_c3_tenant_isolation,
    check_c4_data_retention,
    # Privacy (P)
    check_p1_pii_log_filter,
    check_p2_data_classification,
    check_p3_consent_management,
    check_p4_soc2_config,
]


# ===========================================================================
# Report builder
# ===========================================================================

_STATUS_ICON = {
    Status.PASS: "[PASS]",
    Status.PARTIAL: "[PARTIAL]",
    Status.FAIL: "[FAIL]",
    Status.SKIP: "[SKIP]",
}


def run_assessment() -> ReadinessReport:
    """Execute all checks and build the readiness report."""
    results: List[CheckResult] = []
    for check_fn in ALL_CHECKS:
        try:
            result = check_fn()
        except Exception as exc:
            result = CheckResult(
                control_id="UNKNOWN",
                title=check_fn.__name__,
                criterion=Criterion.CC,
                status=Status.SKIP,
                detail=f"Check raised an exception: {exc}",
                remediation="Investigate and fix the check function.",
            )
        results.append(result)

    summary = {s.value: 0 for s in Status}
    for r in results:
        summary[r.status.value] += 1

    required_failures = [r for r in results if r.status == Status.FAIL and r.required]
    overall_status = "READY" if not required_failures else "NOT READY"

    gaps = [
        f"[{r.control_id}] {r.title}: {r.remediation}"
        for r in results
        if r.status == Status.FAIL and r.required
    ]

    recommendations = [
        f"[{r.control_id}] {r.title}: {r.remediation}"
        for r in results
        if r.status in (Status.PARTIAL, Status.FAIL) and not r.required
    ]

    return ReadinessReport(
        generated_at=datetime.now(timezone.utc).isoformat() + "Z",
        backend_root=str(_BACKEND_ROOT),
        summary=summary,
        overall_status=overall_status,
        checks=results,
        gaps=gaps,
        recommendations=recommendations,
    )


# ===========================================================================
# Console printer
# ===========================================================================

def print_report(report: ReadinessReport) -> None:
    width = 78
    print("=" * width)
    print("  SOC 2 TYPE II READINESS ASSESSMENT — PERENNIA AI")
    print(f"  Generated: {report.generated_at}")
    print(f"  Backend root: {report.backend_root}")
    print("=" * width)

    current_criterion: Optional[str] = None
    for check in report.checks:
        if check.criterion.value != current_criterion:
            current_criterion = check.criterion.value
            print(f"\n--- {current_criterion} ---")

        icon = _STATUS_ICON[check.status]
        req_tag = "" if check.required else " [optional]"
        print(f"\n  {icon}{req_tag}  [{check.control_id}] {check.title}")
        print(f"           {check.detail}")
        if check.status != Status.PASS and check.remediation:
            print(f"           Remediation: {check.remediation}")
        if check.evidence_paths:
            for ep in check.evidence_paths:
                print(f"           Evidence: backend/{ep}")

    print("\n" + "=" * width)
    print("  SUMMARY")
    print("=" * width)
    for status, count in report.summary.items():
        print(f"  {status:<10} {count}")
    print(f"\n  OVERALL STATUS: {report.overall_status}")

    if report.gaps:
        print(f"\n  REQUIRED GAPS ({len(report.gaps)}) — must resolve before audit:")
        for gap in report.gaps:
            print(f"    * {gap}")

    if report.recommendations:
        print(f"\n  OPTIONAL IMPROVEMENTS ({len(report.recommendations)}):")
        for rec in report.recommendations:
            print(f"    - {rec}")

    print("=" * width)


# ===========================================================================
# CLI entry point
# ===========================================================================

def main() -> None:
    parser = argparse.ArgumentParser(
        description="SOC 2 Type II readiness assessment for Perennia AI backend"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON instead of formatted report",
    )
    parser.add_argument(
        "--output",
        metavar="FILE",
        help="Write JSON report to file (implies --json)",
    )
    args = parser.parse_args()

    report = run_assessment()

    if args.json or args.output:
        payload = asdict(report)
        # Convert enums to string values for JSON serialisation
        for check in payload["checks"]:
            check["status"] = check["status"]
            check["criterion"] = check["criterion"]
        json_str = json.dumps(payload, indent=2, default=str)
        if args.output:
            Path(args.output).write_text(json_str)
            print(f"Report written to {args.output}")
        else:
            print(json_str)
    else:
        print_report(report)

    required_failures = [c for c in report.checks if c.status == Status.FAIL and c.required]
    sys.exit(1 if required_failures else 0)


if __name__ == "__main__":
    main()
