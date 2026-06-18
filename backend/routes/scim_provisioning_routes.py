"""
SCIM 2.0 Provisioning, CSV Bulk Import, and MFA Onboarding Routes
Enterprise Readiness Domain 5 (Onboarding & Provisioning)

Covers:
    Check 5.11 - SCIM 2.0 User provisioning (RFC 7644)
    Check 5.12 - CSV bulk user import
    Check 5.15 - MFA wired into onboarding flow

Registration pattern: function-based (same as gdpr_routes, compliance_routes)

SCIM Endpoints (Bearer token auth via SCIM API token):
    GET    /scim/v2/Users          - List/filter users (RFC 7644 Section 3.4.2)
    POST   /scim/v2/Users          - Create user (RFC 7644 Section 3.3)
    GET    /scim/v2/Users/{id}     - Get user (RFC 7644 Section 3.4.1)
    PUT    /scim/v2/Users/{id}     - Replace user (RFC 7644 Section 3.5.1)
    PATCH  /scim/v2/Users/{id}     - Update user (RFC 7644 Section 3.5.2)
    DELETE /scim/v2/Users/{id}     - Deactivate user (RFC 7644 Section 3.6)

CSV Bulk Import Endpoint:
    POST   /api/v1/admin/users/import-csv  - Upload CSV for bulk user creation

MFA Onboarding Endpoints:
    POST   /api/v1/onboarding/mfa/setup    - Generate TOTP secret + QR code
    POST   /api/v1/onboarding/mfa/verify   - Verify TOTP code to complete enrollment
    GET    /api/v1/onboarding/mfa/status   - Check MFA requirement/completion status
"""

import csv
import io
import json
import logging
import os
import re
import secrets
import hashlib
import threading
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import Depends, HTTPException, Request, UploadFile, File, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# ============================================================================
# SCIM-Specific Rate Limiting (Enterprise Readiness 5.x)
# ============================================================================
# Separate from the global API rate limiter. SCIM endpoints get their own
# budget to prevent bulk provisioning abuse from IdP sync storms.

try:
    from middleware.rate_limiter import rate_limit, ip_key, RateLimiter

    def _scim_token_key(request: Request) -> str:
        """Rate-limit key based on SCIM bearer token hash.

        Groups all requests from the same IdP token together, regardless
        of IP address.  Falls back to IP if no bearer token is present.
        """
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            token_hash = hashlib.sha256(token.encode()).hexdigest()[:16]
            return f"scim_token:{token_hash}"
        return ip_key(request)

    # SCIM rate limit profiles
    # Individual SCIM operations: 100/minute per token
    SCIM_OP_LIMIT = rate_limit(limit=100, window=60, key_func=_scim_token_key)
    # SCIM list/search (heavier queries): 30/minute per token
    SCIM_LIST_LIMIT = rate_limit(limit=30, window=60, key_func=_scim_token_key)
    # CSV bulk import: 5/hour per user (very expensive)
    SCIM_BULK_LIMIT = rate_limit(limit=5, window=3600)
    _SCIM_RL_AVAILABLE = True

except ImportError:
    logger.warning("Rate limiter unavailable for SCIM routes — running without SCIM rate limits")

    def _noop_decorator(func):
        return func

    SCIM_OP_LIMIT = _noop_decorator
    SCIM_LIST_LIMIT = _noop_decorator
    SCIM_BULK_LIMIT = _noop_decorator
    _SCIM_RL_AVAILABLE = False


# ============================================================================
# Per-Tenant SCIM Connection Guard
# ============================================================================
# SCIM bulk operations can exhaust DB connections for a single tenant.
# This guard checks the per-tenant connection tracking from db.py before
# allowing SCIM operations to proceed.

_scim_tenant_conn_counts: dict = {}
_scim_tenant_conn_lock = threading.Lock()
# SCIM gets a lower per-tenant limit than general API (default: 3 out of 5)
MAX_SCIM_CONNECTIONS_PER_TENANT = int(os.getenv("MAX_SCIM_CONNECTIONS_PER_TENANT", "3"))


def _check_scim_tenant_connection_limit(org_id: Optional[int]) -> None:
    """Check if the tenant has capacity for another SCIM DB operation.

    Raises HTTPException 503 if the tenant's SCIM connection budget is
    exhausted.  This is separate from (and stricter than) the general
    per-tenant limit in db.py — SCIM should not consume the org's entire
    connection budget.
    """
    if not org_id or MAX_SCIM_CONNECTIONS_PER_TENANT <= 0:
        return
    with _scim_tenant_conn_lock:
        current = _scim_tenant_conn_counts.get(org_id, 0)
        if current >= MAX_SCIM_CONNECTIONS_PER_TENANT:
            logger.warning(
                f"SCIM tenant connection limit reached for org_id={org_id} "
                f"(current={current}, max={MAX_SCIM_CONNECTIONS_PER_TENANT})"
            )
            raise HTTPException(
                status_code=503,
                detail=_scim_error(
                    503,
                    "Too many concurrent SCIM operations for this tenant. Please retry shortly.",
                ),
                headers={"Retry-After": "5"},
            )
        _scim_tenant_conn_counts[org_id] = current + 1


def _release_scim_tenant_connection(org_id: Optional[int]) -> None:
    """Release a SCIM tenant connection slot."""
    if not org_id:
        return
    with _scim_tenant_conn_lock:
        current = _scim_tenant_conn_counts.get(org_id, 1)
        if current <= 1:
            _scim_tenant_conn_counts.pop(org_id, None)
        else:
            _scim_tenant_conn_counts[org_id] = current - 1


# ============================================================================
# Audit Logging Helper
# ============================================================================

def _write_audit_log(
    db: Session,
    user_id: int,
    changed_by_id: int,
    change_type: str,
    entity_type: str,
    entity_id: int = None,
    before_state: dict = None,
    after_state: dict = None,
    ip_address: str = None,
    reason: str = None,
    scim_token_hash: str = None,
):
    """
    Write a hash-chained audit log entry for SCIM/CSV provisioning operations.

    Uses the enterprise audit service (services/audit_service.py) which provides
    SHA-256 hash-chained append-only audit entries with tamper detection.

    When scim_token_hash is provided, it is included in after_state so auditors
    can trace which API token was used for the operation.
    """
    try:
        # Inject SCIM token identity into the audit trail
        if scim_token_hash:
            after_state = dict(after_state) if after_state else {}
            after_state["_scim_token_hash"] = scim_token_hash
            after_state["_scim_operation"] = change_type
            after_state["_scim_timestamp"] = datetime.now(timezone.utc).isoformat()

        from services.audit_service import create_audit_entry

        create_audit_entry(
            db=db,
            user_id=user_id,
            changed_by_id=changed_by_id,
            change_type=change_type,
            entity_type=entity_type,
            entity_id=entity_id,
            before_state=before_state,
            after_state=after_state,
            ip_address=ip_address,
            reason=reason,
        )
    except Exception as e:
        # Audit logging must never block the provisioning operation.
        # Log the failure so it can be investigated, but do not re-raise.
        logger.error(f"Failed to write audit log for {change_type}: {e}")

# SCIM 2.0 schema URIs
SCIM_USER_SCHEMA = "urn:ietf:params:scim:schemas:core:2.0:User"
SCIM_ENTERPRISE_SCHEMA = "urn:ietf:params:scim:schemas:extension:enterprise:2.0:User"
SCIM_GROUP_SCHEMA = "urn:ietf:params:scim:schemas:core:2.0:Group"
SCIM_LIST_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:ListResponse"
SCIM_ERROR_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:Error"
SCIM_PATCH_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:PatchOp"

# Valid SCIM sortBy attributes
VALID_SORT_ATTRS = {"userName", "name.familyName", "name.givenName", "displayName", "active"}

# Default SCIM API token env var
SCIM_TOKEN_ENV = "SCIM_API_TOKEN"

# Valid roles for CSV import
VALID_IMPORT_ROLES = {
    "loan_officer", "processor", "underwriter", "closer",
    "manager", "sales", "processing", "operations",
    "leadership", "site_admin",
}


# ============================================================================
# Request / Response Schemas
# ============================================================================

class MfaSetupResponse(BaseModel):
    secret: str
    provisioning_uri: str
    qr_code_base64: Optional[str] = None
    backup_codes: Optional[List[str]] = None


class MfaVerifyRequest(BaseModel):
    token: str = Field(..., min_length=6, max_length=6, description="6-digit TOTP code")


class CsvImportRow(BaseModel):
    email: str
    name: str
    role: str = "loan_officer"
    branch: Optional[str] = None


# ============================================================================
# Helpers
# ============================================================================

def _scim_error(status: int, detail: str, scim_type: Optional[str] = None) -> dict:
    """Build a SCIM 2.0 error response body (RFC 7644 Section 3.12)."""
    err = {
        "schemas": [SCIM_ERROR_SCHEMA],
        "detail": detail,
        "status": str(status),
    }
    if scim_type:
        err["scimType"] = scim_type
    return err


def _user_to_scim(row, base_url: str = "") -> dict:
    """Convert a DB user row to SCIM 2.0 User resource (RFC 7643 Section 4.1 + 4.3)."""
    user_id = str(row.id)
    first_name = row.first_name or ""
    last_name = row.last_name or ""
    display_name = f"{first_name} {last_name}".strip() or row.email

    resource = {
        "schemas": [SCIM_USER_SCHEMA],
        "id": user_id,
        "userName": row.email,
        "name": {
            "givenName": first_name,
            "familyName": last_name,
            "formatted": display_name,
        },
        "displayName": display_name,
        "active": bool(row.is_active),
        "emails": [
            {
                "value": row.email,
                "type": "work",
                "primary": True,
            }
        ],
        "meta": {
            "resourceType": "User",
            "location": f"{base_url}/scim/v2/Users/{user_id}",
            "created": row.created_at.isoformat() if row.created_at else None,
        },
    }

    # phoneNumbers (RFC 7643 Section 4.1.2)
    phone_numbers = []
    if hasattr(row, "phone") and row.phone:
        phone_numbers.append({
            "value": row.phone,
            "type": "work",
            "primary": True,
        })
    if phone_numbers:
        resource["phoneNumbers"] = phone_numbers

    # addresses (RFC 7643 Section 4.1.2)
    addresses = []
    if hasattr(row, "business_address") and row.business_address:
        addresses.append({
            "value": row.business_address,
            "formatted": row.business_address,
            "type": "work",
            "primary": True,
        })
    if addresses:
        resource["addresses"] = addresses

    # title (RFC 7643 Section 4.1.1)
    if hasattr(row, "title") and row.title:
        resource["title"] = row.title

    # Enterprise extension (RFC 7643 Section 4.3)
    enterprise_ext = {}

    # employeeNumber — prefer nmls_number, fall back to nmls_id
    employee_number = None
    if hasattr(row, "nmls_number") and row.nmls_number:
        employee_number = row.nmls_number
    elif hasattr(row, "nmls_id") and row.nmls_id:
        employee_number = row.nmls_id
    if employee_number:
        enterprise_ext["employeeNumber"] = employee_number

    # department — use branch_name if joined, else team_name, else permission_role
    department = None
    if hasattr(row, "branch_name") and row.branch_name:
        department = row.branch_name
    elif hasattr(row, "team_name") and row.team_name:
        department = row.team_name
    elif hasattr(row, "permission_role") and row.permission_role:
        department = row.permission_role
    if department:
        enterprise_ext["department"] = department

    if hasattr(row, "organization_id") and row.organization_id:
        enterprise_ext["organization"] = str(row.organization_id)

    # manager (RFC 7643 Section 4.3 — $ref + value + displayName)
    if hasattr(row, "manager_id") and row.manager_id:
        manager_ref = {
            "value": str(row.manager_id),
            "$ref": f"{base_url}/scim/v2/Users/{row.manager_id}",
        }
        if hasattr(row, "manager_display_name") and row.manager_display_name:
            manager_ref["displayName"] = row.manager_display_name
        enterprise_ext["manager"] = manager_ref

    if enterprise_ext:
        resource["schemas"].append(SCIM_ENTERPRISE_SCHEMA)
        resource[SCIM_ENTERPRISE_SCHEMA] = enterprise_ext

    return resource


def _validate_scim_token(request: Request) -> tuple:
    """
    Validate the SCIM Bearer token from the Authorization header.
    Returns (token_str, token_hash_prefix) if valid.
    The token_hash_prefix is a truncated SHA-256 for audit logging (never
    stores the raw token in logs).

    Raises HTTPException otherwise.

    The SCIM token is a separate credential from user JWT tokens, stored
    in the SCIM_API_TOKEN environment variable. Identity providers (Okta,
    Azure AD, etc.) send this token with each SCIM request.
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        logger.warning(
            "SCIM auth failed: missing/invalid Authorization header from %s",
            request.client.host if request.client else "unknown",
        )
        raise HTTPException(
            status_code=401,
            detail=_scim_error(401, "Missing or invalid Authorization header"),
        )

    token = auth_header[7:]
    expected_token = os.getenv(SCIM_TOKEN_ENV)

    if not expected_token:
        logger.error("SCIM_API_TOKEN environment variable not set")
        raise HTTPException(
            status_code=500,
            detail=_scim_error(500, "SCIM provisioning is not configured"),
        )

    if not secrets.compare_digest(token, expected_token):
        # Log failed auth attempt with IP for security monitoring
        logger.warning(
            "SCIM auth failed: invalid bearer token from %s",
            request.client.host if request.client else "unknown",
        )
        raise HTTPException(
            status_code=401,
            detail=_scim_error(401, "Invalid SCIM bearer token"),
        )

    # Compute a truncated hash for audit logging — enough to identify the
    # token without exposing the full credential
    token_hash = hashlib.sha256(token.encode()).hexdigest()[:16]

    logger.debug(
        "SCIM token validated: hash_prefix=%s ip=%s path=%s",
        token_hash,
        request.client.host if request.client else "unknown",
        request.url.path,
    )

    return token, token_hash


def _parse_scim_filter(filter_str: str) -> Optional[tuple]:
    """
    Parse a single SCIM filter clause into (attribute, operator, value).

    Supports RFC 7644 Section 3.4.2.2 filter operators:
        eq  — equals (exact match, case-insensitive for strings)
        co  — contains (substring match)
        sw  — starts with (prefix match)

    Examples:
        userName eq "john@example.com"
        displayName co "John"
        name.familyName sw "Sm"
        active eq true

    Returns None if the filter cannot be parsed.
    """
    # Pattern: attribute SPACE operator SPACE value
    # Value is either "quoted string" or true/false (boolean)
    match = re.match(
        r'(\S+)\s+(eq|co|sw)\s+(?:"([^"]*)"|(\S+))',
        filter_str.strip(),
        re.IGNORECASE,
    )
    if not match:
        return None

    attr = match.group(1)
    op = match.group(2).lower()
    # Quoted string value or bare value (for booleans)
    value = match.group(3) if match.group(3) is not None else match.group(4)
    return (attr, op, value)


def _parse_compound_scim_filter(filter_str: str) -> list:
    """
    Parse a compound SCIM filter expression (RFC 7644 Section 3.4.2.2).

    Supports:
        - Single filters: userName eq "john@example.com"
        - Compound AND: userName eq "john@example.com" and active eq true
        - Compound OR: userName sw "john" or userName sw "jane"

    AND takes precedence over OR per the RFC. For simplicity, this
    implementation handles:
        - Multiple clauses joined by "and" -> all must match (SQL AND)
        - Multiple clauses joined by "or"  -> any must match (SQL OR)
        - Mixed and/or: splits on "or" first, then "and" within each group

    Returns a list of dicts, each with:
        - "clauses": list of (attr, op, value) tuples
        - "conjunction": "and" or "or" (how clauses relate to each other)

    For simple cases (no "or"), returns a single group with conjunction="and".
    The caller joins groups with OR and clauses within each group with AND.
    """
    if not filter_str or not filter_str.strip():
        return []

    filter_str = filter_str.strip()

    # Check for "or" at the top level (case-insensitive, word boundary)
    # Split on " or " (space-delimited to avoid matching inside quoted values)
    or_groups = re.split(r'\s+or\s+', filter_str, flags=re.IGNORECASE)

    result = []
    for group_str in or_groups:
        # Split each OR group on " and "
        and_clauses_raw = re.split(r'\s+and\s+', group_str.strip(), flags=re.IGNORECASE)
        clauses = []
        for clause_str in and_clauses_raw:
            parsed = _parse_scim_filter(clause_str)
            if parsed:
                clauses.append(parsed)
        if clauses:
            result.append(clauses)

    return result


# Map SCIM attribute names to SQL column references (using 'u.' alias)
_SCIM_ATTR_TO_COLUMN = {
    "userName": "u.email",
    "emails.value": "u.email",
    "name.givenName": "u.first_name",
    "name.familyName": "u.last_name",
    "displayName": "u.first_name",  # best effort — display is computed from first+last
    "title": "u.title",
    "phoneNumbers.value": "u.phone",
    "active": "u.is_active",
    # Enterprise extension attributes
    "urn:ietf:params:scim:schemas:extension:enterprise:2.0:User:employeeNumber": "u.nmls_number",
    "urn:ietf:params:scim:schemas:extension:enterprise:2.0:User:department": "b.name",
    "urn:ietf:params:scim:schemas:extension:enterprise:2.0:User:manager.value": "u.manager_id",
}


def _build_filter_clause(attr: str, op: str, value: str, param_suffix: str = "") -> tuple:
    """
    Build a SQL WHERE clause fragment from a parsed SCIM filter.

    Args:
        attr: SCIM attribute name.
        op: Filter operator (eq, co, sw).
        value: Filter value.
        param_suffix: Optional suffix to make param keys unique in compound filters.

    Returns (clause_sql, param_key, param_value).
    Returns (None, None, None) if the attribute is not supported.
    """
    column = _SCIM_ATTR_TO_COLUMN.get(attr)
    if not column:
        return (None, None, None)

    param_key = f"scim_filter_val{param_suffix}"

    # Boolean attribute (active)
    if attr == "active":
        if op != "eq":
            return (None, None, None)
        bool_val = value.lower() == "true"
        return (f"{column} = :{param_key}", param_key, bool_val)

    # String attributes
    if op == "eq":
        return (f"LOWER({column}) = LOWER(:{param_key})", param_key, value)
    elif op == "co":
        return (f"LOWER({column}) LIKE LOWER(:{param_key})", param_key, f"%{value}%")
    elif op == "sw":
        return (f"LOWER({column}) LIKE LOWER(:{param_key})", param_key, f"{value}%")

    return (None, None, None)


def _apply_enterprise_ext(ext: dict, update_fields: dict):
    """
    Apply enterprise extension attributes (RFC 7643 Section 4.3) to the
    update_fields dict used by SCIM PATCH/PUT operations.

    Maps:
        employeeNumber -> nmls_number
        department     -> permission_role (if valid role) or team_name
        manager        -> manager_id
    """
    if "employeeNumber" in ext:
        update_fields["nmls_number"] = str(ext["employeeNumber"]) if ext["employeeNumber"] else None
    if "department" in ext:
        dept = ext["department"]
        if isinstance(dept, str) and dept in VALID_IMPORT_ROLES:
            update_fields["permission_role"] = dept
            update_fields["role"] = dept
        elif isinstance(dept, str):
            update_fields["team_name"] = dept
    if "manager" in ext:
        mgr = ext["manager"]
        if isinstance(mgr, dict):
            mgr_id = mgr.get("value")
        else:
            mgr_id = mgr
        if mgr_id is not None:
            try:
                update_fields["manager_id"] = int(mgr_id)
            except (ValueError, TypeError):
                pass


def _get_scim_org_id(db: Session, request: Request = None) -> Optional[int]:
    """
    Determine the organization_id to scope SCIM operations.

    Multi-IdP tenant isolation strategy (checked in order):
    1. X-Scim-Tenant-Id header — explicit org ID from IdP/proxy config
    2. SCIM_ORG_ID environment variable — single-tenant deployments
    3. Lookup via sso_configurations where the SCIM token is associated
       with an org that has active SSO (first active org as last resort)

    In production multi-tenant deployments, configure IdP to send
    X-Scim-Tenant-Id or use per-org SCIM tokens.
    """
    # 1. Explicit tenant header
    if request:
        tenant_header = request.headers.get("X-Scim-Tenant-Id")
        if tenant_header:
            try:
                org_id = int(tenant_header)
                # Verify org exists and is active
                row = db.execute(text(
                    "SELECT id FROM organizations WHERE id = :org_id AND is_active = true"
                ), {"org_id": org_id}).fetchone()
                if row:
                    return row.id
                logger.warning(
                    f"X-Scim-Tenant-Id header value {tenant_header} does not match "
                    f"an active organization"
                )
            except (ValueError, TypeError):
                logger.warning(f"Invalid X-Scim-Tenant-Id header value: {tenant_header}")

    # 2. Environment variable for single-tenant deployments
    env_org_id = os.getenv("SCIM_ORG_ID")
    if env_org_id:
        try:
            return int(env_org_id)
        except (ValueError, TypeError):
            logger.warning(f"Invalid SCIM_ORG_ID env var: {env_org_id}")

    # 3. Fallback: first active org (logs warning for visibility)
    row = db.execute(text(
        "SELECT id FROM organizations WHERE is_active = true ORDER BY id LIMIT 1"
    )).fetchone()
    if row:
        logger.warning(
            f"SCIM request using fallback org_id={row.id} (first active org). "
            f"Configure X-Scim-Tenant-Id header or SCIM_ORG_ID env var for "
            f"proper multi-tenant isolation."
        )
        return row.id
    return None


def _hash_password(password: str) -> str:
    """Hash a password for new user creation."""
    try:
        import bcrypt
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")
    except ImportError:
        import hashlib
        return hashlib.sha256(password.encode()).hexdigest()


def _validate_email(email: str) -> bool:
    """Basic email validation."""
    return bool(re.match(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$", email))


# ============================================================================
# Route Registration
# ============================================================================

def register_scim_provisioning_routes(app, get_db, get_current_user, **kwargs):
    """
    Register SCIM 2.0 provisioning, CSV bulk import, and MFA onboarding routes.

    Enterprise Readiness:
        5.11 - SCIM 2.0 Users endpoint (RFC 7644)
        5.12 - CSV bulk user import with dry-run
        5.15 - MFA setup/verify wired into onboarding
    """

    # ========================================================================
    # SCIM 2.0 ENDPOINTS (Check 5.11)
    # ========================================================================

    @app.get("/scim/v2/Users", tags=["SCIM"])
    @SCIM_LIST_LIMIT
    async def scim_list_users(
        request: Request,
        startIndex: int = Query(1, ge=1, alias="startIndex"),
        count: int = Query(100, ge=1, le=500, alias="count"),
        filter: Optional[str] = Query(None),
        sortBy: Optional[str] = Query(None, alias="sortBy"),
        sortOrder: Optional[str] = Query("ascending", alias="sortOrder"),
        db: Session = Depends(get_db),
    ):
        """
        SCIM 2.0 - List/search users (RFC 7644 Section 3.4.2).

        Supports filter on userName eq "...", active eq true/false.
        Pagination via startIndex and count.
        Rate limited: 30 requests/minute per SCIM token.
        """
        _token, token_hash = _validate_scim_token(request)

        org_id = _get_scim_org_id(db, request)
        _check_scim_tenant_connection_limit(org_id)
        params: dict = {"limit": count, "offset": startIndex - 1}
        where_clauses = []

        if org_id is not None:
            where_clauses.append("u.organization_id = :org_id")
            params["org_id"] = org_id

        # Parse SCIM filter (RFC 7644 Section 3.4.2.2)
        # Supports operators: eq (equals), co (contains), sw (starts with)
        # Supports compound filters: "and" / "or" connectors
        # Supports attributes: userName, active, displayName, name.familyName,
        #   name.givenName, emails.value, title, phoneNumbers.value
        if filter:
            or_groups = _parse_compound_scim_filter(filter)
            if or_groups:
                # Build SQL: (clause1 AND clause2) OR (clause3 AND clause4)
                or_sql_parts = []
                clause_idx = 0
                for and_clauses in or_groups:
                    and_sql_parts = []
                    for attr, op, value in and_clauses:
                        clause, param_key, param_val = _build_filter_clause(
                            attr, op, value, param_suffix=f"_{clause_idx}"
                        )
                        if clause:
                            and_sql_parts.append(clause)
                            params[param_key] = param_val
                        clause_idx += 1
                    if and_sql_parts:
                        or_sql_parts.append("(" + " AND ".join(and_sql_parts) + ")")
                if or_sql_parts:
                    if len(or_sql_parts) == 1:
                        where_clauses.append(or_sql_parts[0])
                    else:
                        where_clauses.append("(" + " OR ".join(or_sql_parts) + ")")

        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

        # Sorting
        order_column = "u.id"
        if sortBy == "userName":
            order_column = "u.email"
        elif sortBy in ("name.familyName",):
            order_column = "u.last_name"
        elif sortBy in ("name.givenName",):
            order_column = "u.first_name"
        elif sortBy == "displayName":
            order_column = "u.first_name"

        order_dir = "DESC" if sortOrder and sortOrder.lower() == "descending" else "ASC"

        # Count total (uses same alias + joins as the main query for filter consistency)
        count_sql = (
            "SELECT COUNT(*) as cnt FROM users u"
            " LEFT JOIN branches b ON b.id = u.branch_id"
            " LEFT JOIN users m ON m.id = u.manager_id"
            " WHERE " + where_sql
        )
        total_row = db.execute(text(count_sql), params).fetchone()
        total_count = total_row.cnt if total_row else 0

        # Fetch page — include columns for enterprise extension (RFC 7643 Section 4.3)
        select_sql = (
            "SELECT u.id, u.email, u.first_name, u.last_name, u.is_active,"
            "       u.permission_role, u.organization_id, u.created_at,"
            "       u.phone, u.business_address, u.title, u.team_name,"
            "       u.nmls_number, u.nmls_id, u.manager_id,"
            "       b.name AS branch_name,"
            "       COALESCE(m.first_name || ' ' || m.last_name, '') AS manager_display_name"
            " FROM users u"
            " LEFT JOIN branches b ON b.id = u.branch_id"
            " LEFT JOIN users m ON m.id = u.manager_id"
            " WHERE " + where_sql +
            " ORDER BY " + order_column + " " + order_dir +
            " LIMIT :limit OFFSET :offset"
        )
        rows = db.execute(text(select_sql), params).fetchall()

        base_url = str(request.base_url).rstrip("/")
        resources = [_user_to_scim(r, base_url) for r in rows]

        _release_scim_tenant_connection(org_id)

        # Audit: SCIM list/search operation
        _write_audit_log(
            db=db,
            user_id=0,
            changed_by_id=0,
            change_type="scim_list_users",
            entity_type="scim_provisioning",
            after_state={
                "filter": filter,
                "startIndex": startIndex,
                "count": count,
                "totalResults": total_count,
            },
            ip_address=request.client.host if request.client else None,
            reason="SCIM 2.0 user list/search (IdP-initiated)",
            scim_token_hash=token_hash,
        )
        db.commit()

        return {
            "schemas": [SCIM_LIST_SCHEMA],
            "totalResults": total_count,
            "startIndex": startIndex,
            "itemsPerPage": count,
            "Resources": resources,
        }

    @app.post("/scim/v2/Users", tags=["SCIM"], status_code=201)
    @SCIM_OP_LIMIT
    async def scim_create_user(
        request: Request,
        db: Session = Depends(get_db),
    ):
        """
        SCIM 2.0 - Create user (RFC 7644 Section 3.3).

        Expects SCIM User JSON with userName, name, active, emails.
        Creates a deactivated-password user (IdP-managed).
        Rate limited: 100 requests/minute per SCIM token.
        """
        _token, token_hash = _validate_scim_token(request)

        try:
            body = await request.json()
        except Exception as e:
            logger.error(f"Error parsing SCIM create user JSON body: {e}")
            raise HTTPException(
                status_code=400,
                detail=_scim_error(400, "Invalid JSON body"),
            )

        # Extract fields from SCIM User resource
        user_name = body.get("userName")
        if not user_name or not _validate_email(user_name):
            raise HTTPException(
                status_code=400,
                detail=_scim_error(400, "userName (valid email) is required", "invalidValue"),
            )

        name_obj = body.get("name", {})
        first_name = name_obj.get("givenName", "")
        last_name = name_obj.get("familyName", "")
        display_name = body.get("displayName", f"{first_name} {last_name}".strip())
        is_active = body.get("active", True)

        # Check for duplicate
        existing = db.execute(
            text("SELECT id FROM users WHERE email = :email"), {"email": user_name}
        ).fetchone()
        if existing:
            raise HTTPException(
                status_code=409,
                detail=_scim_error(409, f"User with userName '{user_name}' already exists", "uniqueness"),
            )

        org_id = _get_scim_org_id(db, request)
        _check_scim_tenant_connection_limit(org_id)

        # Enterprise extension (RFC 7643 Section 4.3)
        enterprise = body.get(SCIM_ENTERPRISE_SCHEMA, {})
        role = enterprise.get("department", "sales")
        if role not in VALID_IMPORT_ROLES:
            role = "sales"

        employee_number = enterprise.get("employeeNumber")
        manager_id = None
        if "manager" in enterprise:
            mgr = enterprise["manager"]
            mgr_val = mgr.get("value") if isinstance(mgr, dict) else mgr
            if mgr_val is not None:
                try:
                    manager_id = int(mgr_val)
                except (ValueError, TypeError):
                    pass

        # phoneNumbers (RFC 7643 Section 4.1.2)
        phone = None
        phone_numbers = body.get("phoneNumbers", [])
        for pn in phone_numbers:
            if pn.get("primary"):
                phone = pn.get("value")
                break
        if phone is None and phone_numbers:
            phone = phone_numbers[0].get("value")

        # addresses (RFC 7643 Section 4.1.2)
        business_address = None
        addresses = body.get("addresses", [])
        for addr in addresses:
            if addr.get("primary"):
                business_address = addr.get("formatted") or addr.get("value", "")
                break
        if business_address is None and addresses:
            business_address = addresses[0].get("formatted") or addresses[0].get("value", "")

        # title (RFC 7643 Section 4.1.1)
        title = body.get("title")

        # Create with random password (IdP-managed, password login not used)
        random_pw = secrets.token_urlsafe(32)
        hashed = _hash_password(random_pw)

        result = db.execute(
            text("""
                INSERT INTO users (
                    email, hashed_password, first_name, last_name,
                    permission_role, role, organization_id, is_active,
                    sso_provider, sso_subject_id,
                    phone, business_address, title, nmls_number, manager_id,
                    created_at
                ) VALUES (
                    :email, :hashed_password, :first_name, :last_name,
                    :permission_role, :role, :org_id, :is_active,
                    'scim', :external_id,
                    :phone, :business_address, :title, :nmls_number, :manager_id,
                    NOW()
                )
                RETURNING id, email, first_name, last_name, is_active,
                          permission_role, organization_id, created_at,
                          phone, business_address, title, nmls_number, nmls_id, manager_id,
                          team_name
            """),
            {
                "email": user_name,
                "hashed_password": hashed,
                "first_name": first_name,
                "last_name": last_name,
                "permission_role": role,
                "role": role,
                "org_id": org_id,
                "is_active": is_active,
                "external_id": body.get("externalId", ""),
                "phone": phone,
                "business_address": business_address,
                "title": title,
                "nmls_number": employee_number,
                "manager_id": manager_id,
            },
        )

        new_user = result.fetchone()
        db.commit()

        # Auto-provision SchedulerConfig for the new SCIM user so they can
        # use the calendar immediately without a manual seed step.
        try:
            from services.scheduler_provisioning import auto_provision_scheduler_config
            await auto_provision_scheduler_config(
                user_id=new_user.id,
                organization_id=org_id,
                db=db,
                user_email=user_name,
            )
        except Exception as _sched_exc:
            logger.warning(
                "scim_create_user: scheduler auto-provision failed for user_id=%s — %s",
                new_user.id if new_user else "unknown", _sched_exc,
            )

        # Audit: SCIM user creation
        _write_audit_log(
            db=db,
            user_id=new_user.id,
            changed_by_id=new_user.id,  # SCIM-provisioned (no human actor)
            change_type="scim_create_user",
            entity_type="scim_provisioning",
            entity_id=new_user.id,
            after_state={
                "email": user_name,
                "first_name": first_name,
                "last_name": last_name,
                "role": role,
                "is_active": is_active,
                "organization_id": org_id,
                "external_id": body.get("externalId", ""),
            },
            ip_address=request.client.host if request.client else None,
            reason="SCIM 2.0 user provisioning (IdP-initiated)",
            scim_token_hash=token_hash,
        )
        db.commit()

        _release_scim_tenant_connection(org_id)

        base_url = str(request.base_url).rstrip("/")
        scim_resource = _user_to_scim(new_user, base_url)
        scim_resource["externalId"] = body.get("externalId", "")

        return scim_resource

    @app.get("/scim/v2/Users/{user_id}", tags=["SCIM"])
    @SCIM_OP_LIMIT
    async def scim_get_user(
        user_id: int,
        request: Request,
        db: Session = Depends(get_db),
    ):
        """SCIM 2.0 - Get user by ID (RFC 7644 Section 3.4.1).
        Rate limited: 100 requests/minute per SCIM token."""
        _token, token_hash = _validate_scim_token(request)

        row = db.execute(
            text("""
                SELECT u.id, u.email, u.first_name, u.last_name, u.is_active,
                       u.permission_role, u.organization_id, u.created_at,
                       u.phone, u.business_address, u.title, u.team_name,
                       u.nmls_number, u.nmls_id, u.manager_id,
                       b.name AS branch_name,
                       COALESCE(m.first_name || ' ' || m.last_name, '') AS manager_display_name
                FROM users u
                LEFT JOIN branches b ON b.id = u.branch_id
                LEFT JOIN users m ON m.id = u.manager_id
                WHERE u.id = :user_id
            """),
            {"user_id": user_id},
        ).fetchone()

        if not row:
            raise HTTPException(
                status_code=404,
                detail=_scim_error(404, f"User {user_id} not found"),
            )

        base_url = str(request.base_url).rstrip("/")
        return _user_to_scim(row, base_url)

    @app.put("/scim/v2/Users/{user_id}", tags=["SCIM"])
    @SCIM_OP_LIMIT
    async def scim_replace_user(
        user_id: int,
        request: Request,
        db: Session = Depends(get_db),
    ):
        """SCIM 2.0 - Replace user (RFC 7644 Section 3.5.1).
        Rate limited: 100 requests/minute per SCIM token."""
        _token, token_hash = _validate_scim_token(request)

        try:
            body = await request.json()
        except Exception as e:
            logger.error(f"Error parsing SCIM replace user JSON body: {e}")
            raise HTTPException(
                status_code=400,
                detail=_scim_error(400, "Invalid JSON body"),
            )

        # Fetch existing user for 404 check and audit before-state
        existing = db.execute(
            text("""
                SELECT id, email, first_name, last_name, is_active, permission_role
                FROM users WHERE id = :user_id
            """),
            {"user_id": user_id},
        ).fetchone()
        if not existing:
            raise HTTPException(
                status_code=404,
                detail=_scim_error(404, f"User {user_id} not found"),
            )

        before_state = {
            "email": existing.email,
            "first_name": existing.first_name,
            "last_name": existing.last_name,
            "is_active": existing.is_active,
            "role": existing.permission_role,
        }

        name_obj = body.get("name", {})
        first_name = name_obj.get("givenName", "")
        last_name = name_obj.get("familyName", "")
        is_active = body.get("active", True)

        # Extract email from userName or emails array
        user_name = body.get("userName")
        if not user_name:
            emails = body.get("emails", [])
            for em in emails:
                if em.get("primary"):
                    user_name = em.get("value")
                    break
            if not user_name and emails:
                user_name = emails[0].get("value")

        if not user_name:
            raise HTTPException(
                status_code=400,
                detail=_scim_error(400, "userName or primary email required", "invalidValue"),
            )

        # Check for email conflict with another user
        conflict = db.execute(
            text("SELECT id FROM users WHERE email = :email AND id != :user_id"),
            {"email": user_name, "user_id": user_id},
        ).fetchone()
        if conflict:
            raise HTTPException(
                status_code=409,
                detail=_scim_error(409, f"Email '{user_name}' already in use", "uniqueness"),
            )

        enterprise = body.get(SCIM_ENTERPRISE_SCHEMA, {})
        role = enterprise.get("department")

        # phoneNumbers (RFC 7643 Section 4.1.2)
        phone = None
        phone_numbers = body.get("phoneNumbers", [])
        for pn in phone_numbers:
            if pn.get("primary"):
                phone = pn.get("value")
                break
        if phone is None and phone_numbers:
            phone = phone_numbers[0].get("value")

        # addresses (RFC 7643 Section 4.1.2)
        business_address = None
        addresses = body.get("addresses", [])
        for addr in addresses:
            if addr.get("primary"):
                business_address = addr.get("formatted") or addr.get("value", "")
                break
        if business_address is None and addresses:
            business_address = addresses[0].get("formatted") or addresses[0].get("value", "")

        title = body.get("title")

        # Enterprise extension fields
        employee_number = enterprise.get("employeeNumber")
        manager_id = None
        if "manager" in enterprise:
            mgr = enterprise["manager"]
            mgr_val = mgr.get("value") if isinstance(mgr, dict) else mgr
            if mgr_val is not None:
                try:
                    manager_id = int(mgr_val)
                except (ValueError, TypeError):
                    pass

        update_params = {
            "user_id": user_id,
            "email": user_name,
            "first_name": first_name,
            "last_name": last_name,
            "is_active": is_active,
            "phone": phone,
            "business_address": business_address,
            "title": title,
            "nmls_number": employee_number,
            "manager_id": manager_id,
        }

        role_clause = ""
        if role and role in VALID_IMPORT_ROLES:
            role_clause = ", permission_role = :permission_role, role = :role_legacy"
            update_params["permission_role"] = role
            update_params["role_legacy"] = role

        update_sql = (
            "UPDATE users SET"
            "    email = :email,"
            "    first_name = :first_name,"
            "    last_name = :last_name,"
            "    is_active = :is_active,"
            "    phone = :phone,"
            "    business_address = :business_address,"
            "    title = :title,"
            "    nmls_number = :nmls_number,"
            "    manager_id = :manager_id"
            "    " + role_clause +
            " WHERE id = :user_id"
        )
        db.execute(text(update_sql), update_params)
        db.commit()

        # Re-fetch and return (with enterprise extension columns)
        row = db.execute(
            text("""
                SELECT u.id, u.email, u.first_name, u.last_name, u.is_active,
                       u.permission_role, u.organization_id, u.created_at,
                       u.phone, u.business_address, u.title, u.team_name,
                       u.nmls_number, u.nmls_id, u.manager_id,
                       b.name AS branch_name,
                       COALESCE(m.first_name || ' ' || m.last_name, '') AS manager_display_name
                FROM users u
                LEFT JOIN branches b ON b.id = u.branch_id
                LEFT JOIN users m ON m.id = u.manager_id
                WHERE u.id = :user_id
            """),
            {"user_id": user_id},
        ).fetchone()

        # Audit: SCIM user replacement (PUT)
        after_state = {
            "email": user_name,
            "first_name": first_name,
            "last_name": last_name,
            "is_active": is_active,
            "role": role if role and role in VALID_IMPORT_ROLES else before_state.get("role"),
        }
        _write_audit_log(
            db=db,
            user_id=user_id,
            changed_by_id=user_id,  # SCIM-provisioned (no human actor)
            change_type="scim_replace_user",
            entity_type="scim_provisioning",
            entity_id=user_id,
            before_state=before_state,
            after_state=after_state,
            ip_address=request.client.host if request.client else None,
            reason="SCIM 2.0 user replacement (PUT, IdP-initiated)",
            scim_token_hash=token_hash,
        )
        db.commit()

        base_url = str(request.base_url).rstrip("/")
        return _user_to_scim(row, base_url)

    @app.patch("/scim/v2/Users/{user_id}", tags=["SCIM"])
    @SCIM_OP_LIMIT
    async def scim_patch_user(
        user_id: int,
        request: Request,
        db: Session = Depends(get_db),
    ):
        """
        SCIM 2.0 - Partial update user (RFC 7644 Section 3.5.2).

        Supports PatchOp with operations:
          - replace: Update specific attributes
          - add: Same as replace for single-valued attrs
          - remove: Set attribute to NULL / deactivate
        Rate limited: 100 requests/minute per SCIM token.
        """
        _token, token_hash = _validate_scim_token(request)

        try:
            body = await request.json()
        except Exception as e:
            logger.error(f"Error parsing SCIM patch user JSON body: {e}")
            raise HTTPException(
                status_code=400,
                detail=_scim_error(400, "Invalid JSON body"),
            )

        # Validate PatchOp schema
        schemas = body.get("schemas", [])
        if SCIM_PATCH_SCHEMA not in schemas:
            raise HTTPException(
                status_code=400,
                detail=_scim_error(400, f"Request must include schema {SCIM_PATCH_SCHEMA}", "invalidValue"),
            )

        operations = body.get("Operations", body.get("operations", []))
        if not operations:
            raise HTTPException(
                status_code=400,
                detail=_scim_error(400, "No operations provided", "invalidValue"),
            )

        # Fetch existing user for 404 check and audit before-state
        existing = db.execute(
            text("""
                SELECT id, email, first_name, last_name, is_active, permission_role
                FROM users WHERE id = :user_id
            """),
            {"user_id": user_id},
        ).fetchone()
        if not existing:
            raise HTTPException(
                status_code=404,
                detail=_scim_error(404, f"User {user_id} not found"),
            )

        patch_before_state = {
            "email": existing.email,
            "first_name": existing.first_name,
            "last_name": existing.last_name,
            "is_active": existing.is_active,
            "role": existing.permission_role,
        }

        # Process each operation (RFC 7644 Section 3.5.2)
        update_fields = {}

        for op in operations:
            op_type = op.get("op", "").lower()
            path = op.get("path", "")
            value = op.get("value")

            if op_type not in ("replace", "add", "remove"):
                raise HTTPException(
                    status_code=400,
                    detail=_scim_error(400, f"Unsupported operation: {op.get('op')}", "invalidValue"),
                )

            if op_type in ("replace", "add"):
                if path == "active" or (not path and isinstance(value, dict) and "active" in value):
                    active_val = value if isinstance(value, bool) else value.get("active", True)
                    update_fields["is_active"] = active_val

                elif path == "userName" or (not path and isinstance(value, dict) and "userName" in value):
                    email_val = value if isinstance(value, str) else value.get("userName")
                    if email_val and _validate_email(email_val):
                        update_fields["email"] = email_val

                elif path == "name.givenName":
                    update_fields["first_name"] = value

                elif path == "name.familyName":
                    update_fields["last_name"] = value

                elif path == "name" and isinstance(value, dict):
                    if "givenName" in value:
                        update_fields["first_name"] = value["givenName"]
                    if "familyName" in value:
                        update_fields["last_name"] = value["familyName"]

                elif path == "displayName":
                    # Split displayName into first/last as best effort
                    if isinstance(value, str):
                        parts = value.strip().split(" ", 1)
                        update_fields["first_name"] = parts[0]
                        if len(parts) > 1:
                            update_fields["last_name"] = parts[1]

                elif path == "title":
                    update_fields["title"] = value if isinstance(value, str) else str(value)

                # phoneNumbers — extract primary or first work number
                elif path == "phoneNumbers":
                    if isinstance(value, list):
                        phone_val = None
                        for pn in value:
                            if pn.get("primary"):
                                phone_val = pn.get("value")
                                break
                        if phone_val is None and value:
                            phone_val = value[0].get("value")
                        if phone_val:
                            update_fields["phone"] = phone_val
                    elif isinstance(value, dict):
                        update_fields["phone"] = value.get("value", "")

                # addresses — extract primary or first work address
                elif path == "addresses":
                    if isinstance(value, list):
                        addr_val = None
                        for addr in value:
                            if addr.get("primary"):
                                addr_val = addr.get("formatted") or addr.get("value", "")
                                break
                        if addr_val is None and value:
                            addr_val = value[0].get("formatted") or value[0].get("value", "")
                        if addr_val:
                            update_fields["business_address"] = addr_val
                    elif isinstance(value, dict):
                        update_fields["business_address"] = value.get("formatted") or value.get("value", "")

                # Enterprise extension attributes via path
                elif path == f"{SCIM_ENTERPRISE_SCHEMA}:employeeNumber":
                    update_fields["nmls_number"] = str(value) if value else None

                elif path == f"{SCIM_ENTERPRISE_SCHEMA}:department":
                    if isinstance(value, str) and value in VALID_IMPORT_ROLES:
                        update_fields["permission_role"] = value
                        update_fields["role"] = value
                    elif isinstance(value, str):
                        update_fields["team_name"] = value

                elif path == f"{SCIM_ENTERPRISE_SCHEMA}:manager":
                    if isinstance(value, dict):
                        mgr_id = value.get("value")
                    else:
                        mgr_id = value
                    if mgr_id is not None:
                        try:
                            update_fields["manager_id"] = int(mgr_id)
                        except (ValueError, TypeError):
                            pass

                # Handle enterprise extension as nested object in path
                elif path == SCIM_ENTERPRISE_SCHEMA and isinstance(value, dict):
                    _apply_enterprise_ext(value, update_fields)

                # Handle no path (bulk replace)
                elif not path and isinstance(value, dict):
                    if "name" in value and isinstance(value["name"], dict):
                        if "givenName" in value["name"]:
                            update_fields["first_name"] = value["name"]["givenName"]
                        if "familyName" in value["name"]:
                            update_fields["last_name"] = value["name"]["familyName"]
                    if "emails" in value and isinstance(value["emails"], list):
                        for em in value["emails"]:
                            if em.get("primary") and em.get("value"):
                                update_fields["email"] = em["value"]
                                break
                    if "phoneNumbers" in value and isinstance(value["phoneNumbers"], list):
                        for pn in value["phoneNumbers"]:
                            if pn.get("primary") and pn.get("value"):
                                update_fields["phone"] = pn["value"]
                                break
                    if "addresses" in value and isinstance(value["addresses"], list):
                        for addr in value["addresses"]:
                            if addr.get("primary"):
                                update_fields["business_address"] = addr.get("formatted") or addr.get("value", "")
                                break
                    if "title" in value:
                        update_fields["title"] = value["title"]
                    # Enterprise extension inside bulk value
                    if SCIM_ENTERPRISE_SCHEMA in value:
                        _apply_enterprise_ext(value[SCIM_ENTERPRISE_SCHEMA], update_fields)

            elif op_type == "remove":
                if path == "active":
                    update_fields["is_active"] = False
                elif path == "title":
                    update_fields["title"] = None
                elif path == "phoneNumbers":
                    update_fields["phone"] = None
                elif path == "addresses":
                    update_fields["business_address"] = None
                elif path == f"{SCIM_ENTERPRISE_SCHEMA}:employeeNumber":
                    update_fields["nmls_number"] = None
                elif path == f"{SCIM_ENTERPRISE_SCHEMA}:department":
                    update_fields["team_name"] = None
                elif path == f"{SCIM_ENTERPRISE_SCHEMA}:manager":
                    update_fields["manager_id"] = None

        if not update_fields:
            # No-op; return current state (with enterprise extension columns)
            row = db.execute(
                text("""
                    SELECT u.id, u.email, u.first_name, u.last_name, u.is_active,
                           u.permission_role, u.organization_id, u.created_at,
                           u.phone, u.business_address, u.title, u.team_name,
                           u.nmls_number, u.nmls_id, u.manager_id,
                           b.name AS branch_name,
                           COALESCE(m.first_name || ' ' || m.last_name, '') AS manager_display_name
                    FROM users u
                    LEFT JOIN branches b ON b.id = u.branch_id
                    LEFT JOIN users m ON m.id = u.manager_id
                    WHERE u.id = :user_id
                """),
                {"user_id": user_id},
            ).fetchone()
            base_url = str(request.base_url).rstrip("/")
            return _user_to_scim(row, base_url)

        # Check email uniqueness if changing email
        if "email" in update_fields:
            conflict = db.execute(
                text("SELECT id FROM users WHERE email = :email AND id != :user_id"),
                {"email": update_fields["email"], "user_id": user_id},
            ).fetchone()
            if conflict:
                raise HTTPException(
                    status_code=409,
                    detail=_scim_error(409, f"Email '{update_fields['email']}' already in use", "uniqueness"),
                )

        # Build dynamic UPDATE
        set_parts = []
        params = {"user_id": user_id}
        for col, val in update_fields.items():
            param_key = f"upd_{col}"
            set_parts.append(f"{col} = :{param_key}")
            params[param_key] = val

        patch_sql = "UPDATE users SET " + ', '.join(set_parts) + " WHERE id = :user_id"
        db.execute(text(patch_sql), params)
        db.commit()

        row = db.execute(
            text("""
                SELECT u.id, u.email, u.first_name, u.last_name, u.is_active,
                       u.permission_role, u.organization_id, u.created_at,
                       u.phone, u.business_address, u.title, u.team_name,
                       u.nmls_number, u.nmls_id, u.manager_id,
                       b.name AS branch_name,
                       COALESCE(m.first_name || ' ' || m.last_name, '') AS manager_display_name
                FROM users u
                LEFT JOIN branches b ON b.id = u.branch_id
                LEFT JOIN users m ON m.id = u.manager_id
                WHERE u.id = :user_id
            """),
            {"user_id": user_id},
        ).fetchone()

        # Audit: SCIM user partial update (PATCH)
        _write_audit_log(
            db=db,
            user_id=user_id,
            changed_by_id=user_id,  # SCIM-provisioned (no human actor)
            change_type="scim_patch_user",
            entity_type="scim_provisioning",
            entity_id=user_id,
            before_state=patch_before_state,
            after_state={"changed_fields": update_fields},
            ip_address=request.client.host if request.client else None,
            reason="SCIM 2.0 user partial update (PATCH, IdP-initiated)",
            scim_token_hash=token_hash,
        )
        db.commit()

        base_url = str(request.base_url).rstrip("/")
        return _user_to_scim(row, base_url)

    @app.delete("/scim/v2/Users/{user_id}", tags=["SCIM"], status_code=204)
    @SCIM_OP_LIMIT
    async def scim_delete_user(
        user_id: int,
        request: Request,
        db: Session = Depends(get_db),
    ):
        """
        SCIM 2.0 - Delete (deactivate) user (RFC 7644 Section 3.6).

        Per enterprise policy, users are soft-deleted (is_active = false)
        rather than hard-deleted, preserving audit history.
        Rate limited: 100 requests/minute per SCIM token.
        """
        _token, token_hash = _validate_scim_token(request)

        existing = db.execute(
            text("""
                SELECT id, email, first_name, last_name, is_active,
                       permission_role, organization_id
                FROM users WHERE id = :user_id
            """),
            {"user_id": user_id},
        ).fetchone()
        if not existing:
            raise HTTPException(
                status_code=404,
                detail=_scim_error(404, f"User {user_id} not found"),
            )

        db.execute(
            text("UPDATE users SET is_active = false WHERE id = :user_id"),
            {"user_id": user_id},
        )
        db.commit()

        # Audit: SCIM user deactivation (DELETE)
        _write_audit_log(
            db=db,
            user_id=user_id,
            changed_by_id=user_id,  # SCIM-provisioned (no human actor)
            change_type="scim_delete_user",
            entity_type="scim_provisioning",
            entity_id=user_id,
            before_state={
                "email": existing.email,
                "first_name": existing.first_name,
                "last_name": existing.last_name,
                "is_active": existing.is_active,
                "role": existing.permission_role,
                "organization_id": existing.organization_id,
            },
            after_state={"is_active": False},
            ip_address=request.client.host if request.client else None,
            reason="SCIM 2.0 user deactivation (DELETE, IdP-initiated)",
            scim_token_hash=token_hash,
        )
        db.commit()

        # 204 No Content per RFC 7644
        from starlette.responses import Response
        return Response(status_code=204)

    # ========================================================================
    # SCIM 2.0 GROUPS ENDPOINTS (RFC 7644 Section 3 — Groups)
    # ========================================================================
    # Maps SCIM Groups to the existing permission_role system.
    # Each unique permission_role within an org is exposed as a SCIM Group.
    # Group membership changes update the user's permission_role.

    def _role_to_scim_group(role: str, org_id: int, members: list, base_url: str = "") -> dict:
        """Convert a permission_role + member list to a SCIM 2.0 Group resource."""
        # Stable group ID: org_id:role (encoded to avoid special chars)
        group_id = f"{org_id}_{role}"
        return {
            "schemas": [SCIM_GROUP_SCHEMA],
            "id": group_id,
            "displayName": role,
            "members": [
                {
                    "value": str(m["id"]),
                    "display": m["display"],
                    "$ref": f"{base_url}/scim/v2/Users/{m['id']}",
                }
                for m in members
            ],
            "meta": {
                "resourceType": "Group",
                "location": f"{base_url}/scim/v2/Groups/{group_id}",
            },
        }

    def _parse_group_id(group_id: str) -> Optional[tuple]:
        """Parse a group ID of the form '{org_id}_{role}' into (org_id, role)."""
        parts = group_id.split("_", 1)
        if len(parts) != 2:
            return None
        try:
            org_id = int(parts[0])
            role = parts[1]
            return (org_id, role)
        except (ValueError, TypeError):
            return None

    @app.get("/scim/v2/Groups", tags=["SCIM"])
    @SCIM_LIST_LIMIT
    async def scim_list_groups(
        request: Request,
        startIndex: int = Query(1, ge=1, alias="startIndex"),
        count: int = Query(100, ge=1, le=500, alias="count"),
        filter: Optional[str] = Query(None),
        db: Session = Depends(get_db),
    ):
        """
        SCIM 2.0 - List groups (RFC 7644 Section 3.4.2).

        Groups are mapped from the permission_role system. Each unique
        permission_role within the org is a SCIM Group, with users
        holding that role as members.

        Supports filter: displayName eq "admin"
        """
        _token, token_hash = _validate_scim_token(request)
        org_id = _get_scim_org_id(db, request)
        base_url = str(request.base_url).rstrip("/")

        # Determine which roles to return
        role_filter = None
        if filter:
            parsed = _parse_scim_filter(filter)
            if parsed:
                attr, op, value = parsed
                if attr == "displayName" and op == "eq":
                    role_filter = value

        # Get distinct roles in this org
        if role_filter:
            roles_sql = (
                "SELECT DISTINCT permission_role FROM users"
                " WHERE organization_id = :org_id AND permission_role = :role"
                " AND permission_role IS NOT NULL"
                " ORDER BY permission_role"
            )
            roles_rows = db.execute(
                text(roles_sql), {"org_id": org_id, "role": role_filter}
            ).fetchall()
        else:
            roles_sql = (
                "SELECT DISTINCT permission_role FROM users"
                " WHERE organization_id = :org_id"
                " AND permission_role IS NOT NULL"
                " ORDER BY permission_role"
            )
            roles_rows = db.execute(text(roles_sql), {"org_id": org_id}).fetchall()

        all_roles = [r.permission_role for r in roles_rows if r.permission_role]
        total_count = len(all_roles)

        # Paginate
        offset = startIndex - 1
        page_roles = all_roles[offset:offset + count]

        # Fetch members for each role in the page
        resources = []
        for role in page_roles:
            members_sql = (
                "SELECT id, email, first_name, last_name FROM users"
                " WHERE organization_id = :org_id AND permission_role = :role"
                " AND is_active = true"
                " ORDER BY id"
            )
            member_rows = db.execute(
                text(members_sql), {"org_id": org_id, "role": role}
            ).fetchall()

            members = [
                {
                    "id": m.id,
                    "display": f"{m.first_name or ''} {m.last_name or ''}".strip() or m.email,
                }
                for m in member_rows
            ]
            resources.append(_role_to_scim_group(role, org_id, members, base_url))

        return {
            "schemas": [SCIM_LIST_SCHEMA],
            "totalResults": total_count,
            "startIndex": startIndex,
            "itemsPerPage": count,
            "Resources": resources,
        }

    @app.get("/scim/v2/Groups/{group_id}", tags=["SCIM"])
    @SCIM_OP_LIMIT
    async def scim_get_group(
        group_id: str,
        request: Request,
        db: Session = Depends(get_db),
    ):
        """
        SCIM 2.0 - Get group by ID (RFC 7644 Section 3.4.1).

        Group ID format: {org_id}_{permission_role}
        """
        _token, token_hash = _validate_scim_token(request)
        base_url = str(request.base_url).rstrip("/")

        parsed = _parse_group_id(group_id)
        if not parsed:
            raise HTTPException(
                status_code=404,
                detail=_scim_error(404, f"Group {group_id} not found"),
            )

        org_id, role = parsed

        # Verify the role exists in this org
        check_sql = (
            "SELECT COUNT(*) as cnt FROM users"
            " WHERE organization_id = :org_id AND permission_role = :role"
        )
        check_row = db.execute(text(check_sql), {"org_id": org_id, "role": role}).fetchone()
        if not check_row or check_row.cnt == 0:
            raise HTTPException(
                status_code=404,
                detail=_scim_error(404, f"Group {group_id} not found"),
            )

        # Fetch members
        members_sql = (
            "SELECT id, email, first_name, last_name FROM users"
            " WHERE organization_id = :org_id AND permission_role = :role"
            " AND is_active = true"
            " ORDER BY id"
        )
        member_rows = db.execute(
            text(members_sql), {"org_id": org_id, "role": role}
        ).fetchall()

        members = [
            {
                "id": m.id,
                "display": f"{m.first_name or ''} {m.last_name or ''}".strip() or m.email,
            }
            for m in member_rows
        ]

        return _role_to_scim_group(role, org_id, members, base_url)

    @app.patch("/scim/v2/Groups/{group_id}", tags=["SCIM"])
    @SCIM_OP_LIMIT
    async def scim_patch_group(
        group_id: str,
        request: Request,
        db: Session = Depends(get_db),
    ):
        """
        SCIM 2.0 - Update group membership (RFC 7644 Section 3.5.2).

        Supports PatchOp operations:
          - add members: Add users to this role/group
          - remove members: Remove users from this role/group (sets role to 'sales' default)
          - replace members: Replace all group members

        Group ID format: {org_id}_{permission_role}
        """
        _token, token_hash = _validate_scim_token(request)
        base_url = str(request.base_url).rstrip("/")

        parsed = _parse_group_id(group_id)
        if not parsed:
            raise HTTPException(
                status_code=404,
                detail=_scim_error(404, f"Group {group_id} not found"),
            )

        org_id, role = parsed

        try:
            body = await request.json()
        except Exception as e:
            logger.error(f"Error parsing SCIM patch group JSON body: {e}")
            raise HTTPException(
                status_code=400,
                detail=_scim_error(400, "Invalid JSON body"),
            )

        schemas = body.get("schemas", [])
        if SCIM_PATCH_SCHEMA not in schemas:
            raise HTTPException(
                status_code=400,
                detail=_scim_error(400, f"Request must include schema {SCIM_PATCH_SCHEMA}", "invalidValue"),
            )

        operations = body.get("Operations", body.get("operations", []))
        if not operations:
            raise HTTPException(
                status_code=400,
                detail=_scim_error(400, "No operations provided", "invalidValue"),
            )

        for op in operations:
            op_type = op.get("op", "").lower()
            path = op.get("path", "")
            value = op.get("value")

            if op_type == "add" and path == "members":
                # Add users to this role
                member_list = value if isinstance(value, list) else [value]
                for member in member_list:
                    user_id = member.get("value") if isinstance(member, dict) else member
                    if user_id:
                        try:
                            db.execute(
                                text(
                                    "UPDATE users SET permission_role = :role, role = :role"
                                    " WHERE id = :user_id AND organization_id = :org_id"
                                ),
                                {"role": role, "user_id": int(user_id), "org_id": org_id},
                            )
                        except (ValueError, TypeError):
                            logger.warning(f"SCIM Groups PATCH: invalid user_id {user_id}")

            elif op_type == "remove" and path and path.startswith("members"):
                # Remove users from this role (reset to 'sales' default)
                # Path format: members[value eq "123"]
                member_match = re.search(r'value\s+eq\s+"(\d+)"', path)
                if member_match:
                    user_id = int(member_match.group(1))
                    db.execute(
                        text(
                            "UPDATE users SET permission_role = 'sales', role = 'sales'"
                            " WHERE id = :user_id AND organization_id = :org_id"
                            " AND permission_role = :role"
                        ),
                        {"user_id": user_id, "org_id": org_id, "role": role},
                    )
                elif isinstance(value, list):
                    # Alternate format: value is a list of member objects
                    for member in value:
                        user_id = member.get("value") if isinstance(member, dict) else member
                        if user_id:
                            try:
                                db.execute(
                                    text(
                                        "UPDATE users SET permission_role = 'sales', role = 'sales'"
                                        " WHERE id = :user_id AND organization_id = :org_id"
                                        " AND permission_role = :role"
                                    ),
                                    {"user_id": int(user_id), "org_id": org_id, "role": role},
                                )
                            except (ValueError, TypeError):
                                logger.warning(f"SCIM Groups PATCH remove: invalid user_id {user_id}")

            elif op_type == "replace" and (path == "members" or not path):
                # Replace all members: remove all current, add new
                # First, reset current members of this role to 'sales'
                db.execute(
                    text(
                        "UPDATE users SET permission_role = 'sales', role = 'sales'"
                        " WHERE organization_id = :org_id AND permission_role = :role"
                    ),
                    {"org_id": org_id, "role": role},
                )
                # Then set new members
                member_list = value if isinstance(value, list) else ([value] if value else [])
                for member in member_list:
                    user_id = member.get("value") if isinstance(member, dict) else member
                    if user_id:
                        try:
                            db.execute(
                                text(
                                    "UPDATE users SET permission_role = :role, role = :role"
                                    " WHERE id = :user_id AND organization_id = :org_id"
                                ),
                                {"role": role, "user_id": int(user_id), "org_id": org_id},
                            )
                        except (ValueError, TypeError):
                            logger.warning(f"SCIM Groups PATCH replace: invalid user_id {user_id}")

        db.commit()

        # Audit
        _write_audit_log(
            db=db,
            user_id=0,
            changed_by_id=0,
            change_type="scim_patch_group",
            entity_type="scim_provisioning",
            after_state={
                "group_id": group_id,
                "role": role,
                "org_id": org_id,
                "operations_count": len(operations),
            },
            ip_address=request.client.host if request.client else None,
            reason="SCIM 2.0 group membership update (PATCH, IdP-initiated)",
            scim_token_hash=token_hash,
        )
        db.commit()

        # Return updated group
        members_sql = (
            "SELECT id, email, first_name, last_name FROM users"
            " WHERE organization_id = :org_id AND permission_role = :role"
            " AND is_active = true"
            " ORDER BY id"
        )
        member_rows = db.execute(
            text(members_sql), {"org_id": org_id, "role": role}
        ).fetchall()

        members = [
            {
                "id": m.id,
                "display": f"{m.first_name or ''} {m.last_name or ''}".strip() or m.email,
            }
            for m in member_rows
        ]

        return _role_to_scim_group(role, org_id, members, base_url)

    # ========================================================================
    # CSV BULK USER IMPORT (Check 5.12)
    # ========================================================================

    @app.post("/api/v1/admin/users/import-csv", tags=["Admin"])
    @SCIM_BULK_LIMIT
    async def import_users_csv(
        request: Request,
        file: UploadFile = File(...),
        preview: bool = Query(False, description="Dry-run mode: validate without creating users"),
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """
        Bulk import users from a CSV file.

        CSV columns: email, name, role, branch (branch is optional).
        Uses the current user's organization_id for all imported users.

        Query params:
            preview=true  - Dry-run: validates rows and returns errors without creating users.
            preview=false - (default) Creates users and returns summary.

        Requires admin or site_admin permission.
        """
        from utils.auth import require_admin
        require_admin(current_user)

        # Read CSV content
        try:
            raw_bytes = await file.read()
            content = raw_bytes.decode("utf-8-sig")  # Handle BOM
        except UnicodeDecodeError:
            raise HTTPException(status_code=400, detail="CSV file must be UTF-8 encoded")

        reader = csv.DictReader(io.StringIO(content))

        # Validate header
        if not reader.fieldnames:
            raise HTTPException(status_code=400, detail="CSV file is empty or missing headers")

        normalized_fields = [f.strip().lower() for f in reader.fieldnames]
        if "email" not in normalized_fields:
            raise HTTPException(
                status_code=400,
                detail=f"CSV must contain 'email' column. Found columns: {', '.join(reader.fieldnames)}",
            )

        org_id = getattr(current_user, "organization_id", None)

        # Look up existing branch names for the org
        branch_map: dict = {}
        if org_id:
            branches = db.execute(
                text("SELECT id, name FROM branches WHERE organization_id = :org_id"),
                {"org_id": org_id},
            ).fetchall()
            branch_map = {b.name.lower(): b.id for b in branches}

        # Collect existing emails for duplicate detection
        existing_emails_rows = db.execute(text("SELECT email FROM users")).fetchall()
        existing_emails = {r.email.lower() for r in existing_emails_rows}

        results = []
        valid_rows = []
        row_num = 0

        for raw_row in reader:
            row_num += 1
            # Normalize keys
            row = {k.strip().lower(): (v.strip() if v else "") for k, v in raw_row.items()}

            email = row.get("email", "")
            name = row.get("name", "")
            role = row.get("role", "loan_officer").lower().replace(" ", "_")
            branch_name = row.get("branch", "")

            errors = []

            # Validate email
            if not email:
                errors.append("email is required")
            elif not _validate_email(email):
                errors.append(f"invalid email format: {email}")
            elif email.lower() in existing_emails:
                errors.append(f"email already exists: {email}")

            # Validate name
            if not name:
                errors.append("name is required")

            # Validate role
            if role and role not in VALID_IMPORT_ROLES:
                errors.append(
                    f"invalid role '{role}'. Valid: {', '.join(sorted(VALID_IMPORT_ROLES))}"
                )

            # Resolve branch
            branch_id = None
            if branch_name:
                branch_id = branch_map.get(branch_name.lower())
                if branch_id is None:
                    errors.append(f"branch not found: {branch_name}")

            row_result = {
                "row": row_num,
                "email": email,
                "name": name,
                "role": role,
                "branch": branch_name or None,
                "errors": errors,
                "status": "error" if errors else "valid",
            }
            results.append(row_result)

            if not errors:
                # Split name
                name_parts = name.strip().split(" ", 1)
                first = name_parts[0]
                last = name_parts[1] if len(name_parts) > 1 else ""

                valid_rows.append({
                    "email": email,
                    "first_name": first,
                    "last_name": last,
                    "role": role,
                    "branch_id": branch_id,
                })
                # Track for intra-file duplicate detection
                existing_emails.add(email.lower())

        summary = {
            "total_rows": row_num,
            "valid": len(valid_rows),
            "errors": row_num - len(valid_rows),
            "preview_mode": preview,
        }

        if preview or not valid_rows:
            return {
                "summary": summary,
                "rows": results,
            }

        # Actually create users
        created_ids = []
        for vr in valid_rows:
            random_pw = secrets.token_urlsafe(16)
            hashed = _hash_password(random_pw)

            insert_result = db.execute(
                text("""
                    INSERT INTO users (
                        email, hashed_password, first_name, last_name,
                        permission_role, role, organization_id, branch_id,
                        is_active, created_at
                    ) VALUES (
                        :email, :hashed_password, :first_name, :last_name,
                        :permission_role, :role, :org_id, :branch_id,
                        true, NOW()
                    )
                    RETURNING id
                """),
                {
                    "email": vr["email"],
                    "hashed_password": hashed,
                    "first_name": vr["first_name"],
                    "last_name": vr["last_name"],
                    "permission_role": vr["role"],
                    "role": vr["role"],
                    "org_id": org_id,
                    "branch_id": vr["branch_id"],
                },
            )
            new_id = insert_result.fetchone()
            created_ids.append(new_id[0] if new_id else None)

        db.commit()

        # Auto-provision SchedulerConfig for each newly created user so they
        # can use the calendar immediately (called after commit so user IDs exist).
        if org_id and created_ids:
            try:
                from services.scheduler_provisioning import auto_provision_scheduler_config
                valid_idx = 0
                for uid in created_ids:
                    if uid is not None and valid_idx < len(valid_rows):
                        await auto_provision_scheduler_config(
                            user_id=uid,
                            organization_id=org_id,
                            db=db,
                            user_email=valid_rows[valid_idx]["email"],
                        )
                    valid_idx += 1
            except Exception as _sched_exc:
                logger.warning(
                    "import_users_csv: scheduler auto-provision failed — %s", _sched_exc,
                )

        # Update results with created IDs
        created_idx = 0
        for r in results:
            if r["status"] == "valid":
                r["status"] = "created"
                r["user_id"] = created_ids[created_idx] if created_idx < len(created_ids) else None
                created_idx += 1

        summary["created"] = len(created_ids)

        # Audit: CSV bulk user import
        imported_emails = [vr["email"] for vr in valid_rows]
        _write_audit_log(
            db=db,
            user_id=current_user.id,
            changed_by_id=current_user.id,
            change_type="bulk_users_imported",
            entity_type="csv_import",
            entity_id=None,
            after_state={
                "total_rows": row_num,
                "created_count": len(created_ids),
                "error_count": row_num - len(valid_rows),
                "created_user_ids": created_ids,
                "created_emails": imported_emails,
                "organization_id": org_id,
                "filename": file.filename,
            },
            ip_address=request.client.host if request.client else None,
            reason=f"CSV bulk import: {len(created_ids)} users created from '{file.filename}'",
        )
        db.commit()

        return {
            "summary": summary,
            "rows": results,
        }

    # ========================================================================
    # MFA ONBOARDING ENDPOINTS (Check 5.15)
    # ========================================================================

    @app.post("/api/v1/onboarding/mfa/setup", tags=["MFA Onboarding"])
    async def mfa_onboarding_setup(
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """
        Generate TOTP secret and QR code for MFA enrollment during onboarding.

        Returns the provisioning URI, base64 QR code image, and backup codes.
        The secret is persisted to the user record but MFA is not activated
        until the user verifies a token via the /mfa/verify endpoint.
        """
        from auth.mfa import generate_mfa_secret, generate_backup_codes

        # If MFA is already enabled, return status
        if getattr(current_user, "mfa_enabled", False):
            return {
                "already_enabled": True,
                "message": "MFA is already enabled for this account",
            }

        # Generate secret and provisioning URI
        mfa_data = generate_mfa_secret(current_user.email)

        # Generate backup codes
        plain_codes, hashed_codes = generate_backup_codes()

        # Persist secret and backup codes (not yet activated)
        db.execute(
            text("""
                UPDATE users
                SET mfa_secret = :secret,
                    mfa_backup_codes = CAST(:backup_codes AS json)
                WHERE id = :user_id
            """),
            {
                "secret": mfa_data["secret"],
                "backup_codes": json.dumps(hashed_codes),
                "user_id": current_user.id,
            },
        )
        db.commit()

        return {
            "secret": mfa_data["secret"],
            "provisioning_uri": mfa_data["provisioning_uri"],
            "qr_code_base64": mfa_data.get("qr_code_base64"),
            "backup_codes": plain_codes,
            "message": "Scan the QR code with your authenticator app, then verify with a code",
        }

    @app.post("/api/v1/onboarding/mfa/verify", tags=["MFA Onboarding"])
    async def mfa_onboarding_verify(
        body: MfaVerifyRequest,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """
        Verify a TOTP code to complete MFA enrollment during onboarding.

        The user must have already called /mfa/setup to generate a secret.
        Upon successful verification, mfa_enabled is set to True.
        """
        from auth.mfa import verify_mfa_token

        # Get the pending secret
        user_row = db.execute(
            text("SELECT mfa_secret, mfa_enabled FROM users WHERE id = :user_id"),
            {"user_id": current_user.id},
        ).fetchone()

        if not user_row or not user_row.mfa_secret:
            raise HTTPException(
                status_code=400,
                detail="MFA setup not initiated. Call /api/v1/onboarding/mfa/setup first.",
            )

        if user_row.mfa_enabled:
            return {"verified": True, "message": "MFA is already enabled"}

        # Verify the TOTP token
        is_valid = verify_mfa_token(user_row.mfa_secret, body.token)
        if not is_valid:
            raise HTTPException(
                status_code=400,
                detail="Invalid TOTP code. Please try again with a current code from your authenticator app.",
            )

        # Activate MFA
        db.execute(
            text("""
                UPDATE users
                SET mfa_enabled = true,
                    mfa_enabled_at = NOW()
                WHERE id = :user_id
            """),
            {"user_id": current_user.id},
        )
        db.commit()

        return {
            "verified": True,
            "mfa_enabled": True,
            "message": "MFA successfully enabled. Your account is now protected with two-factor authentication.",
        }

    @app.get("/api/v1/onboarding/mfa/status", tags=["MFA Onboarding"])
    async def mfa_onboarding_status(
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """
        Check MFA requirement and completion status for the current user.

        Returns whether MFA is required by the organization, whether the
        user has completed enrollment, and when it was enabled.
        """
        # Check if org requires MFA
        org_requires_mfa = False
        org_id = getattr(current_user, "organization_id", None)

        if org_id:
            org_row = db.execute(
                text("SELECT mfa_required FROM organizations WHERE id = :org_id"),
                {"org_id": org_id},
            ).fetchone()
            if org_row:
                org_requires_mfa = bool(org_row.mfa_required)

        # Get user MFA status
        user_row = db.execute(
            text("""
                SELECT mfa_enabled, mfa_enabled_at, mfa_secret IS NOT NULL as setup_started
                FROM users WHERE id = :user_id
            """),
            {"user_id": current_user.id},
        ).fetchone()

        mfa_enabled = bool(user_row.mfa_enabled) if user_row else False
        setup_started = bool(user_row.setup_started) if user_row else False
        enabled_at = user_row.mfa_enabled_at.isoformat() if user_row and user_row.mfa_enabled_at else None

        return {
            "mfa_required": org_requires_mfa,
            "mfa_enabled": mfa_enabled,
            "setup_started": setup_started,
            "enabled_at": enabled_at,
            "action_needed": org_requires_mfa and not mfa_enabled,
            "message": (
                "MFA enrollment is complete."
                if mfa_enabled
                else (
                    "MFA is required by your organization. Please complete enrollment."
                    if org_requires_mfa
                    else "MFA is optional but recommended."
                )
            ),
        }

    logger.info(
        "SCIM 2.0 provisioning, CSV bulk import, and MFA onboarding routes registered "
        "(enterprise readiness checks 5.11, 5.12, 5.15)"
    )
