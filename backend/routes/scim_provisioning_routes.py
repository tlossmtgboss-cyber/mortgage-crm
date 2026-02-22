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
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import Depends, HTTPException, Request, UploadFile, File, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


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
):
    """
    Write a hash-chained audit log entry for SCIM/CSV provisioning operations.

    Uses the enterprise audit service (services/audit_service.py) which provides
    SHA-256 hash-chained append-only audit entries with tamper detection.
    """
    try:
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
    """Convert a DB user row to SCIM 2.0 User resource (RFC 7643 Section 4.1)."""
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

    # Enterprise extension: role / department
    enterprise_ext = {}
    if hasattr(row, "permission_role") and row.permission_role:
        enterprise_ext["department"] = row.permission_role
    if hasattr(row, "organization_id") and row.organization_id:
        enterprise_ext["organization"] = str(row.organization_id)
    if enterprise_ext:
        resource["schemas"].append(SCIM_ENTERPRISE_SCHEMA)
        resource[SCIM_ENTERPRISE_SCHEMA] = enterprise_ext

    return resource


def _validate_scim_token(request: Request) -> str:
    """
    Validate the SCIM Bearer token from the Authorization header.
    Returns the token string if valid, raises HTTPException otherwise.

    The SCIM token is a separate credential from user JWT tokens, stored
    in the SCIM_API_TOKEN environment variable. Identity providers (Okta,
    Azure AD, etc.) send this token with each SCIM request.
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
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
        raise HTTPException(
            status_code=401,
            detail=_scim_error(401, "Invalid SCIM bearer token"),
        )

    return token


def _get_scim_org_id(db: Session) -> Optional[int]:
    """
    Determine the organization_id to scope SCIM operations.

    Currently uses the first active organization. In a multi-IdP deployment
    you would derive this from the bearer token or a tenant header.
    """
    row = db.execute(text(
        "SELECT id FROM organizations WHERE is_active = true ORDER BY id LIMIT 1"
    )).fetchone()
    return row.id if row else None


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
        """
        _validate_scim_token(request)

        org_id = _get_scim_org_id(db)
        params: dict = {"limit": count, "offset": startIndex - 1}
        where_clauses = []

        if org_id is not None:
            where_clauses.append("organization_id = :org_id")
            params["org_id"] = org_id

        # Parse SCIM filter (simplified: supports userName eq "..." and active eq true/false)
        if filter:
            filter_stripped = filter.strip()

            # userName eq "value"
            username_match = re.match(
                r'userName\s+eq\s+"([^"]+)"', filter_stripped, re.IGNORECASE
            )
            if username_match:
                where_clauses.append("email = :filter_email")
                params["filter_email"] = username_match.group(1)

            # active eq true/false
            active_match = re.match(
                r'active\s+eq\s+(true|false)', filter_stripped, re.IGNORECASE
            )
            if active_match:
                is_active = active_match.group(1).lower() == "true"
                where_clauses.append("is_active = :filter_active")
                params["filter_active"] = is_active

        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

        # Sorting
        order_column = "id"
        if sortBy == "userName":
            order_column = "email"
        elif sortBy in ("name.familyName",):
            order_column = "last_name"
        elif sortBy in ("name.givenName",):
            order_column = "first_name"
        elif sortBy == "displayName":
            order_column = "first_name"

        order_dir = "DESC" if sortOrder and sortOrder.lower() == "descending" else "ASC"

        # Count total
        total_row = db.execute(
            text(f"SELECT COUNT(*) as cnt FROM users WHERE {where_sql}"), params
        ).fetchone()
        total_count = total_row.cnt if total_row else 0

        # Fetch page
        rows = db.execute(
            text(f"""
                SELECT id, email, first_name, last_name, is_active,
                       permission_role, organization_id, created_at
                FROM users
                WHERE {where_sql}
                ORDER BY {order_column} {order_dir}
                LIMIT :limit OFFSET :offset
            """),
            params,
        ).fetchall()

        base_url = str(request.base_url).rstrip("/")
        resources = [_user_to_scim(r, base_url) for r in rows]

        return {
            "schemas": [SCIM_LIST_SCHEMA],
            "totalResults": total_count,
            "startIndex": startIndex,
            "itemsPerPage": count,
            "Resources": resources,
        }

    @app.post("/scim/v2/Users", tags=["SCIM"], status_code=201)
    async def scim_create_user(
        request: Request,
        db: Session = Depends(get_db),
    ):
        """
        SCIM 2.0 - Create user (RFC 7644 Section 3.3).

        Expects SCIM User JSON with userName, name, active, emails.
        Creates a deactivated-password user (IdP-managed).
        """
        _validate_scim_token(request)

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

        org_id = _get_scim_org_id(db)

        # Enterprise extension: role
        enterprise = body.get(SCIM_ENTERPRISE_SCHEMA, {})
        role = enterprise.get("department", "sales")
        if role not in VALID_IMPORT_ROLES:
            role = "sales"

        # Create with random password (IdP-managed, password login not used)
        random_pw = secrets.token_urlsafe(32)
        hashed = _hash_password(random_pw)

        result = db.execute(
            text("""
                INSERT INTO users (
                    email, hashed_password, first_name, last_name,
                    permission_role, role, organization_id, is_active,
                    sso_provider, sso_subject_id, created_at
                ) VALUES (
                    :email, :hashed_password, :first_name, :last_name,
                    :permission_role, :role, :org_id, :is_active,
                    'scim', :external_id, NOW()
                )
                RETURNING id, email, first_name, last_name, is_active,
                          permission_role, organization_id, created_at
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
            },
        )

        new_user = result.fetchone()
        db.commit()

        # Audit: SCIM user creation
        _write_audit_log(
            db=db,
            user_id=new_user.id,
            changed_by_id=new_user.id,  # SCIM-provisioned (no human actor)
            change_type="user_created",
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
        )
        db.commit()

        base_url = str(request.base_url).rstrip("/")
        scim_resource = _user_to_scim(new_user, base_url)
        scim_resource["externalId"] = body.get("externalId", "")

        return scim_resource

    @app.get("/scim/v2/Users/{user_id}", tags=["SCIM"])
    async def scim_get_user(
        user_id: int,
        request: Request,
        db: Session = Depends(get_db),
    ):
        """SCIM 2.0 - Get user by ID (RFC 7644 Section 3.4.1)."""
        _validate_scim_token(request)

        row = db.execute(
            text("""
                SELECT id, email, first_name, last_name, is_active,
                       permission_role, organization_id, created_at
                FROM users WHERE id = :user_id
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
    async def scim_replace_user(
        user_id: int,
        request: Request,
        db: Session = Depends(get_db),
    ):
        """SCIM 2.0 - Replace user (RFC 7644 Section 3.5.1)."""
        _validate_scim_token(request)

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

        update_params = {
            "user_id": user_id,
            "email": user_name,
            "first_name": first_name,
            "last_name": last_name,
            "is_active": is_active,
        }

        role_clause = ""
        if role and role in VALID_IMPORT_ROLES:
            role_clause = ", permission_role = :permission_role, role = :role_legacy"
            update_params["permission_role"] = role
            update_params["role_legacy"] = role

        db.execute(
            text(f"""
                UPDATE users SET
                    email = :email,
                    first_name = :first_name,
                    last_name = :last_name,
                    is_active = :is_active
                    {role_clause}
                WHERE id = :user_id
            """),
            update_params,
        )
        db.commit()

        # Re-fetch and return
        row = db.execute(
            text("""
                SELECT id, email, first_name, last_name, is_active,
                       permission_role, organization_id, created_at
                FROM users WHERE id = :user_id
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
            change_type="user_updated",
            entity_type="scim_provisioning",
            entity_id=user_id,
            before_state=before_state,
            after_state=after_state,
            ip_address=request.client.host if request.client else None,
            reason="SCIM 2.0 user replacement (PUT, IdP-initiated)",
        )
        db.commit()

        base_url = str(request.base_url).rstrip("/")
        return _user_to_scim(row, base_url)

    @app.patch("/scim/v2/Users/{user_id}", tags=["SCIM"])
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
        """
        _validate_scim_token(request)

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

        # Process each operation
        update_fields = {}

        for op in operations:
            op_type = op.get("op", "").lower()
            path = op.get("path", "")
            value = op.get("value")

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

            elif op_type == "remove":
                if path == "active":
                    update_fields["is_active"] = False

        if not update_fields:
            # No-op; return current state
            row = db.execute(
                text("""
                    SELECT id, email, first_name, last_name, is_active,
                           permission_role, organization_id, created_at
                    FROM users WHERE id = :user_id
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

        db.execute(
            text(f"UPDATE users SET {', '.join(set_parts)} WHERE id = :user_id"),
            params,
        )
        db.commit()

        row = db.execute(
            text("""
                SELECT id, email, first_name, last_name, is_active,
                       permission_role, organization_id, created_at
                FROM users WHERE id = :user_id
            """),
            {"user_id": user_id},
        ).fetchone()

        # Audit: SCIM user partial update (PATCH)
        _write_audit_log(
            db=db,
            user_id=user_id,
            changed_by_id=user_id,  # SCIM-provisioned (no human actor)
            change_type="user_updated",
            entity_type="scim_provisioning",
            entity_id=user_id,
            before_state=patch_before_state,
            after_state={"changed_fields": update_fields},
            ip_address=request.client.host if request.client else None,
            reason="SCIM 2.0 user partial update (PATCH, IdP-initiated)",
        )
        db.commit()

        base_url = str(request.base_url).rstrip("/")
        return _user_to_scim(row, base_url)

    @app.delete("/scim/v2/Users/{user_id}", tags=["SCIM"], status_code=204)
    async def scim_delete_user(
        user_id: int,
        request: Request,
        db: Session = Depends(get_db),
    ):
        """
        SCIM 2.0 - Delete (deactivate) user (RFC 7644 Section 3.6).

        Per enterprise policy, users are soft-deleted (is_active = false)
        rather than hard-deleted, preserving audit history.
        """
        _validate_scim_token(request)

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
            change_type="user_deactivated",
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
        )
        db.commit()

        # 204 No Content per RFC 7644
        from starlette.responses import Response
        return Response(status_code=204)

    # ========================================================================
    # CSV BULK USER IMPORT (Check 5.12)
    # ========================================================================

    @app.post("/api/v1/admin/users/import-csv", tags=["Admin"])
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
