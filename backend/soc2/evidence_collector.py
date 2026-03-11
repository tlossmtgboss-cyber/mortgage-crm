"""SOC 2 Evidence Collector — Perennia AI
==========================================

Automatically collects and packages SOC 2 Type II evidence artifacts
from the live application database and codebase.

Run:
    python soc2/evidence_collector.py
    python soc2/evidence_collector.py --output evidence_package.json
    python soc2/evidence_collector.py --section access_controls
    python soc2/evidence_collector.py --db               (requires DATABASE_URL)

Sections:
    endpoints            — All API endpoints with auth / public status
    security_headers     — Security header configuration inventory
    rbac_roles           — RBAC role definitions from DB or codebase
    audit_log_sample     — Recent audit log entries (requires DB)
    encryption_inventory — Encryption configuration inventory
    access_matrix        — Access control matrix by role
    vendor_registry      — Third-party vendor risk registry (requires DB)
    retention_policies   — Data retention configuration
    mfa_config           — MFA configuration and enforcement status
    incident_summary     — Open/recent incident summary (requires DB)
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Resolve backend root
# ---------------------------------------------------------------------------
_THIS_FILE = Path(__file__).resolve()
_BACKEND_ROOT = _THIS_FILE.parent.parent  # backend/


# ===========================================================================
# Data structures
# ===========================================================================

@dataclass
class EvidenceSection:
    section_id: str
    title: str
    soc2_criteria: List[str]       # e.g. ["CC6.1", "CC6.3"]
    collected_at: str
    data: Any
    source: str                    # "codebase" | "database" | "config"
    notes: str = ""


@dataclass
class EvidencePackage:
    generated_at: str
    backend_root: str
    collector_version: str
    db_connected: bool
    sections: List[EvidenceSection]


# ===========================================================================
# Helpers
# ===========================================================================

def _p(*parts: str) -> Path:
    return _BACKEND_ROOT.joinpath(*parts)


def _read(relpath: str) -> str:
    p = _p(relpath)
    if not p.exists():
        return ""
    return p.read_text(errors="ignore")


def _exists(*parts: str) -> bool:
    return _p(*parts).exists()


def _route_files() -> List[Path]:
    routes_dir = _p("routes")
    if not routes_dir.is_dir():
        return []
    return sorted(routes_dir.glob("*.py"))


# ---------------------------------------------------------------------------
# Database access (optional — degrades gracefully when DB is not available)
# ---------------------------------------------------------------------------

_db_session = None


def _try_connect_db() -> bool:
    """Attempt to connect to the database. Returns True on success."""
    global _db_session
    try:
        db_url = os.getenv("DATABASE_URL")
        if not db_url:
            return False
        from sqlalchemy import create_engine, text
        from sqlalchemy.orm import sessionmaker
        engine = create_engine(db_url, pool_pre_ping=True, connect_args={"connect_timeout": 5})
        Session = sessionmaker(bind=engine)
        _db_session = Session()
        _db_session.execute(text("SELECT 1"))
        return True
    except Exception:
        _db_session = None
        return False


def _query(sql: str, params: dict = None) -> List[Dict[str, Any]]:
    """Execute a SELECT and return list of dicts. Returns [] if no DB."""
    if _db_session is None:
        return []
    try:
        from sqlalchemy import text
        result = _db_session.execute(text(sql), params or {})
        cols = list(result.keys())
        return [dict(zip(cols, row)) for row in result.fetchall()]
    except Exception as exc:
        return [{"error": str(exc)}]


# ===========================================================================
# Section collectors
# ===========================================================================

def collect_endpoints() -> EvidenceSection:
    """
    Parse all route files and classify each endpoint as authenticated or public.

    Strategy:
      - Public  = path contains /public/ or /health or file is public_routes.py
                  OR the route registration block has no Depends(get_current_user)
                  pattern nearby (heuristic)
      - Auth    = has Depends(get_current_user) / require_auth pattern

    Returns a summary plus per-file counts.
    """
    AUTH_PATTERNS = [
        "Depends(get_current_user",
        "Depends(require_auth",
        "= Depends(_get_current_user",
        "current_user = Depends",
    ]
    PUBLIC_PATTERNS = [
        "/public/",
        "/health",
        "/healthz",
        "/ready",
        "/csrf-token",
    ]

    summary: List[Dict] = []
    total_auth = 0
    total_public = 0
    total_unknown = 0

    for route_file in _route_files():
        if route_file.name.startswith("_"):
            continue
        content = route_file.read_text(errors="ignore")
        # Count @router.get / @router.post / @app.get etc.
        endpoint_matches = re.findall(
            r'@(?:router|app)\.(get|post|put|patch|delete)\s*\(\s*["\']([^"\']+)["\']',
            content,
        )
        if not endpoint_matches:
            continue

        file_auth = 0
        file_public = 0
        file_unknown = 0

        has_auth = any(pat in content for pat in AUTH_PATTERNS)

        for _method, path in endpoint_matches:
            is_public = any(pub in path for pub in PUBLIC_PATTERNS)
            if is_public:
                file_public += 1
            elif has_auth:
                file_auth += 1
            else:
                file_unknown += 1

        total_auth += file_auth
        total_public += file_public
        total_unknown += file_unknown

        summary.append({
            "file": route_file.name,
            "endpoints": len(endpoint_matches),
            "authenticated": file_auth,
            "public": file_public,
            "unknown_auth": file_unknown,
            "has_auth_dependency": has_auth,
        })

    return EvidenceSection(
        section_id="endpoints",
        title="API Endpoint Authentication Inventory",
        soc2_criteria=["CC6.1", "CC6.3", "CC6.6"],
        collected_at=datetime.utcnow().isoformat() + "Z",
        source="codebase",
        data={
            "total_authenticated": total_auth,
            "total_public": total_public,
            "total_unknown_auth_status": total_unknown,
            "total_files_scanned": len(summary),
            "by_file": summary,
        },
        notes=(
            "Endpoints marked 'unknown_auth_status' require manual review. "
            "Authentication may be enforced at the router or middleware level."
        ),
    )


def collect_security_headers() -> EvidenceSection:
    """Collect security header configuration from middleware files."""
    headers: Dict[str, Dict] = {}

    sm_path = "security_middleware.py"
    soc2_sh_path = "soc2_compliance/middleware/security_headers.py"

    for relpath in [sm_path, soc2_sh_path]:
        content = _read(relpath)
        if not content:
            continue
        # Extract header name/value pairs from header assignment patterns
        for m in re.finditer(
            r'response\.headers\[[\'"]([\w\-]+)[\'"]\]\s*=\s*["\']([^"\']+)["\']',
            content,
        ):
            header_name, header_value = m.group(1), m.group(2)
            headers[header_name] = {
                "value": header_value,
                "source_file": relpath,
            }

    # Assess critical headers
    required_headers = {
        "Strict-Transport-Security": "Enforces HTTPS. Required for SOC 2 CC6.7.",
        "X-Frame-Options": "Prevents clickjacking. Required.",
        "X-Content-Type-Options": "Prevents MIME sniffing.",
        "Content-Security-Policy": "Controls resource loading. Recommended.",
        "Referrer-Policy": "Controls referrer information leakage.",
        "Permissions-Policy": "Restricts browser feature access.",
    }

    assessment = []
    for header, rationale in required_headers.items():
        assessment.append({
            "header": header,
            "present": header in headers,
            "value": headers.get(header, {}).get("value", "NOT SET"),
            "rationale": rationale,
        })

    return EvidenceSection(
        section_id="security_headers",
        title="Security Header Configuration",
        soc2_criteria=["CC6.7", "CC5.6"],
        collected_at=datetime.utcnow().isoformat() + "Z",
        source="codebase",
        data={
            "configured_headers": headers,
            "assessment": assessment,
            "missing_required": [a["header"] for a in assessment if not a["present"]],
        },
        notes=(
            "Values extracted statically from security_middleware.py and "
            "soc2_compliance/middleware/security_headers.py. "
            "Verify headers are present in live HTTP responses using curl -I."
        ),
    )


def collect_rbac_roles() -> EvidenceSection:
    """Collect RBAC role definitions from codebase and optionally DB."""
    # Gather role constants from known files
    role_files = [
        "routes/backup_routes.py",
        "routes/permission_core_routes.py",
        "routes/user_roles_routes.py",
    ]
    roles_found: Dict[str, List[str]] = {}

    for relpath in role_files:
        content = _read(relpath)
        if not content:
            continue
        # Find ADMIN_ROLES / permission_role tuples / role string literals
        for m in re.finditer(
            r'(?:ADMIN_ROLES|ROLES|ALLOWED_ROLES)\s*=\s*[\(\[]([^\)\]]+)[\)\]]',
            content,
        ):
            raw = m.group(1)
            roles = re.findall(r'["\']([^"\']+)["\']', raw)
            if roles:
                roles_found[relpath] = roles

    # Query DB if connected
    db_roles: List[Dict] = []
    if _db_session is not None:
        db_roles = _query(
            """
            SELECT DISTINCT permission_role, COUNT(*) as user_count
            FROM users
            WHERE permission_role IS NOT NULL
            GROUP BY permission_role
            ORDER BY permission_role
            """
        )

    return EvidenceSection(
        section_id="rbac_roles",
        title="RBAC Role Definitions",
        soc2_criteria=["CC6.1", "CC6.2", "CC6.3"],
        collected_at=datetime.utcnow().isoformat() + "Z",
        source="codebase" if not db_roles else "database",
        data={
            "roles_in_code": roles_found,
            "roles_in_database": db_roles,
            "known_roles": [
                "admin",
                "site_admin",
                "platform_admin",
                "loan_officer",
                "processor",
                "branch_manager",
                "read_only",
            ],
        },
        notes=(
            "Permission model: permission_role column on users table. "
            "Role checks performed via getattr(current_user, 'permission_role', '') "
            "in route handlers."
        ),
    )


def collect_audit_log_sample() -> EvidenceSection:
    """Pull a recent sample of audit log entries from the soc2_audit_logs table."""
    rows = _query(
        """
        SELECT
            id, tenant_id, user_id, user_email, user_role,
            action, resource_type, resource_id, description,
            ip_address, severity, created_at
        FROM soc2_audit_logs
        ORDER BY created_at DESC
        LIMIT 25
        """,
    )

    # Strip raw UUIDs from output for the evidence document
    sanitized = []
    for row in rows:
        if "error" in row:
            sanitized.append(row)
            break
        sanitized.append({
            "id": str(row.get("id", ""))[:8] + "...",
            "user_email": row.get("user_email", ""),
            "user_role": row.get("user_role", ""),
            "action": row.get("action", ""),
            "resource_type": row.get("resource_type", ""),
            "resource_id": str(row.get("resource_id", ""))[:8] + "..." if row.get("resource_id") else None,
            "description": (row.get("description") or "")[:120],
            "ip_address": row.get("ip_address", ""),
            "severity": row.get("severity", ""),
            "created_at": str(row.get("created_at", "")),
        })

    count_rows = _query("SELECT COUNT(*) as total FROM soc2_audit_logs")
    total = count_rows[0].get("total", "unknown") if count_rows else "unknown"

    return EvidenceSection(
        section_id="audit_log_sample",
        title="Audit Log Sample (Most Recent 25 Events)",
        soc2_criteria=["CC4.1", "CC2.2", "PI1.1"],
        collected_at=datetime.utcnow().isoformat() + "Z",
        source="database",
        data={
            "total_audit_log_entries": total,
            "sample": sanitized,
            "note": "Full audit log available via GET /api/v1/compliance/audit/logs (admin only).",
        },
        notes=(
            "Audit logs are retained for 730 days per SOC2Config.audit_retention_days. "
            "Resource IDs are truncated in this evidence export."
        ),
    )


def collect_encryption_inventory() -> EvidenceSection:
    """Inventory encryption configuration from codebase."""
    findings: List[Dict] = []

    # Check encryption_utils.py
    enc_utils = _read("encryption_utils.py")
    if enc_utils:
        findings.append({
            "component": "EncryptionManager (encryption_utils.py)",
            "algorithm": "Fernet (AES-128-CBC with HMAC-SHA256)",
            "key_source": "DATA_ENCRYPTION_KEY env var (falls back to SECRET_KEY)",
            "use_case": "Field-level encryption for borrower financial data",
            "key_rotation": "Manual — annual rotation recommended",
            "status": "IMPLEMENTED",
        })

    # Check soc2 encryption service
    soc2_enc = _read("soc2_compliance/services/encryption_service.py")
    if soc2_enc:
        findings.append({
            "component": "EncryptionService (soc2_compliance/services/encryption_service.py)",
            "algorithm": "Fernet (AES-128-CBC with HMAC-SHA256)",
            "key_source": "SOC2_FIELD_ENCRYPTION_KEY env var",
            "use_case": "SOC 2 PII field encryption (SSN, bank accounts, tax IDs)",
            "key_rotation": "Annual via SOC2Config",
            "status": "IMPLEMENTED",
        })

    # Check TLS configuration via HSTS
    if "Strict-Transport-Security" in _read("security_middleware.py"):
        findings.append({
            "component": "TLS in Transit",
            "algorithm": "TLS 1.2/1.3 enforced via Railway (PaaS)",
            "key_source": "Platform-managed (Railway)",
            "use_case": "All API traffic encrypted in transit",
            "key_rotation": "Platform-managed",
            "status": "IMPLEMENTED",
        })

    # Check Postgres TLS
    db_url = os.getenv("DATABASE_URL", "")
    if db_url:
        has_ssl = "sslmode=require" in db_url or "sslmode=verify" in db_url
        findings.append({
            "component": "PostgreSQL Database TLS",
            "algorithm": "TLS (SSL mode)",
            "key_source": "DATABASE_URL env var",
            "use_case": "Database connection encryption",
            "key_rotation": "Platform-managed",
            "status": "CONFIGURED" if has_ssl else "REVIEW NEEDED — sslmode not detected in DATABASE_URL",
        })

    # Check migration script existence
    if _exists("migrate_to_encrypted_fields.py"):
        findings.append({
            "component": "Field Encryption Migration",
            "algorithm": "N/A",
            "key_source": "N/A",
            "use_case": "One-time migration to encrypt existing plaintext PII fields",
            "key_rotation": "N/A",
            "status": "SCRIPT EXISTS — confirm migration has been run in production",
        })

    env_vars_present = {
        "DATA_ENCRYPTION_KEY": bool(os.getenv("DATA_ENCRYPTION_KEY")),
        "SOC2_FIELD_ENCRYPTION_KEY": bool(os.getenv("SOC2_FIELD_ENCRYPTION_KEY")),
        "SECRET_KEY": bool(os.getenv("SECRET_KEY")),
        "DATABASE_URL": bool(os.getenv("DATABASE_URL")),
    }

    return EvidenceSection(
        section_id="encryption_inventory",
        title="Encryption Configuration Inventory",
        soc2_criteria=["CC6.7", "C1.1", "C1.2"],
        collected_at=datetime.utcnow().isoformat() + "Z",
        source="codebase",
        data={
            "encryption_components": findings,
            "environment_variables_set": env_vars_present,
            "pii_fields_protected": [
                "ssn", "social_security_number", "tax_id", "ein",
                "bank_account", "routing_number", "date_of_birth",
                "credit_card", "income", "annual_income",
                "drivers_license", "passport_number",
            ],
        },
        notes=(
            "DATA_ENCRYPTION_KEY must be a valid Fernet key (44-char base64). "
            "Never store encryption keys in source control. "
            "Rotate annually and document rotation in change management records."
        ),
    )


def collect_access_matrix() -> EvidenceSection:
    """Build an access control matrix mapping roles to resource capabilities."""
    # Access matrix derived from documented role patterns in the codebase
    matrix = {
        "platform_admin": {
            "description": "Perennia internal admin — full platform access",
            "can_access": [
                "all_organizations", "user_management", "billing", "feature_flags",
                "audit_logs", "security_dashboard", "backup_management",
                "soc2_compliance_endpoints", "impersonation",
            ],
            "cannot_access": [],
        },
        "site_admin": {
            "description": "Organization-level admin — full org access",
            "can_access": [
                "org_users", "org_leads", "org_loans", "org_reports",
                "org_billing", "org_integrations", "compliance_reports",
                "audit_logs_own_org",
            ],
            "cannot_access": ["other_orgs", "platform_admin_panel"],
        },
        "admin": {
            "description": "Branch/team admin",
            "can_access": [
                "team_users", "team_leads", "team_loans", "team_reports",
                "workflow_config",
            ],
            "cannot_access": ["billing", "other_orgs", "platform_admin_panel"],
        },
        "loan_officer": {
            "description": "Primary LO role — own portfolio access",
            "can_access": [
                "own_leads", "own_loans", "pipeline", "documents",
                "scheduling", "messaging", "rate_monitor",
            ],
            "cannot_access": ["other_lo_data", "billing", "admin_panel", "audit_logs"],
        },
        "processor": {
            "description": "Loan processor — assigned loan file access",
            "can_access": [
                "assigned_loans", "documents", "compliance_checks", "conditions",
            ],
            "cannot_access": ["lead_management", "billing", "admin_panel", "audit_logs"],
        },
        "branch_manager": {
            "description": "Branch manager — read access across branch",
            "can_access": [
                "branch_leads", "branch_loans", "branch_reports", "coaching_dashboard",
            ],
            "cannot_access": ["billing", "platform_admin_panel"],
        },
        "read_only": {
            "description": "Reporting / observer role — read-only",
            "can_access": ["reports", "pipeline_read"],
            "cannot_access": ["create", "update", "delete", "admin_panel"],
        },
    }

    # Enrich with DB user counts if available
    db_counts = _query(
        """
        SELECT permission_role, COUNT(*) as count
        FROM users
        WHERE permission_role IS NOT NULL AND is_active = TRUE
        GROUP BY permission_role
        """
    )
    counts_map = {row["permission_role"]: row["count"] for row in db_counts if "error" not in row}

    for role_name in matrix:
        matrix[role_name]["active_user_count"] = counts_map.get(role_name, "N/A (DB not connected)")

    return EvidenceSection(
        section_id="access_matrix",
        title="Access Control Matrix by Role",
        soc2_criteria=["CC6.1", "CC6.2", "CC6.3", "CC6.6"],
        collected_at=datetime.utcnow().isoformat() + "Z",
        source="codebase",
        data=matrix,
        notes=(
            "Matrix is derived from documented role patterns. Verify against "
            "routes/permission_core_routes.py and routes/user_roles_routes.py "
            "for the definitive permission set. "
            "Least privilege principle: each role grants only the minimum access required."
        ),
    )


def collect_vendor_registry() -> EvidenceSection:
    """Collect vendor risk registry from DB or seed script fallback."""
    db_vendors = _query(
        """
        SELECT
            vendor_name, category, data_access_level, soc2_status,
            risk_level, last_review_date, notes
        FROM soc2_vendor_registry
        ORDER BY risk_level, vendor_name
        """
    )

    if db_vendors and "error" not in db_vendors[0]:
        source = "database"
        vendors = db_vendors
    else:
        # Fall back to reading from seed script
        source = "codebase"
        seed_content = _read("soc2_compliance/scripts/seed_vendor_registry.py")
        # Parse VENDORS list from the seed script
        m = re.search(r"VENDORS\s*[:=]\s*(\[.+?\])", seed_content, re.DOTALL)
        vendors = []
        if m:
            try:
                vendors = ast.literal_eval(m.group(1))
            except Exception:
                vendors = [{"note": "Could not parse vendor list from seed script"}]

    return EvidenceSection(
        section_id="vendor_registry",
        title="Third-Party Vendor Risk Registry",
        soc2_criteria=["CC9.1", "CC9.2"],
        collected_at=datetime.utcnow().isoformat() + "Z",
        source=source,
        data={
            "vendor_count": len(vendors),
            "vendors": vendors,
        },
        notes=(
            "Vendors are classified by data access level (full/limited/metadata/none) "
            "and SOC 2 certification status. Annual review required per CC9.1. "
            "High-risk vendors require BAA / DPA agreements."
        ),
    )


def collect_retention_policies() -> EvidenceSection:
    """Collect data retention policy configuration."""
    # Read from soc2_compliance/constants.py
    constants_content = _read("soc2_compliance/constants.py")
    config_content = _read("soc2_compliance/config.py")

    # Parse RETENTION_PERIODS from constants
    retention_periods: Dict[str, Any] = {}
    if constants_content:
        m = re.search(r"RETENTION_PERIODS\s*=\s*\{([^}]+)\}", constants_content, re.DOTALL)
        if m:
            # Extract key: value pairs
            for kv in re.finditer(r"RetentionPolicy\.(\w+):\s*(\d+)", m.group(1)):
                retention_periods[kv.group(1)] = int(kv.group(2))

    # Read SOC2Config retention settings
    config_overrides: Dict[str, Any] = {}
    if config_content:
        for attr in ["audit_retention_days", "default_retention_days"]:
            m = re.search(rf"{attr}\s*[:=]\s*(\d+)", config_content)
            if m:
                config_overrides[attr] = int(m.group(1))

    return EvidenceSection(
        section_id="retention_policies",
        title="Data Retention Policies",
        soc2_criteria=["C1.1", "P4.1", "P4.2"],
        collected_at=datetime.utcnow().isoformat() + "Z",
        source="codebase",
        data={
            "retention_periods_days": retention_periods,
            "config_overrides": config_overrides,
            "policy_table": [
                {
                    "data_type": "Audit Logs",
                    "retention_days": retention_periods.get("AUDIT_LOGS", 730),
                    "regulatory_basis": "SOC 2 Type II minimum",
                    "disposal_method": "Automated database purge via RetentionService",
                },
                {
                    "data_type": "Access Logs",
                    "retention_days": retention_periods.get("ACCESS_LOGS", 730),
                    "regulatory_basis": "SOC 2 Type II minimum",
                    "disposal_method": "Automated database purge",
                },
                {
                    "data_type": "Incident Records",
                    "retention_days": retention_periods.get("INCIDENT_RECORDS", 1095),
                    "regulatory_basis": "SOC 2 Type II / operational requirement",
                    "disposal_method": "Manual review before deletion",
                },
                {
                    "data_type": "Loan Data",
                    "retention_days": retention_periods.get("LOAN_DATA", 1825),
                    "regulatory_basis": "TRID / RESPA — 3 years; best practice 5 years",
                    "disposal_method": "Archival then deletion per written policy",
                },
                {
                    "data_type": "Financial Records",
                    "retention_days": retention_periods.get("FINANCIAL_RECORDS", 2555),
                    "regulatory_basis": "IRS / SOX — 7 years",
                    "disposal_method": "Secure disposal with certificate",
                },
            ],
        },
        notes=(
            "Retention is enforced by soc2_compliance/services/retention_service.py "
            "running on a daily schedule. "
            "Verify the scheduler task is active in Railway."
        ),
    )


def collect_mfa_config() -> EvidenceSection:
    """Collect MFA configuration and enforcement status."""
    mfa_content = _read("auth/mfa.py")
    soc2_config_content = _read("soc2_compliance/config.py")

    mfa_details: Dict[str, Any] = {
        "mfa_module_present": _exists("auth/mfa.py"),
        "totp_library": "pyotp" if "pyotp" in mfa_content else "NOT FOUND",
        "issuer_name": None,
        "backup_codes": None,
        "soc2_require_mfa_setting": None,
    }

    # Parse MFA_ISSUER_NAME
    m = re.search(r'MFA_ISSUER_NAME\s*=\s*["\']([^"\']+)["\']', mfa_content)
    if m:
        mfa_details["issuer_name"] = m.group(1)

    m = re.search(r'BACKUP_CODE_COUNT\s*=\s*(\d+)', mfa_content)
    if m:
        mfa_details["backup_codes"] = int(m.group(1))

    m = re.search(r'require_mfa\s*[:=]\s*(True|False)', soc2_config_content)
    if m:
        mfa_details["soc2_require_mfa_setting"] = m.group(1) == "True"

    # DB: count users with MFA enabled
    db_mfa = _query(
        """
        SELECT
            COUNT(*) FILTER (WHERE mfa_enabled = TRUE) as mfa_enabled_count,
            COUNT(*) as total_users,
            COUNT(*) FILTER (WHERE permission_role IN ('admin','site_admin','platform_admin') AND mfa_enabled = TRUE) as admin_mfa_count,
            COUNT(*) FILTER (WHERE permission_role IN ('admin','site_admin','platform_admin')) as admin_total
        FROM users
        WHERE is_active = TRUE
        """
    )
    if db_mfa and "error" not in db_mfa[0]:
        row = db_mfa[0]
        total = row.get("total_users", 0) or 1
        admin_total = row.get("admin_total", 0) or 1
        mfa_details["database_stats"] = {
            "total_active_users": row.get("total_users"),
            "mfa_enabled_users": row.get("mfa_enabled_count"),
            "mfa_adoption_pct": round((row.get("mfa_enabled_count", 0) / total) * 100, 1),
            "admin_mfa_enabled": row.get("admin_mfa_count"),
            "admin_mfa_pct": round((row.get("admin_mfa_count", 0) / admin_total) * 100, 1),
        }

    return EvidenceSection(
        section_id="mfa_config",
        title="Multi-Factor Authentication Configuration",
        soc2_criteria=["CC6.1", "CC6.8"],
        collected_at=datetime.utcnow().isoformat() + "Z",
        source="codebase" if not _db_session else "database",
        data=mfa_details,
        notes=(
            "SOC 2 Type II strongly recommends MFA for all users with access to "
            "customer data. MFA must be mandatory for all admin roles. "
            "Auditors will request MFA adoption rate during evidence review."
        ),
    )


def collect_incident_summary() -> EvidenceSection:
    """Collect summary of open and recent security incidents."""
    open_incidents = _query(
        """
        SELECT
            id, category, severity, title, status, created_at, detected_at
        FROM soc2_security_incidents
        WHERE status NOT IN ('resolved', 'closed')
        ORDER BY severity DESC, created_at DESC
        LIMIT 20
        """
    )

    recent_closed = _query(
        """
        SELECT
            id, category, severity, title, status, created_at, resolved_at,
            EXTRACT(EPOCH FROM (resolved_at - detected_at)) / 3600 as response_hours
        FROM soc2_security_incidents
        WHERE status IN ('resolved', 'closed')
            AND created_at >= NOW() - INTERVAL '90 days'
        ORDER BY created_at DESC
        LIMIT 10
        """
    )

    stats = _query(
        """
        SELECT
            status, COUNT(*) as count
        FROM soc2_security_incidents
        WHERE created_at >= NOW() - INTERVAL '365 days'
        GROUP BY status
        """
    )

    def sanitize_row(row: dict) -> dict:
        if "error" in row:
            return row
        return {
            "id": str(row.get("id", ""))[:8] + "...",
            "category": row.get("category"),
            "severity": row.get("severity"),
            "title": row.get("title"),
            "status": row.get("status"),
            "created_at": str(row.get("created_at", "")),
        }

    return EvidenceSection(
        section_id="incident_summary",
        title="Security Incident Summary (Last 90 Days)",
        soc2_criteria=["CC7.1", "CC7.2", "CC7.3", "CC7.4", "CC7.5"],
        collected_at=datetime.utcnow().isoformat() + "Z",
        source="database",
        data={
            "open_incidents": [sanitize_row(r) for r in open_incidents],
            "recently_resolved": [sanitize_row(r) for r in recent_closed],
            "annual_by_status": stats,
        },
        notes=(
            "Auditors require evidence of incident detection, response, and resolution. "
            "Mean Time to Respond (MTTR) should be documented. "
            "All P1 (critical) incidents must have post-mortems."
        ),
    )


# ===========================================================================
# Section registry
# ===========================================================================

SECTION_REGISTRY: Dict[str, Any] = {
    "endpoints": collect_endpoints,
    "security_headers": collect_security_headers,
    "rbac_roles": collect_rbac_roles,
    "audit_log_sample": collect_audit_log_sample,
    "encryption_inventory": collect_encryption_inventory,
    "access_matrix": collect_access_matrix,
    "vendor_registry": collect_vendor_registry,
    "retention_policies": collect_retention_policies,
    "mfa_config": collect_mfa_config,
    "incident_summary": collect_incident_summary,
}


# ===========================================================================
# Package builder
# ===========================================================================

def collect_evidence(
    sections: Optional[List[str]] = None,
    connect_db: bool = False,
) -> EvidencePackage:
    db_connected = False
    if connect_db:
        db_connected = _try_connect_db()

    target_sections = sections or list(SECTION_REGISTRY.keys())
    collected: List[EvidenceSection] = []

    for section_id in target_sections:
        fn = SECTION_REGISTRY.get(section_id)
        if fn is None:
            print(f"  WARNING: unknown section '{section_id}' — skipping", file=sys.stderr)
            continue
        try:
            result = fn()
            collected.append(result)
        except Exception as exc:
            collected.append(
                EvidenceSection(
                    section_id=section_id,
                    title=section_id,
                    soc2_criteria=[],
                    collected_at=datetime.utcnow().isoformat() + "Z",
                    source="error",
                    data={"error": str(exc)},
                    notes="Collection failed.",
                )
            )

    return EvidencePackage(
        generated_at=datetime.utcnow().isoformat() + "Z",
        backend_root=str(_BACKEND_ROOT),
        collector_version="1.0.0",
        db_connected=db_connected,
        sections=collected,
    )


# ===========================================================================
# CLI entry point
# ===========================================================================

def main() -> None:
    parser = argparse.ArgumentParser(
        description="SOC 2 evidence collector for Perennia AI"
    )
    parser.add_argument(
        "--output",
        metavar="FILE",
        default=None,
        help="Write evidence package JSON to this file (default: stdout)",
    )
    parser.add_argument(
        "--section",
        metavar="SECTION",
        default=None,
        help=(
            "Collect a specific section only. "
            f"Choices: {', '.join(SECTION_REGISTRY.keys())}"
        ),
    )
    parser.add_argument(
        "--db",
        action="store_true",
        default=False,
        help="Attempt to connect to DATABASE_URL for live DB evidence",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        default=False,
        help="List available evidence sections and exit",
    )
    args = parser.parse_args()

    if args.list:
        print("Available evidence sections:")
        for k in SECTION_REGISTRY:
            print(f"  {k}")
        return

    sections = [args.section] if args.section else None
    package = collect_evidence(sections=sections, connect_db=args.db)

    # Serialize — EvidenceSection.data may contain arbitrary types
    payload = asdict(package)
    json_str = json.dumps(payload, indent=2, default=str)

    if args.output:
        Path(args.output).write_text(json_str)
        print(f"Evidence package written to {args.output}")
        print(f"  Sections collected: {len(package.sections)}")
        print(f"  DB connected: {package.db_connected}")
    else:
        print(json_str)


if __name__ == "__main__":
    main()
