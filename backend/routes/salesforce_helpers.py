"""
Salesforce Integration - Helper Utilities

SQL building, validation, token refresh, auth helpers, and shared
utility functions used across all Salesforce route modules.
"""
import os
import logging
import asyncio
from typing import Optional, Dict, Any
from datetime import datetime

import requests
from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from fastapi import HTTPException, Request

from .salesforce_models import ALLOWED_LOAN_COLUMNS

logger = logging.getLogger(__name__)

# Import Salesforce API version constant for consistency
try:
    from integrations.salesforce_service import SALESFORCE_API_VERSION
except ImportError:
    SALESFORCE_API_VERSION = "v58.0"  # Fallback

# Import encryption functions for secure token storage
try:
    from services.calendly_service import encrypt_token, decrypt_token
except ImportError:
    # SECURITY: Fail hard if encryption not available - never store tokens in plaintext
    logger.error("CRITICAL: Token encryption not available - refusing to handle tokens insecurely")
    def encrypt_token(token: str) -> str:
        raise RuntimeError("Token encryption not available - cannot store tokens securely")
    def decrypt_token(token: str) -> str:
        raise RuntimeError("Token decryption not available - cannot retrieve tokens securely")


# =============================================================================
# Async HTTP helper
# =============================================================================

async def _async_get(*args, **kwargs):
    """Run blocking requests.get() in thread pool to avoid blocking the event loop."""
    return await asyncio.to_thread(requests.get, *args, **kwargs)


# =============================================================================
# Database session dependency
# =============================================================================

def get_db():
    """Get database session with RLS tenant context."""
    from database import get_db as _get_db_rls
    yield from _get_db_rls()


# =============================================================================
# URL validation
# =============================================================================

def _safe_redirect_url(url: Optional[str], frontend_url: str) -> str:
    """Validate redirect URL to prevent open redirect attacks."""
    if not url:
        return f"{frontend_url}/settings/integrations"
    from urllib.parse import urlparse
    parsed = urlparse(url)
    # Allow relative paths
    if not parsed.scheme and not parsed.netloc:
        if url.startswith("/") and not url.startswith("//"):
            return f"{frontend_url}{url}"
        return f"{frontend_url}/settings/integrations"
    # Allow only the frontend URL origin
    frontend_parsed = urlparse(frontend_url)
    if parsed.scheme in ("http", "https") and parsed.netloc == frontend_parsed.netloc:
        return url
    return f"{frontend_url}/settings/integrations"


# =============================================================================
# Instance URL parsing
# =============================================================================

def parse_instance_url_from_scopes(scopes: str) -> Optional[str]:
    """
    Safely parse instance_url from scopes string.

    The scopes field sometimes contains 'instance_url:https://...' format
    from legacy OAuth flows. This function safely extracts it.

    Args:
        scopes: The scopes string that may contain instance_url

    Returns:
        The instance URL if found, None otherwise
    """
    if not scopes:
        return None

    try:
        if "instance_url:" not in scopes:
            return None

        # Extract the URL after 'instance_url:'
        after_prefix = scopes.split("instance_url:")[1]

        # The URL ends at comma or end of string
        instance_url = after_prefix.split(",")[0].strip()

        # Validate it looks like a URL
        if instance_url.startswith("https://") and ".salesforce.com" in instance_url:
            return instance_url

        logger.warning(f"Invalid instance URL format in scopes: {instance_url[:50]}")
        return None

    except (IndexError, AttributeError) as e:
        logger.warning(f"Failed to parse instance_url from scopes: {e}")
        return None


# =============================================================================
# Deprecation headers
# =============================================================================

def add_deprecation_headers(response, endpoint_name: str) -> None:
    """
    Add deprecation headers to response per RFC 8594.
    https://datatracker.ietf.org/doc/html/rfc8594
    """
    from .salesforce_models import DEPRECATION_DATE, SUNSET_LINK
    response.headers["Deprecation"] = f"@{DEPRECATION_DATE}"
    response.headers["Sunset"] = DEPRECATION_DATE
    response.headers["Link"] = f'<{SUNSET_LINK}>; rel="successor-version"'
    logger.warning(
        f"Deprecated endpoint accessed: {endpoint_name}. "
        f"Please migrate to {SUNSET_LINK} before {DEPRECATION_DATE}"
    )


# =============================================================================
# SQL building helpers (injection-safe)
# =============================================================================

def sanitize_loan_data(loan_data: dict) -> dict:
    """
    Filter loan data to only include allowed column names.
    This prevents SQL injection via malicious field names from Salesforce.
    """
    return {k: v for k, v in loan_data.items() if k in ALLOWED_LOAN_COLUMNS}


def build_safe_update_sql(loan_data: dict, table: str = "loans") -> tuple:
    """
    Build a safe UPDATE SQL statement using only whitelisted column names.
    Returns (sql_string, filtered_data_dict)
    """
    safe_data = sanitize_loan_data(loan_data)
    if not safe_data:
        raise ValueError("No valid columns to update")

    # Build update fields, excluding the key field
    update_fields = ", ".join([f"{k} = :{k}" for k in safe_data.keys() if k != 'salesforce_id'])
    sql = f"UPDATE {table} SET {update_fields}, updated_at = CURRENT_TIMESTAMP WHERE salesforce_id = :salesforce_id"
    return sql, safe_data


def build_safe_insert_sql(loan_data: dict, table: str = "loans") -> tuple:
    """
    Build a safe INSERT SQL statement using only whitelisted column names.
    Returns (sql_string, filtered_data_dict)
    """
    safe_data = sanitize_loan_data(loan_data)
    if not safe_data:
        raise ValueError("No valid columns to insert")

    columns = ", ".join(safe_data.keys())
    placeholders = ", ".join([f":{k}" for k in safe_data.keys()])
    sql = f"INSERT INTO {table} ({columns}, created_at, updated_at) VALUES ({placeholders}, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
    return sql, safe_data


def build_safe_upsert_sql(loan_data: dict, conflict_column: str = "salesforce_id", table: str = "loans") -> tuple:
    """
    Build a safe UPSERT (INSERT ... ON CONFLICT DO UPDATE) SQL statement.
    This prevents race conditions by using atomic upsert.
    Returns (sql_string, filtered_data_dict, is_insert_only)

    Note: Requires a unique constraint on conflict_column.
    """
    safe_data = sanitize_loan_data(loan_data)
    if not safe_data:
        raise ValueError("No valid columns to upsert")

    if conflict_column not in safe_data:
        raise ValueError(f"Conflict column '{conflict_column}' must be in data")

    columns = ", ".join(safe_data.keys())
    placeholders = ", ".join([f":{k}" for k in safe_data.keys()])

    # Build update clause excluding the conflict column
    update_cols = [k for k in safe_data.keys() if k != conflict_column]
    if not update_cols:
        # No columns to update, just try insert (might fail on conflict)
        sql = f"INSERT INTO {table} ({columns}, created_at, updated_at) VALUES ({placeholders}, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP) ON CONFLICT ({conflict_column}) DO NOTHING"
        return sql, safe_data, True

    update_clause = ", ".join([f"{k} = EXCLUDED.{k}" for k in update_cols])

    sql = f"""
        INSERT INTO {table} ({columns}, created_at, updated_at)
        VALUES ({placeholders}, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT ({conflict_column}) DO UPDATE SET
            {update_clause},
            updated_at = CURRENT_TIMESTAMP
    """
    return sql, safe_data, False


# =============================================================================
# Token refresh with retry
# =============================================================================

def refresh_and_retry_on_401(
    db: Session,
    user_id: int,
    api_call_func,
    access_token: str,
    refresh_token: Optional[str],
    *args,
    **kwargs
):
    """
    Execute an API call with automatic token refresh on 401 errors.

    Args:
        db: Database session for updating tokens
        user_id: User ID for token storage
        api_call_func: Function that makes the API call (should return response)
        access_token: Current access token
        refresh_token: Refresh token for obtaining new access token
        *args, **kwargs: Additional arguments passed to api_call_func

    Returns:
        Tuple of (result, new_access_token) where new_access_token is set if token was refreshed
    """
    import requests as req_lib

    try:
        # First attempt with current token
        result = api_call_func(access_token, *args, **kwargs)
        return result, None  # No token refresh needed

    except req_lib.exceptions.HTTPError as e:
        if e.response is not None and e.response.status_code == 401 and refresh_token:
            logger.info(f"Got 401, attempting token refresh for user {user_id}")

            # Try to refresh the token
            from integrations.salesforce_service import salesforce_client
            new_tokens = salesforce_client.refresh_access_token(decrypt_token(refresh_token))

            if new_tokens and new_tokens.get("access_token"):
                new_access_token = new_tokens["access_token"]

                # Update token in database
                try:
                    encrypted_access = encrypt_token(new_access_token)
                    db.execute(text("""
                        UPDATE user_integrations
                        SET access_token = :access_token, updated_at = CURRENT_TIMESTAMP
                        WHERE user_id = :user_id AND provider = 'salesforce'
                    """), {
                        "access_token": encrypted_access,
                        "user_id": user_id
                    })
                    db.commit()
                    logger.info(f"Successfully refreshed and stored new token for user {user_id}")
                except Exception as db_error:
                    logger.error(f"Failed to update refreshed token in database: {db_error}")
                    db.rollback()

                # Retry with new token
                result = api_call_func(new_access_token, *args, **kwargs)
                return result, new_access_token

            logger.warning(f"Token refresh failed for user {user_id}")

        # Re-raise if not a 401 or refresh failed
        raise


# =============================================================================
# Auth helpers
# =============================================================================

def get_current_user_id(request: Request, db: Session = None) -> Optional[int]:
    """Extract user ID from JWT token in request.

    Tries RS256 (canonical secure token) first, falls back to HS256 for
    backward compatibility with older clients.
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None

    token = auth_header[7:]

    # Try RS256 canonical auth first (preferred)
    try:
        from auth.tokens import _verify_secure_token
        payload = _verify_secure_token(token)
        if payload:
            user_id = payload.get("user_id")
            if user_id:
                return user_id
            email = payload.get("sub")
            if email and db:
                result = db.execute(text("SELECT id FROM users WHERE email = :email"), {"email": email}).fetchone()
                if result:
                    return result[0]
    except Exception:
        pass  # Fall through to HS256

    # Fallback: HS256 legacy tokens
    try:
        import jwt
        secret_key = os.getenv("SECRET_KEY", "")
        payload = jwt.decode(
            token,
            secret_key,
            algorithms=["HS256"],
            options={"verify_aud": False, "verify_iss": False}
        )
        email = payload.get("sub")
        if email and db:
            result = db.execute(text("SELECT id FROM users WHERE email = :email"), {"email": email}).fetchone()
            if result:
                return result[0]
        return payload.get("user_id")
    except Exception as e:
        logger.warning(f"Failed to extract user ID from token: {e}")
    return None


def require_admin_role(user_id: int, db: Session) -> None:
    """
    Check if user has admin privileges.
    Raises HTTPException 403 if not admin.

    Admin check looks for:
    - role = 'admin'
    - permission_role in ('admin', 'management')
    - is_admin = true
    """
    result = db.execute(text("""
        SELECT role, permission_role, is_admin
        FROM users WHERE id = :user_id
    """), {"user_id": user_id}).fetchone()

    if not result:
        raise HTTPException(status_code=403, detail="User not found")

    role, permission_role, is_admin = result

    # Check various admin indicators
    admin_roles = ['admin', 'management', 'site_administrator', 'company_admin']
    if is_admin:
        return  # User has is_admin flag
    if role and role.lower() in admin_roles:
        return  # Legacy admin role
    if permission_role and permission_role.lower() in admin_roles:
        return  # Phase 2 permission role

    raise HTTPException(
        status_code=403,
        detail="Admin access required. Schema exploration endpoints are restricted to admin users."
    )
