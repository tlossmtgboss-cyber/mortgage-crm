"""
Salesforce Integration Routes (Legacy)
OAuth authentication, webhook handling, and sync endpoints

DEPRECATION NOTICE:
This module is being phased out in favor of salesforce_integration_routes.py which provides:
- Per-user OAuth with PKCE
- Schema discovery and field mapping
- Email and calendar sync
- Bidirectional sync support

New endpoints are available at /api/integrations/salesforce/*
These legacy endpoints at /api/v1/salesforce/* will be maintained for backwards compatibility.
"""
import os
import logging
from datetime import datetime
from typing import Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Query, Body, Response, BackgroundTasks
from fastapi.responses import RedirectResponse
from sqlalchemy import text
from sqlalchemy.orm import Session
from pydantic import BaseModel
import warnings

logger = logging.getLogger(__name__)


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

# Import Salesforce API version constant for consistency
try:
    from integrations.salesforce_service import SALESFORCE_API_VERSION
except ImportError:
    SALESFORCE_API_VERSION = "v58.0"  # Fallback

from sqlalchemy.exc import SQLAlchemyError
import asyncio
import requests
from requests.exceptions import RequestException


async def _async_get(*args, **kwargs):
    """Run blocking requests.get() in thread pool to avoid blocking the event loop."""
    return await asyncio.to_thread(requests.get, *args, **kwargs)

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

router = APIRouter()


# =============================================================================
# UTILITY: Instance URL Parsing (replaces fragile string splitting)
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


# Deprecation configuration
DEPRECATION_DATE = "2025-06-01"  # Date when these endpoints will be removed
SUNSET_LINK = "/api/integrations/salesforce"  # New endpoint location


def add_deprecation_headers(response: Response, endpoint_name: str) -> None:
    """
    Add deprecation headers to response per RFC 8594.
    https://datatracker.ietf.org/doc/html/rfc8594
    """
    response.headers["Deprecation"] = f"@{DEPRECATION_DATE}"
    response.headers["Sunset"] = DEPRECATION_DATE
    response.headers["Link"] = f'<{SUNSET_LINK}>; rel="successor-version"'
    logger.warning(
        f"Deprecated endpoint accessed: {endpoint_name}. "
        f"Please migrate to {SUNSET_LINK} before {DEPRECATION_DATE}"
    )


# Whitelist of allowed column names for loans table to prevent SQL injection
ALLOWED_LOAN_COLUMNS = frozenset([
    'id', 'loan_number', 'borrower_name', 'borrower_email', 'borrower_phone',
    'preferred_communication', 'coborrower_name', 'co_borrower_email', 'stage',
    'program', 'loan_type', 'amount', 'loan_amount', 'purchase_price', 'down_payment',
    'rate', 'term', 'property_address', 'property_city', 'property_state', 'property_zip',
    'lock_date', 'closing_date', 'funded_date', 'loan_officer_id', 'processor',
    'underwriter', 'realtor_agent', 'title_company', 'days_in_stage', 'sla_status',
    'milestones', 'ai_insights', 'predicted_close_date', 'risk_score', 'user_metadata',
    'appraisal_ordered_date', 'appraisal_scheduled_date', 'appraisal_completed_date',
    'appraisal_value', 'lock_expiration_date', 'rate_lock_status', 'rate_lock_recommendation',
    'lock_term_days', 'salesforce_id', 'salesforce_last_synced_at', 'salesforce_sync_status',
    'prospect_date', 'application_date', 'le_pending_date', 'credit_only_date',
    'file_received_date', 'preapproval_date', 'uw_received_date', 'conditions_for_review_date',
    'suspended_date', 'loan_approved_date', 'approved_not_accepted_date', 'approval_expires_date',
    'appraisal_docs_expire_date', 'clear_to_close_date', 'cd_requested_date',
    'cd_sent_to_borrower_date', 'cd_acknowledged_date', 'docs_ordered_date', 'docs_out_date',
    'signing_date', 'wire_ordered_date', 'funding_date', 'funding_verified_date',
    'contract_received_date', 'earnest_money_verified_date', 'lender', 'origination_channel',
    'referral_source', 'created_at', 'updated_at', 'notes', 'ltv', 'cltv', 'dti',
])


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


# Request/Response Models
class SalesforceConnectionStatus(BaseModel):
    connected: bool
    instance_url: Optional[str] = None
    user_email: Optional[str] = None
    connected_at: Optional[str] = None
    last_sync_at: Optional[str] = None


class SalesforceWebhookPayload(BaseModel):
    records: Optional[list] = None
    event_type: Optional[str] = None
    # Allow arbitrary fields for single-record format
    class Config:
        extra = "allow"


class SyncResponse(BaseModel):
    status: str
    records_processed: int
    records_created: int
    records_updated: int
    records_failed: int
    errors: list = []
    message: str


class FieldMappingRequest(BaseModel):
    salesforce_field: str
    crm_field: str
    transform_type: Optional[str] = None


# Dependency to get database session
def get_db():
    """Get database session - imported from main app."""
    from main import SessionLocal
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user_id(request: Request, db: Session = None) -> Optional[int]:
    """Extract user ID from JWT token in request."""
    try:
        import jwt
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            secret_key = os.getenv("SECRET_KEY", "")
            payload = jwt.decode(
                token,
                secret_key,
                algorithms=["HS256"],
                options={"verify_aud": False, "verify_iss": False}
            )
            email = payload.get("sub")
            if email and db:
                # Look up user by email
                result = db.execute(text("SELECT id FROM users WHERE email = :email"), {"email": email}).fetchone()
                if result:
                    return result[0]
            # Fallback: try to get user_id from payload
            return payload.get("user_id")
    except SQLAlchemyError as e:
        logger.warning(f"Failed to extract user ID: {e}")
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


# ============ OAuth Endpoints ============

@router.get("/connect")
async def salesforce_connect(
    request: Request,
    redirect_url: Optional[str] = Query(None, description="URL to redirect after auth"),
    db: Session = Depends(get_db)
):
    """
    Initiate Salesforce OAuth flow.
    Redirects user to Salesforce login page.

    DEPRECATED: Use /api/integrations/salesforce/connect instead for:
    - PKCE-secured OAuth flow
    - Better token management
    - Calendar sync settings initialization
    """
    logger.warning("DEPRECATED: /api/v1/salesforce/connect - Use /api/integrations/salesforce/connect instead")
    from integrations.salesforce_service import salesforce_client

    if not salesforce_client.enabled:
        raise HTTPException(
            status_code=503,
            detail="Salesforce integration not configured. Set SALESFORCE_CLIENT_ID and SALESFORCE_CLIENT_SECRET."
        )

    user_id = get_current_user_id(request, db)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    # Create state parameter with user_id and optional redirect URL
    state = f"{user_id}"
    if redirect_url:
        state = f"{user_id}:{redirect_url}"

    auth_url = salesforce_client.get_authorization_url(state=state)

    return RedirectResponse(url=auth_url)


@router.get("/callback")
async def salesforce_callback(
    code: str = Query(..., description="Authorization code from Salesforce"),
    state: Optional[str] = Query(None, description="State parameter with user_id"),
    error: Optional[str] = Query(None, description="Error from Salesforce"),
    error_description: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """
    Handle OAuth callback from Salesforce.
    Exchanges authorization code for access token.
    Supports two state formats:
    1. Secure hex token stored in oauth_states table (from integration_settings_routes)
    2. Legacy format: user_id:redirect_url
    """
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")

    if error:
        logger.error(f"Salesforce OAuth error: {error} - {error_description}")
        return RedirectResponse(
            url=f"{frontend_url}/settings/integrations?error=salesforce_auth_failed&message={error_description or error}"
        )

    # First, try to handle state as a secure token from oauth_states table
    if state:
        try:
            from services.salesforce.oauth_service import salesforce_oauth

            # Ensure oauth_states table exists with correct schema
            try:
                db.execute(text("""
                    CREATE TABLE IF NOT EXISTS oauth_states (
                        id SERIAL PRIMARY KEY,
                        state_token VARCHAR(255) UNIQUE NOT NULL,
                        user_id INTEGER NOT NULL,
                        provider VARCHAR(50) NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        expires_at TIMESTAMP NOT NULL,
                        used BOOLEAN DEFAULT FALSE,
                        return_url TEXT,
                        state_metadata JSONB
                    )
                """))
                db.commit()
            except Exception as table_err:
                logger.debug(f"oauth_states table check: {table_err}")
                try:
                    db.rollback()
                except Exception:
                    pass

            # Check if this state exists in oauth_states table
            logger.info(f"Looking up OAuth state in database: {state[:20]}...")
            oauth_state = db.execute(text("""
                SELECT id, user_id, return_url, state_metadata, expires_at, used
                FROM oauth_states
                WHERE state_token = :state AND provider = 'salesforce'
            """), {"state": state}).fetchone()

            if oauth_state:
                logger.info(f"Found OAuth state in database for state token")

                # Check if state has expired
                if oauth_state[4] and oauth_state[4] < datetime.utcnow():
                    logger.error(f"OAuth state has expired")
                    return RedirectResponse(
                        url=f"{frontend_url}/settings/integrations?error=state_expired&message=OAuth+session+expired.+Please+try+again."
                    )

                # Check if state was already used
                if oauth_state[5]:
                    logger.error(f"OAuth state has already been used")
                    return RedirectResponse(
                        url=f"{frontend_url}/settings/integrations?error=state_used&message=OAuth+state+already+used.+Please+try+again."
                    )

                # Use the oauth service to handle the callback
                try:
                    result = await salesforce_oauth.handle_callback(db, code, state)
                    return_url = _safe_redirect_url(result.get('return_url'), frontend_url)
                    logger.info(f"Salesforce OAuth successful for user {result['user_id']}")
                    return RedirectResponse(url=f"{return_url}?salesforce=connected")
                except ValueError as e:
                    logger.error(f"OAuth callback error: {e}")
                    from urllib.parse import urlencode
                    safe_msg = str(e)[:100].replace("\r", "").replace("\n", "")
                    return RedirectResponse(
                        url=f"{frontend_url}/settings/integrations?error=salesforce_auth_failed&{urlencode({'message': safe_msg})}"
                    )
            else:
                # State not found in oauth_states - check if it's a long hex token that should have been there
                if len(state) > 20 and all(c in '0123456789abcdefABCDEF' for c in state[:20]):
                    logger.error(f"Secure OAuth state not found in database - may have expired or been cleaned up")
                    return RedirectResponse(
                        url=f"{frontend_url}/settings/integrations?error=state_not_found&message=OAuth+session+not+found.+Please+try+again."
                    )
        except Exception as e:
            logger.error(f"OAuth state lookup failed with exception: {type(e).__name__}: {e}")
            # Check if state looks like a secure hex token - if so, it should be in the database
            # This prevents falling through to legacy format for secure states
            if state and len(state) >= 32:
                # Check if it's a hex string (secure state token format)
                try:
                    int(state[:32], 16)  # Will succeed for hex strings
                    # It's a hex token but wasn't found - return clear error
                    logger.error(f"Secure OAuth state token not found in database. State: {state[:20]}..., Error: {e}")

                    # Try to get more info about what's in the database
                    try:
                        count_result = db.execute(text("SELECT COUNT(*) FROM oauth_states WHERE provider = 'salesforce'")).fetchone()
                        logger.info(f"oauth_states table has {count_result[0]} salesforce entries")
                    except Exception as count_err:
                        logger.error(f"Could not query oauth_states table: {count_err}")

                    return RedirectResponse(
                        url=f"{frontend_url}/settings/integrations?error=state_not_found&message=OAuth+session+not+found.+Please+try+connecting+again."
                    )
                except ValueError:
                    logger.info(f"State is not a hex token, trying legacy format")
                    pass  # Not a hex string, continue to legacy format

    # Fall back to legacy format: user_id:redirect_url
    from integrations.salesforce_service import salesforce_client

    # Parse state
    user_id = None
    redirect_url = None
    if state:
        parts = state.split(":", 1)
        try:
            user_id = int(parts[0])
        except ValueError:
            pass
        if len(parts) > 1:
            redirect_url = parts[1]

    if not user_id:
        # Check one more time if this looks like a secure state that we couldn't handle
        if state and len(state) >= 32:
            try:
                int(state[:32], 16)
                logger.error(f"Cannot parse secure state token - database lookup failed")
                return RedirectResponse(
                    url=f"{frontend_url}/settings/integrations?error=state_lookup_failed&message=Could+not+look+up+OAuth+state.+Please+ensure+database+migrations+are+run."
                )
            except ValueError:
                pass
        logger.error(f"Invalid state parameter: {state[:50] if state else 'None'}...")
        # Return redirect with error instead of JSON HTTPException for OAuth callback flow
        return RedirectResponse(
            url=f"{frontend_url}/settings/integrations?error=invalid_state&message=Invalid+OAuth+state+parameter.+Please+try+connecting+again."
        )

    # Retrieve PKCE code_verifier using state
    code_verifier = salesforce_client.get_code_verifier(state) if state else None

    # Exchange code for tokens (with PKCE code_verifier)
    token_data = salesforce_client.exchange_code_for_token(code, code_verifier=code_verifier)

    if not token_data:
        frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
        return RedirectResponse(
            url=f"{frontend_url}/settings/integrations?error=salesforce_token_exchange_failed"
        )

    # Get user info from Salesforce
    user_info = None
    if token_data.get("id"):
        user_info = salesforce_client.get_user_info(
            token_data["access_token"],
            token_data["id"]
        )

    # Store tokens in user_integrations table
    try:
        # Ensure table exists (create if not exists - safe operation)
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS user_integrations (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                provider VARCHAR(50) NOT NULL,
                access_token TEXT,
                refresh_token TEXT,
                expires_at TIMESTAMP,
                scopes TEXT,
                email VARCHAR(255),
                provider_user_id VARCHAR(255),
                instance_url TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, provider)
            )
        """))
        db.commit()

        # Encrypt tokens before storage
        encrypted_access = encrypt_token(token_data.get("access_token", ""))
        encrypted_refresh = encrypt_token(token_data.get("refresh_token", "")) if token_data.get("refresh_token") else None

        # Use atomic UPSERT to avoid race conditions
        # PostgreSQL: INSERT ... ON CONFLICT DO UPDATE
        db.execute(text("""
            INSERT INTO user_integrations
            (user_id, provider, access_token, refresh_token, scopes, instance_url, email, provider_user_id, created_at, updated_at)
            VALUES (:user_id, 'salesforce', :access_token, :refresh_token, :scopes, :instance_url, :email, :provider_user_id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT (user_id, provider) DO UPDATE SET
                access_token = EXCLUDED.access_token,
                refresh_token = EXCLUDED.refresh_token,
                expires_at = NULL,
                scopes = EXCLUDED.scopes,
                instance_url = EXCLUDED.instance_url,
                email = EXCLUDED.email,
                provider_user_id = EXCLUDED.provider_user_id,
                updated_at = CURRENT_TIMESTAMP
        """), {
            "user_id": int(user_id),
            "access_token": encrypted_access,
            "refresh_token": encrypted_refresh,
            "scopes": token_data.get("scope", ""),
            "instance_url": token_data.get("instance_url", ""),
            "email": user_info.get("email") if user_info else None,
            "provider_user_id": user_info.get("user_id") if user_info else None,
        })

        db.commit()
        logger.info(f"Stored Salesforce tokens for user {user_id}")

    except SQLAlchemyError as e:
        logger.error(f"Failed to store Salesforce tokens: {e}")
        db.rollback()
        frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
        return RedirectResponse(
            url=f"{frontend_url}/settings/integrations?error=salesforce_storage_failed"
        )

    # Redirect to frontend (validate URL to prevent open redirect)
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
    final_redirect = _safe_redirect_url(redirect_url, frontend_url)

    return RedirectResponse(url=f"{final_redirect}?salesforce=connected")


@router.get("/status", response_model=SalesforceConnectionStatus)
async def salesforce_status(
    request: Request,
    db: Session = Depends(get_db)
):
    """Check Salesforce connection status for current user."""
    user_id = get_current_user_id(request, db)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    integration = db.execute(text("""
        SELECT access_token, scopes, email, created_at, updated_at, instance_url
        FROM user_integrations
        WHERE user_id = :user_id AND provider = 'salesforce'
    """), {"user_id": user_id}).fetchone()

    if not integration or not integration[0]:
        return SalesforceConnectionStatus(connected=False)

    # Get instance_url from dedicated column, fall back to parsing from scopes for legacy data
    instance_url = integration[5] if len(integration) > 5 and integration[5] else None
    if not instance_url and integration[1] and "instance_url:" in str(integration[1]):
        instance_url = parse_instance_url_from_scopes(str(integration[1]))

    # Get last sync time (table may not exist yet)
    last_sync_time = None
    try:
        last_sync = db.execute(text("""
            SELECT MAX(completed_at) FROM salesforce_sync_logs
            WHERE user_id = :user_id AND status = 'success'
        """), {"user_id": user_id}).fetchone()
        if last_sync and last_sync[0]:
            last_sync_time = last_sync[0].isoformat()
    except Exception:
        # Table doesn't exist yet - that's ok
        pass

    return SalesforceConnectionStatus(
        connected=True,
        instance_url=instance_url,
        user_email=integration[2],
        connected_at=integration[3].isoformat() if integration[3] else None,
        last_sync_at=last_sync_time,
    )


@router.delete("/disconnect")
async def salesforce_disconnect(
    request: Request,
    db: Session = Depends(get_db)
):
    """Disconnect Salesforce integration."""
    user_id = get_current_user_id(request, db)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    # Get current token to revoke
    integration = db.execute(text("""
        SELECT access_token, refresh_token FROM user_integrations
        WHERE user_id = :user_id AND provider = 'salesforce'
    """), {"user_id": user_id}).fetchone()

    if integration:
        from integrations.salesforce_service import salesforce_client

        # Try to revoke token
        if integration[0]:
            salesforce_client.revoke_token(decrypt_token(integration[0]))

        # Delete from database
        db.execute(text("""
            DELETE FROM user_integrations
            WHERE user_id = :user_id AND provider = 'salesforce'
        """), {"user_id": user_id})
        db.commit()

    return {"status": "disconnected", "message": "Salesforce integration disconnected"}


# ============ Webhook Endpoint ============

@router.post("/webhook", response_model=SyncResponse)
async def salesforce_webhook(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Receive webhook notifications from Salesforce.

    This endpoint should be called by Salesforce when records are created/updated.
    Configure in Salesforce via:
    - Outbound Message (Workflow/Process Builder)
    - Platform Events + Apex HTTP callout
    - Apex Trigger with @future callout
    """
    from services.salesforce_sync_service import get_salesforce_sync_service

    # Get raw body for signature verification
    body = await request.body()

    # Verify webhook signature if configured
    signature = request.headers.get("X-Salesforce-Signature", "")
    sync_service = get_salesforce_sync_service(db)

    if not sync_service.verify_webhook_signature(body, signature):
        logger.warning("Invalid webhook signature")
        raise HTTPException(status_code=401, detail="Invalid signature")

    # Parse payload
    try:
        import json
        payload = json.loads(body)
    except Exception as e:
        logger.error(f"Invalid JSON payload: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    # Handle Salesforce Outbound Message (SOAP XML format)
    content_type = request.headers.get("Content-Type", "")
    if "xml" in content_type.lower():
        # Parse XML payload (Outbound Messages)
        payload = parse_outbound_message(body)

    # Process webhook
    result = sync_service.process_webhook(payload)

    return SyncResponse(
        status=result.status.value,
        records_processed=result.records_processed,
        records_created=result.records_created,
        records_updated=result.records_updated,
        records_failed=result.records_failed,
        errors=result.errors,
        message=f"Processed {result.records_processed} records: {result.records_created} created, {result.records_updated} updated"
    )


def parse_outbound_message(xml_body: bytes) -> Dict[str, Any]:
    """Parse Salesforce Outbound Message XML format."""
    try:
        import xml.etree.ElementTree as ET

        root = ET.fromstring(xml_body)

        # Salesforce Outbound Message structure
        # <soapenv:Envelope><soapenv:Body><notifications>
        #   <Notification><sObject>...</sObject></Notification>
        # </notifications></soapenv:Body></soapenv:Envelope>

        namespaces = {
            "soapenv": "http://schemas.xmlsoap.org/soap/envelope/",
            "sf": "urn:sobject.enterprise.soap.sforce.com",
        }

        records = []

        # Find all sObject elements
        for sobject in root.findall(".//sf:sObject", namespaces):
            record = {}
            for child in sobject:
                # Remove namespace prefix from tag
                tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                record[tag] = child.text
            if record:
                records.append(record)

        return {"records": records, "event_type": "outbound_message"}

    except Exception as e:
        logger.error(f"Failed to parse Outbound Message XML: {e}")
        return {"records": [], "event_type": "outbound_message"}


# ============ Sync Endpoints ============

@router.post("/sync/full", response_model=SyncResponse, deprecated=True)
async def salesforce_full_sync(
    request: Request,
    response: Response,
    db: Session = Depends(get_db)
):
    """
    Perform a full sync from Salesforce.
    Fetches all MtgPlanner_CRM__Transaction_Property__c records.

    DEPRECATED: Use /api/integrations/salesforce/sync instead.
    """
    add_deprecation_headers(response, "POST /sync/full")

    user_id = get_current_user_id(request, db)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    # Get stored tokens
    integration = db.execute(text("""
        SELECT access_token, refresh_token, scopes FROM user_integrations
        WHERE user_id = :user_id AND provider = 'salesforce'
    """), {"user_id": user_id}).fetchone()

    if not integration or not integration[0]:
        raise HTTPException(
            status_code=400,
            detail="Salesforce not connected. Please connect first."
        )

    access_token = decrypt_token(integration[0])
    refresh_token = decrypt_token(integration[1]) if integration[1] else None

    # Parse instance_url from scopes
    instance_url = None
    if integration[2] and "instance_url:" in integration[2]:
        instance_url = parse_instance_url_from_scopes(integration[2])

    if not instance_url:
        raise HTTPException(
            status_code=400,
            detail="Salesforce instance URL not found. Please reconnect."
        )

    from services.salesforce_sync_service import get_salesforce_sync_service

    sync_service = get_salesforce_sync_service(db, user_id=user_id)
    result = sync_service.full_sync(access_token, instance_url)

    return SyncResponse(
        status=result.status.value,
        records_processed=result.records_processed,
        records_created=result.records_created,
        records_updated=result.records_updated,
        records_failed=result.records_failed,
        errors=result.errors,
        message=f"Full sync complete: {result.records_created} created, {result.records_updated} updated"
    )


@router.get("/sync/history")
async def salesforce_sync_history(
    request: Request,
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """Get recent sync history."""
    user_id = get_current_user_id(request, db)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    history = db.execute(text("""
        SELECT id, sync_type, direction, status, records_processed,
               records_created, records_updated, records_failed,
               error_message, started_at, completed_at
        FROM salesforce_sync_logs
        WHERE user_id = :user_id
        ORDER BY started_at DESC
        LIMIT :limit
    """), {"user_id": user_id, "limit": limit}).fetchall()

    return {
        "history": [
            {
                "id": row[0],
                "sync_type": row[1],
                "direction": row[2],
                "status": row[3],
                "records_processed": row[4],
                "records_created": row[5],
                "records_updated": row[6],
                "records_failed": row[7],
                "error_message": row[8],
                "started_at": row[9].isoformat() if row[9] else None,
                "completed_at": row[10].isoformat() if row[10] else None,
            }
            for row in history
        ]
    }


# ============ Field Mapping Endpoints ============

@router.get("/mappings")
async def get_field_mappings(
    request: Request,
    db: Session = Depends(get_db)
):
    """Get current field mappings for Salesforce sync."""
    user_id = get_current_user_id(request, db)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    # Get organization_id from user
    user = db.execute(text("""
        SELECT organization_id FROM users WHERE id = :user_id
    """), {"user_id": user_id}).fetchone()

    org_id = user[0] if user and user[0] else 1

    mappings = db.execute(text("""
        SELECT id, salesforce_field, crm_field, transform_type, is_active
        FROM salesforce_field_mappings
        WHERE organization_id = :org_id
          AND salesforce_object = 'MtgPlanner_CRM__Transaction_Property__c'
        ORDER BY salesforce_field
    """), {"org_id": org_id}).fetchall()

    # If no custom mappings, return defaults
    if not mappings:
        from services.salesforce_sync_service import DEFAULT_FIELD_MAPPING
        return {
            "mappings": [
                {
                    "salesforce_field": sf_field,
                    "crm_field": crm_field,
                    "transform_type": transform,
                    "is_custom": False,
                }
                for sf_field, (crm_field, transform) in DEFAULT_FIELD_MAPPING.items()
            ],
            "using_defaults": True,
        }

    return {
        "mappings": [
            {
                "id": row[0],
                "salesforce_field": row[1],
                "crm_field": row[2],
                "transform_type": row[3],
                "is_active": row[4],
                "is_custom": True,
            }
            for row in mappings
        ],
        "using_defaults": False,
    }


@router.post("/mappings")
async def create_field_mapping(
    request: Request,
    mapping: FieldMappingRequest,
    db: Session = Depends(get_db)
):
    """Create or update a field mapping."""
    user_id = get_current_user_id(request, db)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    # Get organization_id from user
    user = db.execute(text("""
        SELECT organization_id FROM users WHERE id = :user_id
    """), {"user_id": user_id}).fetchone()

    org_id = user[0] if user and user[0] else 1

    try:
        db.execute(text("""
            INSERT INTO salesforce_field_mappings
            (organization_id, salesforce_object, salesforce_field, crm_entity, crm_field, transform_type)
            VALUES (:org_id, 'MtgPlanner_CRM__Transaction_Property__c', :sf_field, 'loan', :crm_field, :transform)
            ON CONFLICT (organization_id, salesforce_object, salesforce_field)
            DO UPDATE SET crm_field = :crm_field, transform_type = :transform, updated_at = CURRENT_TIMESTAMP
        """), {
            "org_id": org_id,
            "sf_field": mapping.salesforce_field,
            "crm_field": mapping.crm_field,
            "transform": mapping.transform_type,
        })
        db.commit()

        return {"status": "success", "message": "Field mapping saved"}

    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Failed to save field mapping: {e}")
        raise HTTPException(status_code=500, detail="Failed to save mapping")


# ============ Test/Debug Endpoints ============

@router.get("/test-connection")
async def test_salesforce_connection(
    request: Request,
    db: Session = Depends(get_db)
):
    """Test Salesforce connection by querying a simple object."""
    user_id = get_current_user_id(request, db)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    integration = db.execute(text("""
        SELECT access_token, scopes FROM user_integrations
        WHERE user_id = :user_id AND provider = 'salesforce'
    """), {"user_id": user_id}).fetchone()

    if not integration or not integration[0]:
        return {"connected": False, "error": "Not connected to Salesforce"}

    access_token = decrypt_token(integration[0])
    instance_url = None
    if integration[1] and "instance_url:" in integration[1]:
        instance_url = parse_instance_url_from_scopes(integration[1])

    if not instance_url:
        return {"connected": False, "error": "Instance URL not found"}

    from integrations.salesforce_service import salesforce_client

    # Try a simple query
    result = salesforce_client.query(
        access_token,
        instance_url,
        "SELECT COUNT() FROM MtgPlanner_CRM__Transaction_Property__c"
    )

    if result:
        return {
            "connected": True,
            "instance_url": instance_url,
            "record_count": result.get("totalSize", 0),
            "message": "Connection successful"
        }
    else:
        return {
            "connected": False,
            "error": "Query failed - token may be expired"
        }


# ============ Schema Exploration Endpoints ============

@router.get("/explore/objects")
async def explore_salesforce_objects(
    request: Request,
    db: Session = Depends(get_db)
):
    """List all available Salesforce objects. Admin access required."""
    user_id = get_current_user_id(request, db)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    # Require admin access for schema exploration
    require_admin_role(user_id, db)

    integration = db.execute(text("""
        SELECT access_token, scopes FROM user_integrations
        WHERE user_id = :user_id AND provider = 'salesforce'
    """), {"user_id": user_id}).fetchone()

    if not integration or not integration[0]:
        raise HTTPException(status_code=400, detail="Not connected to Salesforce")

    access_token = decrypt_token(integration[0])
    instance_url = None
    if integration[1] and "instance_url:" in integration[1]:
        instance_url = parse_instance_url_from_scopes(integration[1])

    if not instance_url:
        raise HTTPException(status_code=400, detail="Instance URL not found")

    import requests

    try:
        # Get global describe (list of all objects)
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }

        response = await _async_get(
            f"{instance_url}/services/data/{SALESFORCE_API_VERSION}/sobjects/",
            headers=headers,
            timeout=30
        )
        response.raise_for_status()

        data = response.json()

        # Filter to relevant objects (custom objects and standard loan-related)
        relevant_objects = []
        loan_keywords = ['loan', 'mortgage', 'opportunity', 'account', 'contact', 'lead', 'transaction', 'property', 'mtg']

        for obj in data.get('sobjects', []):
            obj_name = obj.get('name', '').lower()
            # Include custom objects and loan-related standard objects
            if obj.get('custom') or any(kw in obj_name for kw in loan_keywords):
                relevant_objects.append({
                    "name": obj.get('name'),
                    "label": obj.get('label'),
                    "custom": obj.get('custom'),
                    "queryable": obj.get('queryable'),
                    "createable": obj.get('createable'),
                    "updateable": obj.get('updateable'),
                })

        return {
            "instance_url": instance_url,
            "total_objects": len(data.get('sobjects', [])),
            "relevant_objects": sorted(relevant_objects, key=lambda x: x['name']),
            "relevant_count": len(relevant_objects)
        }

    except requests.exceptions.HTTPError as e:
        logger.error(f"Salesforce API error: {e}")
        raise HTTPException(status_code=502, detail="Salesforce API error")
    except Exception as e:
        logger.error(f"Failed to explore Salesforce objects: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/explore/objects/{object_name}")
async def explore_salesforce_object_fields(
    object_name: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """Get fields for a specific Salesforce object. Admin access required."""
    user_id = get_current_user_id(request, db)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    # Require admin access for schema exploration
    require_admin_role(user_id, db)

    integration = db.execute(text("""
        SELECT access_token, scopes FROM user_integrations
        WHERE user_id = :user_id AND provider = 'salesforce'
    """), {"user_id": user_id}).fetchone()

    if not integration or not integration[0]:
        raise HTTPException(status_code=400, detail="Not connected to Salesforce")

    access_token = decrypt_token(integration[0])
    instance_url = None
    if integration[1] and "instance_url:" in integration[1]:
        instance_url = parse_instance_url_from_scopes(integration[1])

    if not instance_url:
        raise HTTPException(status_code=400, detail="Instance URL not found")

    import requests

    try:
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }

        # Get object describe (field details)
        response = await _async_get(
            f"{instance_url}/services/data/{SALESFORCE_API_VERSION}/sobjects/{object_name}/describe/",
            headers=headers
        )
        response.raise_for_status()

        data = response.json()

        fields = []
        for field in data.get('fields', []):
            fields.append({
                "name": field.get('name'),
                "label": field.get('label'),
                "type": field.get('type'),
                "length": field.get('length'),
                "custom": field.get('custom'),
                "nillable": field.get('nillable'),
                "picklistValues": [pv.get('value') for pv in field.get('picklistValues', [])] if field.get('type') == 'picklist' else None,
            })

        return {
            "object_name": object_name,
            "label": data.get('label'),
            "custom": data.get('custom'),
            "field_count": len(fields),
            "fields": sorted(fields, key=lambda x: x['name'])
        }

    except requests.exceptions.HTTPError as e:
        logger.error(f"Salesforce API error: {e}")
        raise HTTPException(status_code=502, detail="Salesforce API error")
    except Exception as e:
        logger.error(f"Failed to describe object: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/explore/query")
async def explore_salesforce_query(
    request: Request,
    object_name: str = Query(..., description="Salesforce object name"),
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """Query sample records from a Salesforce object. Admin access required."""
    user_id = get_current_user_id(request, db)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    # Require admin access for schema exploration
    require_admin_role(user_id, db)

    integration = db.execute(text("""
        SELECT access_token, scopes FROM user_integrations
        WHERE user_id = :user_id AND provider = 'salesforce'
    """), {"user_id": user_id}).fetchone()

    if not integration or not integration[0]:
        raise HTTPException(status_code=400, detail="Not connected to Salesforce")

    access_token = decrypt_token(integration[0])
    instance_url = None
    if integration[1] and "instance_url:" in integration[1]:
        instance_url = parse_instance_url_from_scopes(integration[1])

    if not instance_url:
        raise HTTPException(status_code=400, detail="Instance URL not found")

    from integrations.salesforce_service import salesforce_client

    # First get all queryable fields
    import requests
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    try:
        # Get object describe to find queryable fields
        describe_response = await _async_get(
            f"{instance_url}/services/data/{SALESFORCE_API_VERSION}/sobjects/{object_name}/describe/",
            headers=headers
        )
        describe_response.raise_for_status()
        describe_data = describe_response.json()

        # Get important fields (excluding large blob fields)
        queryable_fields = []
        for field in describe_data.get('fields', []):
            if field.get('type') not in ['base64', 'address', 'location']:
                queryable_fields.append(field.get('name'))

        # Limit fields to avoid query size issues
        fields_to_query = queryable_fields[:30]  # First 30 fields

        # Build and execute query
        field_list = ", ".join(fields_to_query)
        soql = f"SELECT {field_list} FROM {object_name} LIMIT {limit}"

        result = salesforce_client.query(access_token, instance_url, soql)

        if result:
            return {
                "object_name": object_name,
                "query": soql,
                "total_size": result.get("totalSize", 0),
                "records": result.get("records", []),
                "fields_queried": fields_to_query
            }
        else:
            raise HTTPException(status_code=502, detail="Query failed")

    except requests.exceptions.HTTPError as e:
        logger.error(f"Salesforce API error: {e}")
        raise HTTPException(status_code=502, detail="Salesforce API error")
    except Exception as e:
        logger.error(f"Query failed: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ============ Import Loans Endpoint ============

@router.post("/import/closed-loans", deprecated=True)
async def import_closed_loans(
    request: Request,
    response: Response,
    db: Session = Depends(get_db)
):
    """
    Import closed loans/opportunities from Salesforce.

    DEPRECATED: Use /api/integrations/salesforce/import instead.
    """
    add_deprecation_headers(response, "POST /import/closed-loans")

    user_id = get_current_user_id(request, db)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    integration = db.execute(text("""
        SELECT access_token, scopes FROM user_integrations
        WHERE user_id = :user_id AND provider = 'salesforce'
    """), {"user_id": user_id}).fetchone()

    if not integration or not integration[0]:
        raise HTTPException(status_code=400, detail="Not connected to Salesforce")

    access_token = decrypt_token(integration[0])
    instance_url = None
    if integration[1] and "instance_url:" in integration[1]:
        instance_url = parse_instance_url_from_scopes(integration[1])

    if not instance_url:
        raise HTTPException(status_code=400, detail="Instance URL not found")

    import requests

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    results = {
        "imported": 0,
        "updated": 0,
        "skipped": 0,
        "errors": [],
        "loans": []
    }

    try:
        # First, discover what objects are available
        sobjects_response = await _async_get(f"{instance_url}/services/data/{SALESFORCE_API_VERSION}/sobjects/", headers=headers)
        sobjects_response.raise_for_status()
        available_objects = {obj['name']: obj for obj in sobjects_response.json().get('sobjects', [])}

        # Try different possible loan objects in order of preference
        loan_objects_to_try = [
            ("MtgPlanner_CRM__Transaction_Property__c", "MtgPlanner_CRM__Status__c", ["Closed", "Funded"]),
            ("Opportunity", "StageName", ["Closed Won", "Closed", "Funded"]),
            ("Loan__c", "Status__c", ["Closed", "Funded", "Closed Won"]),
        ]

        found_object = None
        status_field = None
        closed_values = None

        for obj_name, status_fld, closed_vals in loan_objects_to_try:
            if obj_name in available_objects and available_objects[obj_name].get('queryable'):
                found_object = obj_name
                status_field = status_fld
                closed_values = closed_vals
                break

        if not found_object:
            return {
                "status": "error",
                "message": "No loan object found in Salesforce. Available custom objects: " +
                          ", ".join([k for k, v in available_objects.items() if v.get('custom')])[:500],
                "results": results
            }

        logger.info(f"Using Salesforce object: {found_object}")

        # Get object fields
        describe_response = await _async_get(
            f"{instance_url}/services/data/{SALESFORCE_API_VERSION}/sobjects/{found_object}/describe/",
            headers=headers
        )
        describe_response.raise_for_status()
        describe_data = describe_response.json()

        # Build field list (exclude binary fields)
        queryable_fields = []
        field_info = {}
        for field in describe_data.get('fields', []):
            if field.get('type') not in ['base64', 'address', 'location']:
                queryable_fields.append(field.get('name'))
                field_info[field.get('name')] = {
                    'label': field.get('label'),
                    'type': field.get('type')
                }

        # Build WHERE clause for closed loans
        status_conditions = " OR ".join([f"{status_field} = '{val}'" for val in closed_values])

        # Query closed loans
        field_list = ", ".join(queryable_fields[:40])  # Limit fields
        soql = f"SELECT {field_list} FROM {found_object} WHERE ({status_conditions}) ORDER BY LastModifiedDate DESC LIMIT 200"

        logger.info(f"Executing SOQL: {soql[:200]}...")

        query_response = await _async_get(
            f"{instance_url}/services/data/{SALESFORCE_API_VERSION}/query/",
            headers=headers,
            params={"q": soql}
        )
        query_response.raise_for_status()
        query_data = query_response.json()

        records = query_data.get('records', [])
        logger.info(f"Found {len(records)} closed loans in Salesforce")

        # Get user's organization
        user_org = db.execute(text("SELECT organization_id FROM users WHERE id = :user_id"), {"user_id": user_id}).fetchone()
        org_id = user_org[0] if user_org and user_org[0] else 1

        # Field mapping - try to map common Salesforce fields to our loan fields
        field_mapping = {
            # Standard Opportunity fields
            'Name': 'loan_number',
            'Amount': 'loan_amount',
            'CloseDate': 'funded_at',
            'StageName': 'status',
            'AccountId': 'salesforce_account_id',
            # Common custom fields
            'Property_Address__c': 'property_address',
            'Borrower_Name__c': 'borrower_name',
            'Loan_Amount__c': 'loan_amount',
            'Interest_Rate__c': 'interest_rate',
            'Loan_Type__c': 'loan_type',
            'Property_Type__c': 'property_type',
            'Close_Date__c': 'funded_at',
            # MtgPlanner fields
            'MtgPlanner_CRM__Property_Address__c': 'property_address',
            'MtgPlanner_CRM__Loan_Amount__c': 'loan_amount',
            'MtgPlanner_CRM__Borrower_Name__c': 'borrower_name',
        }

        for record in records:
            try:
                sf_id = record.get('Id')

                # Map fields
                loan_data = {
                    'salesforce_id': sf_id,
                    'organization_id': org_id,
                    'created_by_user_id': user_id,
                    'loan_officer_id': user_id,
                    'status': 'funded',
                    'salesforce_sync_status': 'synced',
                    'salesforce_last_synced_at': datetime.utcnow(),
                }

                # Try to map all available fields
                for sf_field, crm_field in field_mapping.items():
                    if sf_field in record and record[sf_field]:
                        loan_data[crm_field] = record[sf_field]

                # Try to get borrower name from various possible fields
                if 'borrower_name' not in loan_data or not loan_data.get('borrower_name'):
                    for name_field in ['Name', 'Borrower_Name__c', 'MtgPlanner_CRM__Borrower_Name__c', 'Contact_Name__c']:
                        if name_field in record and record[name_field]:
                            loan_data['borrower_name'] = record[name_field]
                            break

                # Try to get loan amount
                if 'loan_amount' not in loan_data or not loan_data.get('loan_amount'):
                    for amt_field in ['Amount', 'Loan_Amount__c', 'MtgPlanner_CRM__Loan_Amount__c']:
                        if amt_field in record and record[amt_field]:
                            loan_data['loan_amount'] = float(record[amt_field])
                            break

                # Generate loan number if not present
                if 'loan_number' not in loan_data or not loan_data.get('loan_number'):
                    loan_data['loan_number'] = f"SF-{sf_id[-8:]}"

                # Use atomic UPSERT to avoid race conditions
                try:
                    upsert_sql, safe_data, is_insert_only = build_safe_upsert_sql(loan_data, conflict_column='salesforce_id')
                    result = db.execute(text(upsert_sql), safe_data)

                    # Check if insert or update based on rowcount
                    # Note: For PostgreSQL, we can use RETURNING to be more precise
                    if result.rowcount > 0:
                        results['imported'] += 1  # Could be insert or update
                    else:
                        results['skipped'] += 1

                except ValueError as ve:
                    logger.warning(f"No valid columns for upsert on {sf_id}: {ve}")
                    results['skipped'] += 1
                    continue

                results['loans'].append({
                    'salesforce_id': sf_id,
                    'name': loan_data.get('borrower_name') or loan_data.get('loan_number'),
                    'amount': loan_data.get('loan_amount'),
                    'action': 'upserted'
                })

            except Exception as e:
                logger.error(f"Error importing loan {record.get('Id')}: {e}")
                results['errors'].append({
                    'salesforce_id': record.get('Id'),
                    'error': str(e)[:200]  # Truncate to avoid exposing sensitive data
                })
                results['skipped'] += 1

        db.commit()

        return {
            "status": "success",
            "message": f"Imported {results['imported']} loans, updated {results['updated']}, {results['skipped']} errors",
            "salesforce_object": found_object,
            "total_found": len(records),
            "results": results
        }

    except requests.exceptions.HTTPError as e:
        logger.error(f"Salesforce API error: {e}")
        raise HTTPException(status_code=502, detail="Salesforce API error")
    except Exception as e:
        logger.error(f"Import failed: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


# ============ Outbound Sync (Push) Endpoints ============

class PushLoanRequest(BaseModel):
    loan_id: int
    sf_object: Optional[str] = "MtgPlanner_CRM__Transaction_Property__c"


class PushBatchRequest(BaseModel):
    loan_ids: list
    sf_object: Optional[str] = "MtgPlanner_CRM__Transaction_Property__c"


@router.post("/push/loan/{loan_id}")
async def push_loan_to_salesforce(
    loan_id: int,
    request: Request,
    sf_object: str = Query("MtgPlanner_CRM__Transaction_Property__c", description="Salesforce object to push to"),
    db: Session = Depends(get_db)
):
    """
    Push a single loan to Salesforce.
    Creates a new record if no salesforce_id exists, otherwise updates existing record.
    """
    user_id = get_current_user_id(request, db)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    # Get stored tokens
    integration = db.execute(text("""
        SELECT access_token, refresh_token, scopes FROM user_integrations
        WHERE user_id = :user_id AND provider = 'salesforce'
    """), {"user_id": user_id}).fetchone()

    if not integration or not integration[0]:
        raise HTTPException(
            status_code=400,
            detail="Salesforce not connected. Please connect first."
        )

    access_token = decrypt_token(integration[0])

    # Parse instance_url from scopes
    instance_url = None
    if integration[2] and "instance_url:" in integration[2]:
        instance_url = parse_instance_url_from_scopes(integration[2])

    if not instance_url:
        raise HTTPException(
            status_code=400,
            detail="Salesforce instance URL not found. Please reconnect."
        )

    from services.salesforce_sync_service import get_salesforce_sync_service

    # Get user's organization
    user_org = db.execute(text("SELECT organization_id FROM users WHERE id = :user_id"), {"user_id": user_id}).fetchone()
    org_id = user_org[0] if user_org and user_org[0] else 1

    sync_service = get_salesforce_sync_service(db, user_id=user_id, organization_id=org_id)
    success, action, result_data = sync_service.push_loan(
        loan_id, access_token, instance_url, sf_object
    )

    if success:
        return {
            "status": "success",
            "action": action,
            "loan_id": loan_id,
            "salesforce_id": result_data,
            "message": f"Loan {loan_id} {action} in Salesforce"
        }
    else:
        raise HTTPException(
            status_code=500,
            detail={
                "status": "error",
                "action": action,
                "loan_id": loan_id,
                "error": result_data
            }
        )


@router.post("/push/batch", response_model=SyncResponse)
async def push_loans_batch_to_salesforce(
    request: Request,
    batch_request: PushBatchRequest,
    db: Session = Depends(get_db)
):
    """
    Push multiple loans to Salesforce.
    Creates new records for loans without salesforce_id, updates existing records.
    """
    user_id = get_current_user_id(request, db)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    # Get stored tokens
    integration = db.execute(text("""
        SELECT access_token, refresh_token, scopes FROM user_integrations
        WHERE user_id = :user_id AND provider = 'salesforce'
    """), {"user_id": user_id}).fetchone()

    if not integration or not integration[0]:
        raise HTTPException(
            status_code=400,
            detail="Salesforce not connected. Please connect first."
        )

    access_token = decrypt_token(integration[0])

    # Parse instance_url from scopes
    instance_url = None
    if integration[2] and "instance_url:" in integration[2]:
        instance_url = parse_instance_url_from_scopes(integration[2])

    if not instance_url:
        raise HTTPException(
            status_code=400,
            detail="Salesforce instance URL not found. Please reconnect."
        )

    from services.salesforce_sync_service import get_salesforce_sync_service

    # Get user's organization
    user_org = db.execute(text("SELECT organization_id FROM users WHERE id = :user_id"), {"user_id": user_id}).fetchone()
    org_id = user_org[0] if user_org and user_org[0] else 1

    sync_service = get_salesforce_sync_service(db, user_id=user_id, organization_id=org_id)
    result = sync_service.push_loans_batch(
        batch_request.loan_ids,
        access_token,
        instance_url,
        batch_request.sf_object
    )

    return SyncResponse(
        status=result.status.value,
        records_processed=result.records_processed,
        records_created=result.records_created,
        records_updated=result.records_updated,
        records_failed=result.records_failed,
        errors=result.errors,
        message=f"Pushed {result.records_processed} loans: {result.records_created} created, {result.records_updated} updated"
    )


@router.get("/push/pending")
async def get_pending_push_loans(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db)
):
    """
    Get loans that need to be pushed to Salesforce.
    Returns loans that have been modified since last sync or never synced.
    """
    user_id = get_current_user_id(request, db)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    from services.salesforce_sync_service import get_salesforce_sync_service

    # Get user's organization
    user_org = db.execute(text("SELECT organization_id FROM users WHERE id = :user_id"), {"user_id": user_id}).fetchone()
    org_id = user_org[0] if user_org and user_org[0] else 1

    sync_service = get_salesforce_sync_service(db, user_id=user_id, organization_id=org_id)
    loans = sync_service.get_pushable_loans(limit=limit)

    return {
        "count": len(loans),
        "loans": loans,
        "message": f"Found {len(loans)} loans pending sync to Salesforce"
    }


@router.get("/loan/{loan_id}/sync-status")
async def get_loan_sync_status(
    loan_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """Get Salesforce sync status for a specific loan."""
    user_id = get_current_user_id(request, db)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    loan = db.execute(text("""
        SELECT id, loan_number, salesforce_id, salesforce_last_synced_at,
               salesforce_sync_status, updated_at
        FROM loans
        WHERE id = :loan_id
    """), {"loan_id": loan_id}).fetchone()

    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")

    # Determine if loan needs sync
    needs_sync = False
    if not loan[2]:  # No salesforce_id
        needs_sync = True
    elif not loan[3]:  # Never synced
        needs_sync = True
    elif loan[5] and loan[3] and loan[5] > loan[3]:  # Updated after last sync
        needs_sync = True

    return {
        "loan_id": loan[0],
        "loan_number": loan[1],
        "salesforce_id": loan[2],
        "last_synced_at": loan[3].isoformat() if loan[3] else None,
        "sync_status": loan[4],
        "updated_at": loan[5].isoformat() if loan[5] else None,
        "needs_sync": needs_sync,
        "is_linked": loan[2] is not None
    }


@router.post("/pull/loan/{loan_id}")
async def pull_loan_from_salesforce(
    loan_id: int,
    request: Request,
    sf_object: str = Query("MtgPlanner_CRM__Transaction_Property__c", description="Salesforce object to pull from"),
    db: Session = Depends(get_db)
):
    """
    Pull/refresh a single loan from Salesforce.
    Updates the CRM loan with the latest data from Salesforce.
    Requires the loan to have an existing salesforce_id.
    """
    user_id = get_current_user_id(request, db)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    # Get stored tokens
    integration = db.execute(text("""
        SELECT access_token, refresh_token, scopes FROM user_integrations
        WHERE user_id = :user_id AND provider = 'salesforce'
    """), {"user_id": user_id}).fetchone()

    if not integration or not integration[0]:
        raise HTTPException(
            status_code=400,
            detail="Salesforce not connected. Please connect first."
        )

    access_token = decrypt_token(integration[0])

    # Parse instance_url from scopes
    instance_url = None
    if integration[2] and "instance_url:" in integration[2]:
        instance_url = parse_instance_url_from_scopes(integration[2])

    if not instance_url:
        raise HTTPException(
            status_code=400,
            detail="Salesforce instance URL not found. Please reconnect."
        )

    from services.salesforce_sync_service import get_salesforce_sync_service

    # Get user's organization
    user_org = db.execute(text("SELECT organization_id FROM users WHERE id = :user_id"), {"user_id": user_id}).fetchone()
    org_id = user_org[0] if user_org and user_org[0] else 1

    sync_service = get_salesforce_sync_service(db, user_id=user_id, organization_id=org_id)
    success, message, updated_data = sync_service.pull_loan(
        loan_id, access_token, instance_url, sf_object
    )

    if success:
        return {
            "status": "success",
            "loan_id": loan_id,
            "message": message,
            "updated_fields": list(updated_data.keys()) if updated_data else []
        }
    else:
        raise HTTPException(
            status_code=500,
            detail={
                "status": "error",
                "loan_id": loan_id,
                "error": message
            }
        )


# ============ Admin Migration Endpoint ============

@router.get("/admin/run-migration")
async def run_salesforce_migration(
    admin_key: str = Query(..., description="Admin API key"),
    db: Session = Depends(get_db)
):
    """
    Run Salesforce database migration.
    Protected by admin API key.
    """
    expected_key = os.getenv("ADMIN_API_KEY", "")
    if admin_key != expected_key:
        raise HTTPException(status_code=403, detail="Invalid admin key")

    results = []

    # Add salesforce columns to loans table
    migrations = [
        ("Add salesforce_id column", """
            ALTER TABLE loans ADD COLUMN IF NOT EXISTS salesforce_id VARCHAR(18) UNIQUE
        """),
        ("Add salesforce_last_synced_at column", """
            ALTER TABLE loans ADD COLUMN IF NOT EXISTS salesforce_last_synced_at TIMESTAMP
        """),
        ("Add salesforce_sync_status column", """
            ALTER TABLE loans ADD COLUMN IF NOT EXISTS salesforce_sync_status VARCHAR(20) DEFAULT 'pending'
        """),
        ("Create salesforce_id index", """
            CREATE INDEX IF NOT EXISTS idx_loans_salesforce_id ON loans(salesforce_id)
        """),
        ("Create salesforce_sync_logs table", """
            CREATE TABLE IF NOT EXISTS salesforce_sync_logs (
                id SERIAL PRIMARY KEY,
                sync_type VARCHAR(20) NOT NULL,
                direction VARCHAR(20) DEFAULT 'inbound',
                salesforce_id VARCHAR(18),
                loan_id INTEGER REFERENCES loans(id) ON DELETE SET NULL,
                status VARCHAR(20) NOT NULL,
                records_processed INTEGER DEFAULT 0,
                records_created INTEGER DEFAULT 0,
                records_updated INTEGER DEFAULT 0,
                records_failed INTEGER DEFAULT 0,
                error_message TEXT,
                payload_summary JSONB,
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                organization_id INTEGER
            )
        """),
        ("Create salesforce_field_mappings table", """
            CREATE TABLE IF NOT EXISTS salesforce_field_mappings (
                id SERIAL PRIMARY KEY,
                organization_id INTEGER NOT NULL,
                salesforce_object VARCHAR(100) NOT NULL,
                salesforce_field VARCHAR(100) NOT NULL,
                crm_entity VARCHAR(50) NOT NULL,
                crm_field VARCHAR(100) NOT NULL,
                transform_type VARCHAR(50),
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(organization_id, salesforce_object, salesforce_field)
            )
        """),
    ]

    for name, sql in migrations:
        try:
            db.execute(text(sql))
            db.commit()
            results.append({"migration": name, "status": "success"})
            logger.info(f"Migration '{name}' completed successfully")
        except SQLAlchemyError as e:
            error_msg = str(e)
            if "already exists" in error_msg.lower():
                results.append({"migration": name, "status": "skipped", "reason": "already exists"})
            else:
                results.append({"migration": name, "status": "error", "error": error_msg})
                logger.error(f"Migration '{name}' failed: {e}")

    return {
        "status": "complete",
        "migrations": results,
        "message": f"Processed {len(results)} migrations"
    }


@router.get("/admin/pull-recent")
async def admin_pull_recent_loans(
    admin_key: str = Query(..., description="Admin API key"),
    limit: int = Query(10, ge=1, le=100, description="Number of loans to pull"),
    db: Session = Depends(get_db)
):
    """
    Admin endpoint to pull recent loans from Salesforce.
    Uses the first connected Salesforce account found.
    Protected by admin API key.
    """
    expected_key = os.getenv("ADMIN_API_KEY", "")
    if admin_key != expected_key:
        raise HTTPException(status_code=403, detail="Invalid admin key")

    # Get the first connected Salesforce account
    integration = db.execute(text("""
        SELECT user_id, access_token, refresh_token, scopes
        FROM user_integrations
        WHERE provider = 'salesforce' AND access_token IS NOT NULL
        ORDER BY updated_at DESC
        LIMIT 1
    """)).fetchone()

    if not integration:
        return {
            "status": "error",
            "message": "No Salesforce connection found. Please connect Salesforce first via the Settings page."
        }

    user_id = integration[0]
    access_token = integration[1]

    # Parse instance_url from scopes
    instance_url = None
    if integration[3] and "instance_url:" in integration[3]:
        instance_url = parse_instance_url_from_scopes(integration[3])

    if not instance_url:
        return {
            "status": "error",
            "message": "Salesforce instance URL not found. Please reconnect Salesforce."
        }

    import requests

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    try:
        # Query the most recent loans from Salesforce
        sf_object = "MtgPlanner_CRM__Transaction_Property__c"

        # Get object fields first
        describe_response = await _async_get(
            f"{instance_url}/services/data/{SALESFORCE_API_VERSION}/sobjects/{sf_object}/describe/",
            headers=headers,
            timeout=30
        )

        if describe_response.status_code == 401:
            return {
                "status": "error",
                "message": "Salesforce token expired. Please reconnect via Settings > Integrations."
            }

        describe_response.raise_for_status()
        describe_data = describe_response.json()

        # Build field list
        queryable_fields = []
        for field in describe_data.get('fields', []):
            if field.get('type') not in ['base64', 'address', 'location']:
                queryable_fields.append(field.get('name'))

        field_list = ", ".join(queryable_fields[:40])
        soql = f"SELECT {field_list} FROM {sf_object} ORDER BY LastModifiedDate DESC LIMIT {limit}"

        logger.info(f"Executing SOQL: {soql[:200]}...")

        query_response = await _async_get(
            f"{instance_url}/services/data/{SALESFORCE_API_VERSION}/query/",
            headers=headers,
            params={"q": soql},
            timeout=30
        )
        query_response.raise_for_status()
        query_data = query_response.json()

        records = query_data.get('records', [])
        logger.info(f"Found {len(records)} loans in Salesforce")

        # Get user's organization
        user_org = db.execute(text("SELECT organization_id FROM users WHERE id = :user_id"), {"user_id": user_id}).fetchone()
        org_id = user_org[0] if user_org and user_org[0] else 1

        # Import the records using the sync service
        from services.salesforce_sync_service import get_salesforce_sync_service, DEFAULT_FIELD_MAPPING

        results = {
            "imported": 0,
            "updated": 0,
            "skipped": 0,
            "errors": [],
            "loans": []
        }

        for record in records:
            try:
                sf_id = record.get('Id')

                # Check if already imported
                existing = db.execute(text(
                    "SELECT id, loan_number FROM loans WHERE salesforce_id = :sf_id"
                ), {"sf_id": sf_id}).fetchone()

                # Map fields using DEFAULT_FIELD_MAPPING
                loan_data = {
                    'salesforce_id': sf_id,
                    'organization_id': org_id,
                    'created_by_user_id': user_id,
                    'salesforce_sync_status': 'synced',
                    'salesforce_last_synced_at': datetime.utcnow(),
                }

                for sf_field, (crm_field, transform) in DEFAULT_FIELD_MAPPING.items():
                    if sf_field in record and record[sf_field] is not None:
                        value = record[sf_field]

                        # Apply transforms
                        if transform == "decimal" and value:
                            try:
                                value = float(value)
                            except Exception:
                                pass
                        elif transform == "date" and value:
                            try:
                                from datetime import datetime as dt
                                value = dt.fromisoformat(value.replace('Z', '+00:00')).date()
                            except Exception:
                                pass

                        loan_data[crm_field] = value

                # Generate loan number if missing
                if not loan_data.get('loan_number'):
                    loan_data['loan_number'] = f"SF-{sf_id[-8:]}"

                if existing:
                    # Update existing loan - use safe SQL builder to prevent injection
                    try:
                        update_sql, safe_data = build_safe_update_sql(loan_data)
                        db.execute(text(update_sql), safe_data)
                        results['updated'] += 1
                        action = 'updated'
                    except ValueError as ve:
                        logger.warning(f"No valid columns to update for {sf_id}: {ve}")
                        results['skipped'] += 1
                        continue
                else:
                    # Insert new loan - use safe SQL builder to prevent injection
                    try:
                        insert_sql, safe_data = build_safe_insert_sql(loan_data)
                        db.execute(text(insert_sql), safe_data)
                        results['imported'] += 1
                        action = 'imported'
                    except ValueError as ve:
                        logger.warning(f"No valid columns to insert for {sf_id}: {ve}")
                        results['skipped'] += 1
                        continue

                results['loans'].append({
                    'salesforce_id': sf_id,
                    'loan_number': loan_data.get('loan_number'),
                    'borrower_name': loan_data.get('borrower_name'),
                    'amount': loan_data.get('amount') or loan_data.get('loan_amount'),
                    'action': action
                })

            except Exception as e:
                logger.error(f"Error importing loan {record.get('Id')}: {e}")
                results['errors'].append({
                    'salesforce_id': record.get('Id'),
                    'error': str(e)[:200]  # Truncate to avoid exposing sensitive data
                })
                results['skipped'] += 1

        db.commit()

        return {
            "status": "success",
            "message": f"Pulled {len(records)} loans: {results['imported']} imported, {results['updated']} updated",
            "instance_url": instance_url,
            "salesforce_object": sf_object,
            "total_found": len(records),
            "results": results
        }

    except requests.exceptions.HTTPError as e:
        logger.error(f"Salesforce API error: {e}")
        return {
            "status": "error",
            "message": "Salesforce API error"
        }
    except Exception as e:
        logger.error(f"Pull failed: {e}")
        db.rollback()
        return {
            "status": "error",
            "message": "Internal server error"
        }


# ============ Import Closed Loans from Salesforce ============

# In-memory tracking of import jobs (for background task status)
_import_jobs: Dict[str, Dict[str, Any]] = {}


async def _run_import_job(job_id: str, user_id: int, also_import_to_mum: bool):
    """Background task to run the Salesforce import"""
    from database import SessionLocal
    import uuid

    try:
        _import_jobs[job_id] = {'status': 'running', 'progress': 'Connecting to Salesforce...'}
        logger.info(f"Starting background import job {job_id} for user {user_id}")

        from scripts.import_salesforce_closed_loans import SalesforceClosedLoansImporter

        # Create importer with user context
        _import_jobs[job_id]['progress'] = 'Querying Salesforce opportunities...'
        importer = SalesforceClosedLoansImporter(user_id=user_id)
        results = await importer.run()

        _import_jobs[job_id]['progress'] = f"Imported {results['imported']} loans, processing MUM clients..."

        mum_results = {'imported': 0, 'errors': []}

        # Also import to MUM clients if requested
        # Create a FRESH db session to see the newly committed loans
        if also_import_to_mum:
            db = SessionLocal()
            try:
                # Use atomic INSERT...SELECT to avoid rollback bug where per-row
                # db.rollback() destroys ALL previous uncommitted inserts
                mum_result = db.execute(text("""
                    INSERT INTO mum_clients (
                        client_name, loan_number, original_close_date,
                        original_rate, loan_balance,
                        original_loan_amount, current_loan_amount,
                        interest_rate, appraisal_value_at_closing,
                        current_property_value, closing_date, first_payment_date,
                        status, engagement_score, created_at, user_id
                    )
                    SELECT
                        COALESCE(
                            NULLIF(l.borrower_name, ''),
                            NULLIF(TRIM(COALESCE(le.first_name, '') || ' ' || COALESCE(le.last_name, '')), ''),
                            'Client - ' || l.loan_number
                        ),
                        l.loan_number,
                        COALESCE(l.funded_date, l.closing_date, CURRENT_DATE),
                        COALESCE(l.rate, 0),
                        COALESCE(l.amount, 0),
                        COALESCE(l.amount, 0),
                        COALESCE(l.amount, 0),
                        COALESCE(l.rate, 0),
                        COALESCE(l.amount * 1.25, 0),
                        COALESCE(l.amount * 1.25, 0),
                        COALESCE(l.closing_date, l.funded_date, CURRENT_DATE),
                        COALESCE(l.funded_date, l.closing_date, CURRENT_DATE),
                        'active',
                        50,
                        CURRENT_TIMESTAMP,
                        :user_id
                    FROM loans l
                    LEFT JOIN leads le ON le.email = l.borrower_email AND le.email IS NOT NULL
                    WHERE (LOWER(CAST(l.stage AS TEXT)) LIKE '%fund%'
                           OR (LOWER(CAST(l.stage AS TEXT)) LIKE '%closed%' AND LOWER(CAST(l.stage AS TEXT)) NOT LIKE '%disclosed%')
                           OR LOWER(CAST(l.stage AS TEXT)) LIKE '%won%'
                           OR LOWER(CAST(l.stage AS TEXT)) LIKE '%ship%'
                           OR l.funded_date IS NOT NULL)
                    AND l.loan_number IS NOT NULL
                    AND NOT EXISTS (
                        SELECT 1 FROM mum_clients m
                        WHERE m.loan_number = l.loan_number
                    )
                """), {'user_id': user_id})

                mum_results['imported'] = mum_result.rowcount
                db.commit()
                logger.info(f"Imported {mum_results['imported']} loans to MUM clients")

            except Exception as e:
                logger.error(f"MUM import phase failed: {e}")
                mum_results['errors'].append(f"MUM import failed: {str(e)}")
                try:
                    db.rollback()
                except Exception:
                    pass
            finally:
                db.close()

        # Update job status with results
        _import_jobs[job_id] = {
            'status': 'completed',
            'results': {
                "status": "success" if results['success'] else "partial",
                "message": f"Import complete: {results['imported']} new loans, {results['updated']} updated, {mum_results['imported']} added to MUM clients",
                "total_found": results['total_found'],
                "imported": results['imported'],
                "updated": results['updated'],
                "failed": results['failed'],
                "mum_imported": mum_results['imported'],
                "errors": (results['errors'] + mum_results['errors'])[:20],
            }
        }
        logger.info(f"Import job {job_id} completed: {results['imported']} imported, {mum_results['imported']} to MUM")

    except Exception as e:
        logger.error(f"Import job {job_id} failed: {e}")
        _import_jobs[job_id] = {'status': 'failed', 'error': str(e)}


@router.get("/debug/salesforce-objects")
async def debug_salesforce_objects(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Debug endpoint to list available Salesforce objects.
    """
    user_id = get_current_user_id(request, db)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    try:
        from scripts.import_salesforce_closed_loans import SalesforceClosedLoansImporter
        import httpx

        importer = SalesforceClosedLoansImporter(user_id=user_id)
        importer.access_token, importer.instance_url = await importer.get_access_token(db)

        # Query for all objects
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{importer.instance_url}/services/data/v60.0/sobjects",
                headers={
                    'Authorization': f'Bearer {importer.access_token}',
                    'Content-Type': 'application/json'
                },
                timeout=30.0
            )

            if response.status_code != 200:
                return {"error": f"Failed to get objects: {response.text}"}

            data = response.json()
            sobjects = data.get('sobjects', [])

            # Filter for relevant objects (mortgage/loan related)
            relevant = [o for o in sobjects if any(term in o['name'].lower() for term in
                        ['loan', 'mortgage', 'opportunity', 'contact', 'account', 'lead', 'mtg', 'crm'])]

            return {
                "status": "success",
                "instance_url": importer.instance_url,
                "total_objects": len(sobjects),
                "relevant_objects": [{"name": o['name'], "label": o.get('label', '')} for o in relevant],
                "all_custom_objects": [{"name": o['name'], "label": o.get('label', '')}
                                        for o in sobjects if o['name'].endswith('__c')][:50]
            }

    except Exception as e:
        logger.error(f"Debug objects failed: {e}")
        return {"status": "error", "error": "Internal server error"}


@router.get("/debug/salesforce-query")
async def debug_salesforce_query(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Debug endpoint to see what Salesforce returns for closed opportunities.
    """
    user_id = get_current_user_id(request, db)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    try:
        from scripts.import_salesforce_closed_loans import SalesforceClosedLoansImporter

        importer = SalesforceClosedLoansImporter(user_id=user_id)

        # Get access token
        importer.access_token, importer.instance_url = await importer.get_access_token(db)

        # Discover fields
        available_fields = await importer.discover_opportunity_fields()

        # Build query
        soql = importer.build_soql_query(available_fields)

        # Execute query
        opportunities = await importer.query_closed_opportunities(soql)

        # Get unique stages
        stages = {}
        for opp in opportunities:
            stage = opp.get('StageName', 'Unknown')
            stages[stage] = stages.get(stage, 0) + 1

        return {
            "status": "success",
            "instance_url": importer.instance_url,
            "soql_query": soql,
            "total_opportunities": len(opportunities),
            "stages_found": stages,
            "sample_opportunities": [
                {
                    "Id": o.get("Id"),
                    "Name": o.get("Name"),
                    "StageName": o.get("StageName"),
                    "Amount": o.get("Amount"),
                    "CloseDate": o.get("CloseDate")
                }
                for o in opportunities[:10]
            ]
        }

    except Exception as e:
        logger.error(f"Debug query failed: {e}")
        return {"status": "error", "error": "Internal server error"}


@router.post("/import-closed-loans")
async def import_closed_loans_from_salesforce(
    request: Request,
    background_tasks: BackgroundTasks,
    also_import_to_mum: bool = Query(True, description="Also import funded loans to MUM clients"),
    db: Session = Depends(get_db)
):
    """
    Import all closed/funded loans from Salesforce into the CRM.

    This endpoint starts a background import job and returns immediately.
    Use GET /import-closed-loans/status/{job_id} to check progress.

    The import queries Salesforce for all Opportunities with Stage = 'Closed Won'
    (or similar funded stages) and imports them into the CRM loans table.

    If also_import_to_mum is True (default), funded loans are also imported to the
    mum_clients table for portfolio management.

    Data flows ONE-WAY: Salesforce → CRM → MUM Clients
    """
    import uuid

    user_id = get_current_user_id(request, db)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    # Generate job ID
    job_id = str(uuid.uuid4())[:8]

    # Start background task
    background_tasks.add_task(_run_import_job, job_id, user_id, also_import_to_mum)

    logger.info(f"Started import job {job_id} for user {user_id}")

    return {
        "status": "started",
        "message": "Import started in background. Check MUM Clients page in 1-2 minutes for results.",
        "job_id": job_id,
        "check_status_url": f"/api/v1/salesforce/import-closed-loans/status/{job_id}"
    }


@router.get("/import-closed-loans/status/{job_id}")
async def get_import_job_status(job_id: str, request: Request, db: Session = Depends(get_db)):
    """Get the status of an import job"""
    user_id = get_current_user_id(request, db)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    job = _import_jobs.get(job_id)
    if not job:
        return {"status": "not_found", "message": "Job not found or expired"}

    return job


@router.post("/import-closed-loans/test-one")
async def test_import_one_closed_loan(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Diagnostic: Try importing just ONE closed loan from Salesforce and return full details.
    This runs synchronously so we can see exactly what happens.
    """
    user_id = get_current_user_id(request, db)
    if not user_id:
        return {"error": "Authentication required"}

    try:
        from scripts.import_salesforce_closed_loans import SalesforceClosedLoansImporter
        from database import SessionLocal

        importer = SalesforceClosedLoansImporter(user_id=user_id)
        test_db = SessionLocal()

        try:
            # Get org_id
            user_row = test_db.execute(text(
                "SELECT organization_id FROM users WHERE id = :uid"
            ), {"uid": user_id}).fetchone()
            importer.organization_id = user_row[0] if user_row else None

            # Connect to Salesforce
            importer.access_token, importer.instance_url = await importer.get_access_token(test_db)

            # Discover fields
            available_fields = await importer.discover_opportunity_fields()

            # Build query but limit to 1
            soql = importer.build_soql_query(available_fields)
            soql = soql.replace('LIMIT 2000', 'LIMIT 1')

            # Query one record
            records = await importer.query_closed_opportunities(soql)
            if not records:
                return {"status": "no_records", "message": "No closed loans found in Salesforce"}

            opp = records[0]

            # Get valid columns
            valid_cols = importer._get_valid_columns(test_db)

            # Transform
            loan_data = importer.transform_opportunity_to_loan(opp)
            raw_keys = set(loan_data.keys())
            filtered_data = {k: v for k, v in loan_data.items() if k in valid_cols}
            removed_keys = raw_keys - set(filtered_data.keys())

            # Try import
            try:
                loan_id = await importer.import_loan(test_db, loan_data)
                test_db.commit()
                result_status = "success"
                result_error = None
            except Exception as imp_err:
                test_db.rollback()
                result_status = "failed"
                result_error = str(imp_err)
                loan_id = None

            return {
                "status": result_status,
                "sf_record_name": opp.get('Name'),
                "sf_record_id": opp.get('Id'),
                "sf_raw_fields": list(opp.keys())[:30],
                "valid_db_columns_count": len(valid_cols),
                "loan_data_keys": sorted(filtered_data.keys()),
                "removed_keys": sorted(removed_keys),
                "salesforce_id_in_valid_cols": 'salesforce_id' in valid_cols,
                "loan_id": loan_id,
                "error": result_error,
                "importer_results": importer.results,
            }

        finally:
            test_db.close()

    except Exception as e:
        logger.error(f"Test import failed: {e}", exc_info=True)
        return {"status": "error", "error": "Import test failed. Check server logs for details."}


# ============ Diagnostic: Check Salesforce Imported Loans ============

@router.get("/imported-loans-check")
async def check_imported_loans(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Diagnostic endpoint to check loans imported from Salesforce
    and whether they should appear in MUM clients.
    """
    user_id = get_current_user_id(request, db)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    try:
        # Get all loans with salesforce_id
        sf_loans = db.execute(text("""
            SELECT id, loan_number, borrower_name, stage,
                   salesforce_id, funded_date, closing_date, amount
            FROM loans
            WHERE salesforce_id IS NOT NULL
            ORDER BY created_at DESC
            LIMIT 50
        """)).fetchall()

        # Get funded loans that should be in MUM (flexible matching)
        should_be_in_mum = db.execute(text("""
            SELECT l.id, l.loan_number, l.borrower_name, l.stage, l.funded_date
            FROM loans l
            WHERE (LOWER(CAST(l.stage AS TEXT)) LIKE '%fund%'
                   OR (LOWER(CAST(l.stage AS TEXT)) LIKE '%closed%' AND LOWER(CAST(l.stage AS TEXT)) NOT LIKE '%disclosed%')
                   OR LOWER(CAST(l.stage AS TEXT)) LIKE '%won%'
                   OR LOWER(CAST(l.stage AS TEXT)) LIKE '%ship%'
                   OR l.funded_date IS NOT NULL)
            AND NOT EXISTS (
                SELECT 1 FROM mum_clients m
                WHERE m.loan_number = l.loan_number
            )
        """)).fetchall()

        # Get count in MUM
        mum_count = db.execute(text("SELECT COUNT(*) FROM mum_clients")).scalar()

        return {
            "salesforce_loans": [
                {
                    "id": l[0], "loan_number": l[1], "borrower": l[2],
                    "stage": l[3], "salesforce_id": l[4],
                    "funded_date": str(l[5]) if l[5] else None,
                    "amount": float(l[7]) if l[7] else None
                }
                for l in sf_loans
            ],
            "loans_should_be_in_mum": [
                {
                    "id": l[0], "loan_number": l[1], "borrower": l[2],
                    "stage": l[3], "funded_date": str(l[4]) if l[4] else None
                }
                for l in should_be_in_mum
            ],
            "mum_client_count": mum_count,
            "salesforce_loan_count": len(sf_loans),
            "loans_missing_from_mum": len(should_be_in_mum)
        }

    except Exception as e:
        logger.error(f"Check imported loans failed: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ============ Debug: Database Stats (No Auth) ============

@router.get("/debug/db-stats")
async def get_db_stats(db: Session = Depends(get_db)):
    """
    Debug endpoint to check database state (no auth required).
    Returns counts and sample data to diagnose import issues.
    """
    try:
        # Count total loans
        total_loans = db.execute(text("SELECT COUNT(*) FROM loans")).scalar() or 0

        # Count salesforce loans
        sf_loans = db.execute(text(
            "SELECT COUNT(*) FROM loans WHERE salesforce_id IS NOT NULL"
        )).scalar() or 0

        # Count MUM clients
        mum_clients = db.execute(text("SELECT COUNT(*) FROM mum_clients")).scalar() or 0

        # Get sample of recent loans with their stage
        sample_loans = db.execute(text("""
            SELECT id, loan_number, borrower_name, stage, salesforce_id, created_at
            FROM loans
            ORDER BY created_at DESC
            LIMIT 10
        """)).fetchall()

        # Count loans that should be in MUM
        should_be_mum = db.execute(text("""
            SELECT COUNT(*) FROM loans l
            WHERE (LOWER(CAST(l.stage AS TEXT)) LIKE '%fund%'
                   OR (LOWER(CAST(l.stage AS TEXT)) LIKE '%closed%' AND LOWER(CAST(l.stage AS TEXT)) NOT LIKE '%disclosed%')
                   OR LOWER(CAST(l.stage AS TEXT)) LIKE '%won%'
                   OR LOWER(CAST(l.stage AS TEXT)) LIKE '%ship%'
                   OR l.funded_date IS NOT NULL)
            AND NOT EXISTS (
                SELECT 1 FROM mum_clients m
                WHERE m.loan_number = l.loan_number
            )
        """)).scalar() or 0

        # Get details of loans that should be in MUM
        mum_candidates = db.execute(text("""
            SELECT l.id, l.loan_number, l.borrower_name, l.stage, l.funded_date
            FROM loans l
            WHERE (LOWER(CAST(l.stage AS TEXT)) LIKE '%fund%'
                   OR (LOWER(CAST(l.stage AS TEXT)) LIKE '%closed%' AND LOWER(CAST(l.stage AS TEXT)) NOT LIKE '%disclosed%')
                   OR LOWER(CAST(l.stage AS TEXT)) LIKE '%won%'
                   OR LOWER(CAST(l.stage AS TEXT)) LIKE '%ship%'
                   OR l.funded_date IS NOT NULL)
            AND NOT EXISTS (
                SELECT 1 FROM mum_clients m
                WHERE m.loan_number = l.loan_number
            )
            LIMIT 20
        """)).fetchall()

        return {
            "total_loans": total_loans,
            "salesforce_loans": sf_loans,
            "mum_clients": mum_clients,
            "loans_should_be_in_mum": should_be_mum,
            "mum_candidates": [
                {
                    "id": l[0],
                    "loan_number": l[1],
                    "borrower": l[2],
                    "stage": l[3],
                    "funded_date": str(l[4]) if l[4] else None
                }
                for l in mum_candidates
            ],
            "recent_loans": [
                {
                    "id": l[0],
                    "loan_number": l[1],
                    "borrower": l[2],
                    "stage": l[3],
                    "salesforce_id": l[4],
                    "created_at": str(l[5]) if l[5] else None
                }
                for l in sample_loans
            ]
        }

    except Exception as e:
        logger.error(f"DB stats failed: {e}")
        return {"error": "Internal server error"}


# ============ Debug: Import Closed Loans from Salesforce (No Auth) ============

@router.post("/debug/import-closed-loans")
async def debug_import_closed_loans_from_sf(
    limit: int = Query(10, description="Max records to import"),
    db: Session = Depends(get_db)
):
    """
    Debug endpoint to import closed loans from Salesforce to CRM (no auth required).
    Limited to 10 records by default for testing.
    """
    from services.salesforce_sync_service import SalesforceSyncService, SALESFORCE_API_VERSION

    try:
        results = {
            'status': 'running',
            'sf_records_found': 0,
            'imported': 0,
            'updated': 0,
            'skipped': 0,
            'errors': [],
            'imported_loans': []
        }

        # Get Salesforce credentials from integration_profiles (new OAuth)
        profile = db.execute(text("""
            SELECT id, access_token_encrypted, refresh_token_encrypted, instance_url, user_id
            FROM integration_profiles
            WHERE provider = 'salesforce' AND access_token_encrypted IS NOT NULL
            ORDER BY updated_at DESC
            LIMIT 1
        """)).fetchone()

        if not profile:
            return {"status": "error", "message": "No Salesforce integration found"}

        profile_id = profile[0]
        instance_url = profile[3]
        user_id = profile[4]

        # Get access token - try refresh first since tokens expire frequently
        from services.salesforce.oauth_service import SalesforceOAuthService
        oauth = SalesforceOAuthService()
        access_token = None
        try:
            # First try to refresh the token (it's likely expired after ~1-2 hours)
            access_token = await oauth.refresh_access_token(db, profile_id)
            logger.info(f"Refreshed Salesforce token for profile {profile_id}")
        except Exception as refresh_err:
            logger.warning(f"Token refresh failed, trying existing token: {refresh_err}")
            # Fall back to existing token
            try:
                access_token, _ = await oauth.get_access_token(db, profile_id)
            except Exception as oauth_err:
                return {
                    "status": "error",
                    "message": f"Failed to get Salesforce access token: {oauth_err}",
                    "hint": "Try reconnecting Salesforce in Settings > Integrations"
                }

        # Query closed loans from Salesforce
        sf_object = "MtgPlanner_CRM__Transaction_Property__c"
        soql = f"""
            SELECT Id, Name, MtgPlanner_CRM__Status__c, MtgPlanner_CRM__Borrower_Name__c,
                   MtgPlanner_CRM__Loan_Amount__c, MtgPlanner_CRM__Interest_Rate__c,
                   MtgPlanner_CRM__Property_Address__c, MtgPlanner_CRM__Property_City__c,
                   MtgPlanner_CRM__Property_State__c, MtgPlanner_CRM__Property_Zip__c,
                   MtgPlanner_CRM__Closing_Date__c,
                   MtgPlanner_CRM__Borrower_Email__c, MtgPlanner_CRM__Borrower_Phone__c,
                   MtgPlanner_CRM__Loan_Type__c, LastModifiedDate
            FROM {sf_object}
            WHERE MtgPlanner_CRM__Status__c = 'Closed'
            ORDER BY LastModifiedDate DESC
            LIMIT {limit}
        """

        import urllib.parse
        encoded_soql = urllib.parse.quote(soql)
        url = f"{instance_url}/services/data/{SALESFORCE_API_VERSION}/query/?q={encoded_soql}"

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }

        response = await _async_get(url, headers=headers, timeout=60)

        if response.status_code != 200:
            return {
                "status": "error",
                "message": f"Salesforce query failed: {response.status_code}",
                "details": response.text[:500],
                "hint": "Token may have expired. Try reconnecting Salesforce."
            }

        sf_data = response.json()
        records = sf_data.get('records', [])
        results['sf_records_found'] = len(records)

        # Import each record
        sync_service = SalesforceSyncService(db, user_id=user_id)

        for record in records:
            try:
                sf_id = record.get('Id')
                borrower_name = record.get('MtgPlanner_CRM__Borrower_Name__c') or record.get('Name', 'Unknown')

                # Map Salesforce record to loan data
                loan_data = {
                    'salesforce_id': sf_id,
                    'borrower_name': borrower_name,
                    'loan_number': record.get('Name'),
                    'amount': record.get('MtgPlanner_CRM__Loan_Amount__c'),
                    'interest_rate': record.get('MtgPlanner_CRM__Interest_Rate__c'),
                    'property_address': record.get('MtgPlanner_CRM__Property_Address__c'),
                    'property_city': record.get('MtgPlanner_CRM__Property_City__c'),
                    'property_state': record.get('MtgPlanner_CRM__Property_State__c'),
                    'property_zip': record.get('MtgPlanner_CRM__Property_Zip__c'),
                    'closing_date': record.get('MtgPlanner_CRM__Closing_Date__c'),
                    'borrower_email': record.get('MtgPlanner_CRM__Borrower_Email__c'),
                    'borrower_phone': record.get('MtgPlanner_CRM__Borrower_Phone__c'),
                    'loan_type': record.get('MtgPlanner_CRM__Loan_Type__c'),
                    'stage': 'FUNDED',  # Closed = Funded
                    'salesforce_sync_status': 'synced',
                    'salesforce_last_synced_at': datetime.utcnow(),
                }

                # Remove None values
                loan_data = {k: v for k, v in loan_data.items() if v is not None}

                # Upsert the loan
                loan_id, action = sync_service.upsert_loan(loan_data)

                if action == 'created':
                    results['imported'] += 1
                    results['imported_loans'].append({
                        'loan_id': loan_id,
                        'borrower': borrower_name,
                        'sf_id': sf_id
                    })
                elif action == 'updated':
                    results['updated'] += 1
                else:
                    results['skipped'] += 1

            except Exception as e:
                results['errors'].append(f"{record.get('Name', 'Unknown')}: {str(e)}")
                results['skipped'] += 1

        results['status'] = 'success'
        return results

    except Exception as e:
        logger.error(f"Debug import failed: {e}")
        import traceback
        return {
            "status": "error",
            "error": "Internal server error"
        }


# ============ Debug: Import to MUM (No Auth) ============

@router.post("/debug/import-to-mum")
async def debug_import_to_mum(db: Session = Depends(get_db)):
    """
    Debug endpoint to import funded loans to MUM (no auth required).
    """
    try:
        results = {'imported': 0, 'skipped': 0, 'errors': [], 'imported_clients': []}

        # Get funded loans not already in mum_clients
        # Columns: 0=id, 1=loan_number, 2=borrower_name, 3=email, 4=phone, 5=amount, 6=rate, 7=funded_date, 8=closing_date
        funded_loans = db.execute(text("""
            SELECT l.id, l.loan_number, l.borrower_name,
                   l.borrower_email, l.borrower_phone, l.amount, l.rate,
                   l.funded_date, l.closing_date, l.property_address,
                   l.property_city, l.property_state, l.property_zip,
                   l.loan_type, l.stage
            FROM loans l
            WHERE (LOWER(CAST(l.stage AS TEXT)) LIKE '%fund%'
                   OR (LOWER(CAST(l.stage AS TEXT)) LIKE '%closed%' AND LOWER(CAST(l.stage AS TEXT)) NOT LIKE '%disclosed%')
                   OR LOWER(CAST(l.stage AS TEXT)) LIKE '%won%'
                   OR LOWER(CAST(l.stage AS TEXT)) LIKE '%ship%'
                   OR l.funded_date IS NOT NULL)
            AND NOT EXISTS (
                SELECT 1 FROM mum_clients m
                WHERE m.loan_number = l.loan_number
            )
        """)).fetchall()

        logger.info(f"Debug: Found {len(funded_loans)} funded loans to import to MUM clients")

        for loan in funded_loans:
            try:
                # Extract borrower name
                client_name = loan[2]  # borrower_name

                if not client_name:
                    results['skipped'] += 1
                    continue

                # Insert into mum_clients (using actual table schema)
                loan_amount = float(loan[5]) if loan[5] else 0
                loan_rate = float(loan[6]) if loan[6] else 0
                close_date = loan[7] or loan[8]  # funded_date or closing_date
                db.execute(text("""
                    INSERT INTO mum_clients (
                        client_name, loan_number, original_close_date,
                        original_rate, loan_balance,
                        original_loan_amount, current_loan_amount,
                        interest_rate, appraisal_value_at_closing,
                        current_property_value, closing_date, first_payment_date,
                        status, created_at
                    ) VALUES (
                        :client_name, :loan_number, :original_close_date,
                        :original_rate, :loan_balance,
                        :original_loan_amount, :current_loan_amount,
                        :interest_rate, :appraisal_value,
                        :property_value, :closing_date, :first_payment_date,
                        'active', CURRENT_TIMESTAMP
                    )
                """), {
                    'client_name': client_name,
                    'loan_number': loan[1],
                    'original_close_date': close_date,
                    'original_rate': loan_rate,
                    'loan_balance': loan_amount,
                    'original_loan_amount': loan_amount,
                    'current_loan_amount': loan_amount,
                    'interest_rate': loan_rate,
                    'appraisal_value': loan_amount * 1.25,
                    'property_value': loan_amount * 1.25,
                    'closing_date': close_date,
                    'first_payment_date': close_date,
                })

                results['imported'] += 1
                results['imported_clients'].append({
                    'loan_number': loan[1],
                    'client_name': client_name
                })

            except Exception as e:
                results['errors'].append(f"Error importing {loan[1]}: {str(e)}")
                try:
                    db.rollback()  # Reset transaction so next insert can proceed
                except Exception:
                    pass

        db.commit()
        return results

    except Exception as e:
        logger.error(f"Debug import to MUM failed: {e}")
        return {"error": "Internal server error"}


# ============ Import Funded Loans to MUM Clients ============

@router.post("/import-to-mum")
async def import_funded_loans_to_mum(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Import all funded loans from the loans table to MUM clients.

    This creates MUM client records for portfolio management from any funded loan
    that doesn't already exist in the mum_clients table.
    """
    user_id = get_current_user_id(request, db)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    try:
        # Use a single atomic INSERT...SELECT to avoid the rollback bug where
        # per-row exception handling with db.rollback() destroys ALL previous
        # uncommitted inserts in the transaction (not just the failed row).
        result = db.execute(text("""
            INSERT INTO mum_clients (
                client_name, loan_number, original_close_date,
                original_rate, loan_balance,
                original_loan_amount, current_loan_amount,
                interest_rate, appraisal_value_at_closing,
                current_property_value, closing_date, first_payment_date,
                status, engagement_score, created_at, user_id
            )
            SELECT
                COALESCE(
                    NULLIF(CASE WHEN l.borrower_name ~ '^[0-9a-zA-Z]{15,18}$' THEN NULL ELSE l.borrower_name END, ''),
                    NULLIF(TRIM(COALESCE(le.first_name, '') || ' ' || COALESCE(le.last_name, '')), ''),
                    'Client - ' || l.loan_number
                ),
                l.loan_number,
                COALESCE(l.funded_date, l.closing_date, CURRENT_DATE),
                COALESCE(l.rate, 0),
                COALESCE(l.amount, 0),
                COALESCE(l.amount, 0),
                COALESCE(l.amount, 0),
                COALESCE(l.rate, 0),
                COALESCE(l.amount * 1.25, 0),
                COALESCE(l.amount * 1.25, 0),
                COALESCE(l.closing_date, l.funded_date, CURRENT_DATE),
                COALESCE(l.funded_date, l.closing_date, CURRENT_DATE),
                'active',
                50,
                CURRENT_TIMESTAMP,
                :user_id
            FROM loans l
            LEFT JOIN leads le ON le.email = l.borrower_email AND le.email IS NOT NULL
            WHERE (LOWER(CAST(l.stage AS TEXT)) LIKE '%fund%'
                   OR (LOWER(CAST(l.stage AS TEXT)) LIKE '%closed%' AND LOWER(CAST(l.stage AS TEXT)) NOT LIKE '%disclosed%')
                   OR LOWER(CAST(l.stage AS TEXT)) LIKE '%won%'
                   OR LOWER(CAST(l.stage AS TEXT)) LIKE '%ship%'
                   OR l.funded_date IS NOT NULL)
            AND l.loan_number IS NOT NULL
            AND NOT EXISTS (
                SELECT 1 FROM mum_clients m
                WHERE m.loan_number = l.loan_number
            )
        """), {'user_id': user_id})

        imported_count = result.rowcount
        db.commit()

        logger.info(f"Imported {imported_count} funded loans to MUM clients for user {user_id}")

        return {
            "status": "success",
            "message": f"Imported {imported_count} funded loans to MUM clients",
            "imported": imported_count,
            "skipped": 0,
            "errors": [],
            "clients": []
        }

    except SQLAlchemyError as e:
        logger.error(f"Import to MUM failed: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/fix-mum-user-ids")
async def fix_mum_client_user_ids(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Fix MUM clients that were created without user_id.
    Sets user_id to current user for any records missing it.
    """
    user_id = get_current_user_id(request, db)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    try:
        # Update all MUM clients without user_id to belong to current user
        result = db.execute(text("""
            UPDATE mum_clients
            SET user_id = :user_id
            WHERE user_id IS NULL
            RETURNING id, client_name, loan_number
        """), {'user_id': user_id})

        updated = result.fetchall()
        db.commit()

        return {
            "status": "success",
            "message": f"Updated {len(updated)} MUM clients with user_id",
            "updated_count": len(updated),
            "updated_clients": [
                {"id": r[0], "client_name": r[1], "loan_number": r[2]}
                for r in updated
            ]
        }
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Failed to fix MUM user IDs: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/fix-mum-client-names")
async def fix_mum_client_names(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Fix MUM clients that show Salesforce IDs instead of real borrower names.
    Updates names from: loans.borrower_name, then leads, then Salesforce Contact API.
    """
    user_id = get_current_user_id(request, db)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    try:
        # Step 1: Fix from loans.borrower_name where it's a real name (not a SF ID)
        from_loans = db.execute(text("""
            UPDATE mum_clients m
            SET client_name = l.borrower_name
            FROM loans l
            WHERE m.loan_number = l.loan_number
            AND l.borrower_name IS NOT NULL
            AND l.borrower_name != ''
            AND l.borrower_name != 'Unknown Borrower'
            AND l.borrower_name !~ '^[0-9a-zA-Z]{15,18}$'
            AND (m.client_name LIKE 'Client - %'
                 OR m.client_name ~ '^[0-9a-zA-Z]{15,18}$')
            RETURNING m.id, m.client_name, m.loan_number
        """))
        fixed_from_loans = from_loans.fetchall()

        # Step 2: Fix remaining from leads (first_name + last_name) via email match
        from_leads = db.execute(text("""
            UPDATE mum_clients m
            SET client_name = TRIM(COALESCE(le.first_name, '') || ' ' || COALESCE(le.last_name, ''))
            FROM leads le, loans l
            WHERE l.loan_number = m.loan_number
            AND le.email = l.borrower_email
            AND le.email IS NOT NULL
            AND l.borrower_email IS NOT NULL
            AND (le.first_name IS NOT NULL OR le.last_name IS NOT NULL)
            AND TRIM(COALESCE(le.first_name, '') || ' ' || COALESCE(le.last_name, '')) != ''
            AND (m.client_name LIKE 'Client - %'
                 OR m.client_name ~ '^[0-9a-zA-Z]{15,18}$')
            RETURNING m.id, m.client_name, m.loan_number
        """))
        fixed_from_leads = from_leads.fetchall()

        # Step 3: Also fix the loans table borrower_name from leads for future imports
        loans_fixed = db.execute(text("""
            UPDATE loans l
            SET borrower_name = TRIM(COALESCE(le.first_name, '') || ' ' || COALESCE(le.last_name, ''))
            FROM leads le
            WHERE le.email = l.borrower_email
            AND le.email IS NOT NULL
            AND (le.first_name IS NOT NULL OR le.last_name IS NOT NULL)
            AND TRIM(COALESCE(le.first_name, '') || ' ' || COALESCE(le.last_name, '')) != ''
            AND (l.borrower_name IS NULL OR l.borrower_name = '' OR l.borrower_name = 'Unknown Borrower'
                 OR l.borrower_name ~ '^[0-9a-zA-Z]{15,18}$')
            RETURNING l.id, l.loan_number
        """))
        loans_updated = loans_fixed.fetchall()

        db.commit()

        # Step 4: Resolve remaining via Salesforce Contact API
        # Uses integration_profiles (new OAuth) instead of user_integrations
        sf_fixed_count = 0
        sf_errors = []
        sf_status = "not_attempted"
        try:
            profile = db.execute(text("""
                SELECT id, access_token_encrypted, refresh_token_encrypted, instance_url, user_id
                FROM integration_profiles
                WHERE provider = 'salesforce' AND access_token_encrypted IS NOT NULL
                ORDER BY updated_at DESC
                LIMIT 1
            """)).fetchone()

            if not profile:
                sf_status = "no_sf_integration"
                sf_errors.append("No Salesforce integration_profile found")
            else:
                profile_id = profile[0]
                instance_url = profile[3]
                sf_integration_user = profile[4]

                from services.salesforce.oauth_service import SalesforceOAuthService
                oauth = SalesforceOAuthService()
                access_token_sf = None

                try:
                    access_token_sf = await oauth.refresh_access_token(db, profile_id)
                except Exception as refresh_err:
                    sf_errors.append(f"Token refresh failed: {str(refresh_err)[:100]}")
                    try:
                        access_token_sf, _ = await oauth.get_access_token(db, profile_id)
                    except Exception as oauth_err:
                        sf_errors.append(f"Token get failed: {str(oauth_err)[:100]}")

                if not access_token_sf or not instance_url:
                    sf_status = "no_credentials"
                    sf_errors.append(f"Missing token or instance_url for profile {profile_id}")
                else:
                    sf_status = "connected"
                    # Get SF Contact IDs from loans.borrower_name for unfixed MUM clients
                    sf_contact_rows = db.execute(text("""
                        SELECT DISTINCT l.borrower_name as contact_id, l.loan_number
                        FROM loans l
                        JOIN mum_clients m ON m.loan_number = l.loan_number
                        WHERE l.borrower_name ~ '^[0-9a-zA-Z]{15,18}$'
                        AND (m.client_name LIKE 'Client - %'
                             OR m.client_name ~ '^[0-9a-zA-Z]{15,18}$')
                    """)).fetchall()

                    sf_errors.append(f"Found {len(sf_contact_rows)} SF Contact IDs to resolve (profile {profile_id})")

                    if sf_contact_rows:
                        contact_ids = list(set(r[0] for r in sf_contact_rows))
                        contact_name_map = {}

                        import urllib.parse
                        for i in range(0, len(contact_ids), 200):
                            batch = contact_ids[i:i + 200]
                            id_list = "','".join(batch)
                            soql = f"SELECT Id, FirstName, LastName FROM Contact WHERE Id IN ('{id_list}')"
                            encoded_soql = urllib.parse.quote(soql)
                            url = f"{instance_url}/services/data/{SALESFORCE_API_VERSION}/query/?q={encoded_soql}"

                            try:
                                import httpx
                                async with httpx.AsyncClient(timeout=30) as client:
                                    resp = await client.get(url, headers={"Authorization": f"Bearer {access_token_sf}"})
                                    if resp.status_code == 200:
                                        result = resp.json()
                                        for rec in result.get("records", []):
                                            first = rec.get("FirstName") or ""
                                            last = rec.get("LastName") or ""
                                            full_name = f"{first} {last}".strip()
                                            if full_name:
                                                contact_name_map[rec["Id"]] = full_name
                                        sf_errors.append(f"Batch {i}: {len(result.get('records', []))} contacts resolved")
                                    else:
                                        sf_errors.append(f"Batch {i}: HTTP {resp.status_code} - {resp.text[:100]}")
                            except Exception as qe:
                                sf_errors.append(f"SOQL batch {i}: {type(qe).__name__}: {str(qe)[:100]}")

                        sf_errors.append(f"Resolved {len(contact_name_map)} unique Contact names")

                        # Update loans and MUM clients with resolved names
                        for contact_id, real_name in contact_name_map.items():
                            db.execute(text("""
                                UPDATE loans SET borrower_name = :name
                                WHERE borrower_name = :contact_id
                            """), {"name": real_name, "contact_id": contact_id})

                            result = db.execute(text("""
                                UPDATE mum_clients m
                                SET client_name = :name
                                FROM loans l
                                WHERE m.loan_number = l.loan_number
                                AND l.borrower_name = :name
                                AND (m.client_name LIKE 'Client - %'
                                     OR m.client_name ~ '^[0-9a-zA-Z]{15,18}$')
                            """), {"name": real_name})
                            sf_fixed_count += result.rowcount

                        db.commit()
        except Exception as sf_err:
            import traceback
            sf_errors.append(f"SF resolution ({type(sf_err).__name__}): {str(sf_err)[:200]}")
            sf_errors.append(f"TB: {traceback.format_exc()[-400:]}")
            logger.warning(f"Salesforce Contact resolution failed: {type(sf_err).__name__}: {sf_err}")

        # Count remaining unfixed
        remaining = db.execute(text("""
            SELECT COUNT(*) FROM mum_clients
            WHERE client_name LIKE 'Client - %'
               OR client_name ~ '^[0-9a-zA-Z]{15,18}$'
        """)).scalar()

        total_fixed = len(fixed_from_loans) + len(fixed_from_leads) + sf_fixed_count

        # Diagnostic: show sample borrower_name values for remaining unfixed
        diag_samples = db.execute(text("""
            SELECT l.borrower_name, l.loan_number, l.borrower_email,
                   m.client_name, LENGTH(l.borrower_name) as name_len
            FROM loans l
            JOIN mum_clients m ON m.loan_number = l.loan_number
            WHERE m.client_name LIKE 'Client - %'
               OR m.client_name ~ '^[0-9a-zA-Z]{15,18}$'
            LIMIT 10
        """)).fetchall()

        return {
            "status": "success",
            "fixed_from_loans": len(fixed_from_loans),
            "fixed_from_leads": len(fixed_from_leads),
            "fixed_from_salesforce": sf_fixed_count,
            "loans_table_updated": len(loans_updated),
            "remaining_unfixed": remaining,
            "sf_status": sf_status,
            "sf_errors": sf_errors if sf_errors else None,
            "message": f"Fixed {total_fixed} MUM client names ({sf_fixed_count} from Salesforce API), {remaining} still need review",
            "samples": [
                {"id": r[0], "new_name": r[1], "loan_number": r[2]}
                for r in (list(fixed_from_loans) + list(fixed_from_leads))[:20]
            ],
            "diagnostic_unfixed_loans": [
                {
                    "borrower_name": r[0],
                    "loan_number": r[1],
                    "borrower_email": r[2],
                    "mum_client_name": r[3],
                    "name_length": r[4]
                }
                for r in diag_samples
            ] if remaining > 0 else []
        }
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to fix MUM client names: {e}")
        return {
            "status": "error",
            "message": "Fix failed due to an internal error",
            "fixed_from_loans": 0,
            "fixed_from_leads": 0,
            "fixed_from_salesforce": 0,
            "loans_table_updated": 0,
            "remaining_unfixed": -1
        }


@router.post("/sync-and-import-mum")
async def sync_salesforce_and_import_mum(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Full sync: Pull closed loans from Salesforce, then import to MUM clients.

    1. Pulls all funded/closed loans from Salesforce
    2. Imports/updates them in the loans table
    3. Creates MUM client records for portfolio management
    """
    user_id = get_current_user_id(request, db)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    results = {
        'salesforce_sync': {'created': 0, 'updated': 0, 'errors': []},
        'mum_import': {'imported': 0, 'errors': []},
        'salesforce_connected': False
    }

    # Step 1: Check for Salesforce connection and sync
    integration = db.execute(text("""
        SELECT user_id, access_token, refresh_token, scopes
        FROM user_integrations
        WHERE provider = 'salesforce' AND access_token IS NOT NULL
        ORDER BY updated_at DESC
        LIMIT 1
    """)).fetchone()

    if integration and integration[1]:
        results['salesforce_connected'] = True
        access_token = integration[1]

        # Parse instance_url
        instance_url = None
        scopes = integration[3] or ""
        if "instance_url:" in scopes:
            instance_url = parse_instance_url_from_scopes(scopes)

        if instance_url:
            try:
                # Pull from Salesforce
                headers = {
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json"
                }

                sf_object = "MtgPlanner_CRM__Transaction_Property__c"

                # Get fields
                describe_url = f"{instance_url}/services/data/{SALESFORCE_API_VERSION}/sobjects/{sf_object}/describe/"
                describe_resp = await _async_get(describe_url, headers=headers, timeout=30)

                if describe_resp.status_code == 200:
                    describe_data = describe_resp.json()
                    queryable_fields = [f['name'] for f in describe_data.get('fields', [])
                                       if f.get('type') not in ['base64', 'address', 'location']]

                    field_list = ", ".join(queryable_fields[:50])

                    # Only include Funded_Date__c filter if the field exists on this object
                    funded_date_filter = ""
                    if 'MtgPlanner_CRM__Funded_Date__c' in queryable_fields:
                        funded_date_filter = "OR MtgPlanner_CRM__Funded_Date__c != null"

                    soql = f"""
                        SELECT {field_list}
                        FROM {sf_object}
                        WHERE MtgPlanner_CRM__Status__c IN ('Funded', 'Closed', 'Closed Won')
                           {funded_date_filter}
                        ORDER BY LastModifiedDate DESC
                        LIMIT 200
                    """

                    query_url = f"{instance_url}/services/data/{SALESFORCE_API_VERSION}/query/"
                    query_resp = await _async_get(query_url, headers=headers, params={"q": soql}, timeout=60)

                    if query_resp.status_code == 200:
                        records = query_resp.json().get('records', [])
                        logger.info(f"Found {len(records)} closed loans in Salesforce")

                        # Import records
                        from services.salesforce_sync_service import DEFAULT_FIELD_MAPPING, STAGE_MAPPING

                        for record in records:
                            try:
                                sf_id = record.get('Id')
                                existing = db.execute(text(
                                    "SELECT id FROM loans WHERE salesforce_id = :sf_id"
                                ), {"sf_id": sf_id}).fetchone()

                                loan_data = {'salesforce_id': sf_id}
                                for sf_field, (crm_field, transform) in DEFAULT_FIELD_MAPPING.items():
                                    if sf_field in record and record[sf_field] is not None:
                                        value = record[sf_field]
                                        if transform == "decimal":
                                            try:
                                                value = float(value)
                                            except Exception:
                                                continue
                                        elif transform == "date":
                                            try:
                                                value = datetime.fromisoformat(value.replace('Z', '+00:00')).date()
                                            except Exception:
                                                try:
                                                    value = datetime.strptime(value[:10], "%Y-%m-%d").date()
                                                except Exception:
                                                    continue
                                        elif transform == "stage_mapping":
                                            value = STAGE_MAPPING.get(str(value), "FUNDED")
                                        loan_data[crm_field] = value

                                loan_data['salesforce_last_synced_at'] = datetime.utcnow()
                                loan_data['salesforce_sync_status'] = 'synced'
                                if not loan_data.get('loan_number'):
                                    loan_data['loan_number'] = f"SF-{sf_id[-8:]}"
                                if not loan_data.get('stage'):
                                    loan_data['stage'] = 'FUNDED'

                                if existing:
                                    update_fields = ", ".join([f"{k} = :{k}" for k in loan_data.keys() if k != 'salesforce_id'])
                                    db.execute(text(f"""
                                        UPDATE loans SET {update_fields}, updated_at = CURRENT_TIMESTAMP
                                        WHERE salesforce_id = :salesforce_id
                                    """), loan_data)
                                    results['salesforce_sync']['updated'] += 1
                                else:
                                    loan_data['organization_id'] = 1
                                    columns = ", ".join(loan_data.keys())
                                    placeholders = ", ".join([f":{k}" for k in loan_data.keys()])
                                    db.execute(text(f"""
                                        INSERT INTO loans ({columns}, created_at, updated_at)
                                        VALUES ({placeholders}, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                                    """), loan_data)
                                    results['salesforce_sync']['created'] += 1

                            except SQLAlchemyError as e:
                                results['salesforce_sync']['errors'].append(str(e))

                        db.commit()

            except SQLAlchemyError as e:
                logger.error(f"Salesforce sync error: {e}")
                results['salesforce_sync']['errors'].append(str(e))

    # Step 2: Import funded loans to MUM clients
    # Columns: 0=id, 1=loan_number, 2=borrower_name, 3=amount, 4=rate, 5=funded_date, 6=closing_date
    try:
        funded_loans = db.execute(text("""
            SELECT l.id, l.loan_number, l.borrower_name,
                   l.amount, l.rate, l.funded_date, l.closing_date
            FROM loans l
            WHERE (LOWER(CAST(l.stage AS TEXT)) LIKE '%fund%'
                   OR (LOWER(CAST(l.stage AS TEXT)) LIKE '%closed%' AND LOWER(CAST(l.stage AS TEXT)) NOT LIKE '%disclosed%')
                   OR LOWER(CAST(l.stage AS TEXT)) LIKE '%won%'
                   OR LOWER(CAST(l.stage AS TEXT)) LIKE '%ship%'
                   OR l.funded_date IS NOT NULL)
            AND NOT EXISTS (
                SELECT 1 FROM mum_clients m
                WHERE m.loan_number = l.loan_number
            )
        """)).fetchall()

        for loan in funded_loans:
            try:
                client_name = loan[2]  # borrower_name
                if not client_name:
                    client_name = f"Client - {loan[1]}"

                close_date = loan[5] or loan[6]  # funded_date or closing_date
                loan_amount = float(loan[3]) if loan[3] else 0
                loan_rate = float(loan[4]) if loan[4] else 0

                db.execute(text("""
                    INSERT INTO mum_clients (
                        client_name, loan_number, original_close_date,
                        original_rate, loan_balance,
                        original_loan_amount, current_loan_amount,
                        interest_rate, appraisal_value_at_closing,
                        current_property_value, closing_date, first_payment_date,
                        status, engagement_score, created_at, user_id
                    ) VALUES (
                        :client_name, :loan_number, :close_date,
                        :rate, :balance,
                        :original_loan_amount, :current_loan_amount,
                        :interest_rate, :appraisal_value,
                        :property_value, :closing_date, :first_payment_date,
                        'active', 50, CURRENT_TIMESTAMP, :user_id
                    )
                """), {
                    'client_name': client_name,
                    'loan_number': loan[1],
                    'close_date': close_date,
                    'rate': loan_rate,
                    'balance': loan_amount,
                    'original_loan_amount': loan_amount,
                    'current_loan_amount': loan_amount,
                    'interest_rate': loan_rate,
                    'appraisal_value': loan_amount * 1.25,
                    'property_value': loan_amount * 1.25,
                    'closing_date': close_date,
                    'first_payment_date': close_date,
                    'user_id': user_id,
                })
                results['mum_import']['imported'] += 1

            except Exception as e:
                results['mum_import']['errors'].append(str(e))
                try:
                    db.rollback()  # Reset transaction so next insert can proceed
                except Exception:
                    pass

        db.commit()

    except SQLAlchemyError as e:
        logger.error(f"MUM import error: {e}")
        results['mum_import']['errors'].append(str(e))

    return {
        "status": "success",
        "salesforce_connected": results['salesforce_connected'],
        "message": f"Synced from Salesforce: {results['salesforce_sync']['created']} new, {results['salesforce_sync']['updated']} updated. MUM clients: {results['mum_import']['imported']} imported.",
        "salesforce_sync": results['salesforce_sync'],
        "mum_import": results['mum_import']
    }


@router.post("/sync-all-loans")
async def sync_all_loans_from_salesforce(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Full sync: Link and pull ALL loans from Salesforce to CRM.

    1. Queries all Transaction_Property records from Salesforce
    2. Matches to CRM loans by loan_number (or creates new loans)
    3. Updates all fields from Salesforce

    This resolves the "Not in Salesforce" issue for existing CRM loans.
    """
    import requests
    import re

    user_id = get_current_user_id(request, db)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    results = {
        'linked': 0,
        'created': 0,
        'updated': 0,
        'skipped': 0,
        'errors': [],
        'details': []
    }

    # Get Salesforce connection - try user's first, then any org connection
    try:
        integration = db.execute(text("""
            SELECT access_token, refresh_token, scopes, user_id
            FROM user_integrations
            WHERE provider = 'salesforce' AND access_token IS NOT NULL
            ORDER BY
                CASE WHEN user_id = :user_id THEN 0 ELSE 1 END,
                updated_at DESC
            LIMIT 1
        """), {"user_id": user_id}).fetchone()
    except Exception as e:
        logger.error(f"Database error querying Salesforce integration: {e}")
        raise HTTPException(status_code=500, detail="Database error")

    if not integration or not integration[0]:
        # Check if table exists and has any rows
        try:
            count = db.execute(text("SELECT COUNT(*) FROM user_integrations WHERE provider = 'salesforce'")).fetchone()
            logger.info(f"Found {count[0] if count else 0} Salesforce integrations in database")
        except Exception as e:
            logger.error(f"Error checking integrations: {e}")
        raise HTTPException(
            status_code=400,
            detail="Salesforce not connected. Please connect first at Settings > Integrations."
        )

    # Use token directly (matching other working endpoints)
    access_token = integration[0]
    refresh_token = integration[1]  # For token refresh on 401
    integration_user_id = integration[3]

    logger.info(f"Using Salesforce connection from user {integration_user_id}")

    # Parse instance_url from scopes
    instance_url = None
    scopes_str = integration[2] or ""
    logger.info(f"Scopes string: {scopes_str[:100]}...")

    if "instance_url:" in scopes_str:
        instance_url = parse_instance_url_from_scopes(scopes_str)
        logger.info(f"Parsed instance URL: {instance_url}")

    if not instance_url:
        # Try to get from a different location - check if stored separately
        logger.warning("Instance URL not found in scopes, checking alternatives...")
        raise HTTPException(
            status_code=400,
            detail=f"Salesforce instance URL not found in scopes. Scopes: {scopes_str[:200]}. Please reconnect."
        )

    # Get user's organization
    user_org = db.execute(text("SELECT organization_id FROM users WHERE id = :user_id"), {"user_id": user_id}).fetchone()
    org_id = user_org[0] if user_org and user_org[0] else 1

    try:
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }

        # Discover which fields actually exist on the Salesforce object
        sf_object = "MtgPlanner_CRM__Transaction_Property__c"
        desired_fields = [
            'Id', 'Name',
            'MtgPlanner_CRM__Loan_Amount__c', 'MtgPlanner_CRM__Loan_Type__c', 'MtgPlanner_CRM__Loan_Program__c',
            'MtgPlanner_CRM__Interest_Rate__c', 'MtgPlanner_CRM__Note_Rate__c',
            'MtgPlanner_CRM__Property_Address__c', 'MtgPlanner_CRM__Property_City__c',
            'MtgPlanner_CRM__Property_State__c', 'MtgPlanner_CRM__Property_Zip__c',
            'MtgPlanner_CRM__Purchase_Price__c', 'MtgPlanner_CRM__Down_Payment__c',
            'MtgPlanner_CRM__Borrower_Name__c', 'MtgPlanner_CRM__Borrower_Email__c',
            'MtgPlanner_CRM__Borrower_Phone__c', 'MtgPlanner_CRM__CoBorrower_Name__c',
            'MtgPlanner_CRM__Status__c', 'MtgPlanner_CRM__Stage__c',
            'MtgPlanner_CRM__Closing_Date__c', 'MtgPlanner_CRM__Application_Date__c',
            'MtgPlanner_CRM__Lock_Date__c', 'MtgPlanner_CRM__Lock_Expiration__c',
            'MtgPlanner_CRM__Funded_Date__c', 'MtgPlanner_CRM__Clear_To_Close_Date__c',
            'MtgPlanner_CRM__UW_Received_Date__c', 'MtgPlanner_CRM__Loan_Approved_Date__c',
            'MtgPlanner_CRM__Appraisal_Ordered_Date__c', 'MtgPlanner_CRM__Appraisal_Received_Date__c',
            'MtgPlanner_CRM__CD_Sent_To_Borrower_Date__c', 'MtgPlanner_CRM__Scheduled_Closing_Date__c',
            'MtgPlanner_CRM__First_Payment_Date__c', 'MtgPlanner_CRM__Loan_Purpose__c',
            'MtgPlanner_CRM__LTV__c', 'MtgPlanner_CRM__CLTV__c',
            'MtgPlanner_CRM__Property_Type__c', 'MtgPlanner_CRM__Occupancy_Type__c',
            'MtgPlanner_CRM__Mortgage_Ins_1st_TD__c', 'MtgPlanner_CRM__Property_Tax_1st_TD__c',
            'MtgPlanner_CRM__Hazard_Ins_1st_TD__c', 'MtgPlanner_CRM__HOA_1st_TD__c',
            'MtgPlanner_CRM__Monthly_Payment_1st_TD__c',
            'CreatedDate', 'LastModifiedDate',
        ]

        # Describe object to find available fields
        describe_url = f"{instance_url}/services/data/{SALESFORCE_API_VERSION}/sobjects/{sf_object}/describe/"
        describe_resp = await _async_get(describe_url, headers=headers, timeout=30)
        if describe_resp.status_code == 200:
            available_fields = {f['name'] for f in describe_resp.json().get('fields', [])}
            query_fields = [f for f in desired_fields if f in available_fields]
        else:
            # Fallback: use basic fields only
            logger.warning(f"Could not describe {sf_object}, using basic fields")
            query_fields = ['Id', 'Name', 'MtgPlanner_CRM__Status__c', 'CreatedDate', 'LastModifiedDate']

        field_list = ", ".join(query_fields)
        soql = f"""
            SELECT {field_list}
            FROM {sf_object}
            ORDER BY LastModifiedDate DESC
            LIMIT 500
        """

        # Use params instead of URL encoding (matches working endpoints)
        query_url = f"{instance_url}/services/data/{SALESFORCE_API_VERSION}/query/"
        response = await _async_get(query_url, headers=headers, params={"q": soql}, timeout=60)

        # Handle token expiration with refresh
        if response.status_code == 401 and refresh_token:
            logger.info(f"Got 401, attempting token refresh for sync-all-loans")
            try:
                from integrations.salesforce_service import salesforce_client
                new_tokens = salesforce_client.refresh_access_token(refresh_token)

                if new_tokens and new_tokens.get("access_token"):
                    access_token = new_tokens["access_token"]

                    # Update token in database
                    try:
                        db.execute(text("""
                            UPDATE user_integrations
                            SET access_token = :access_token, updated_at = CURRENT_TIMESTAMP
                            WHERE user_id = :user_id AND provider = 'salesforce'
                        """), {
                            "access_token": access_token,
                            "user_id": integration_user_id
                        })
                        db.commit()
                        logger.info(f"Successfully refreshed token for user {integration_user_id}")
                    except Exception as db_error:
                        logger.error(f"Failed to update refreshed token: {db_error}")
                        db.rollback()

                    # Retry with new token
                    headers = {
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json"
                    }
                    response = await _async_get(query_url, headers=headers, params={"q": soql}, timeout=60)
                else:
                    logger.error("Token refresh failed - refresh token has expired")
                    # Use 424 (Failed Dependency) instead of 401 to avoid triggering CRM logout
                    # 401 is for CRM auth issues, 424 indicates the Salesforce dependency failed
                    raise HTTPException(
                        status_code=424,
                        detail="Your Salesforce connection has expired. Please go to Settings > Integrations and click 'Reconnect' next to Salesforce to re-authorize the connection."
                    )
            except ImportError:
                logger.error("Could not import salesforce_client for token refresh")
                raise HTTPException(
                    status_code=424,
                    detail="Salesforce session expired. Please reconnect Salesforce at Settings > Integrations."
                )

        if response.status_code != 200:
            error_text = response.text
            logger.error(f"Salesforce query failed: {error_text}")
            raise HTTPException(status_code=500, detail="Salesforce query failed. Check server logs for details.")

        sf_data = response.json()
        sf_records = sf_data.get("records", [])

        logger.info(f"Found {len(sf_records)} loans in Salesforce")

        # Stage mapping from Salesforce to CRM
        stage_mapping = {
            "New": "APPLICATION",
            "Application": "APPLICATION",
            "Submitted": "PROCESSING",
            "Processing": "PROCESSING",
            "In Processing": "PROCESSING",
            "Loan in Process": "PROCESSING",
            "Underwriting": "UNDERWRITING",
            "In Underwriting": "UNDERWRITING",
            "Conditionally Approved": "APPROVED",
            "Approved": "APPROVED",
            "Clear to Close": "CLEAR_TO_CLOSE",
            "CTC": "CLEAR_TO_CLOSE",
            "Docs": "DOCS",
            "Docs Out": "DOCS",
            "File Complete": "FUNDED",
            "Funded": "FUNDED",
            "Closed": "FUNDED",
        }

        # Process each Salesforce record
        for sf_record in sf_records:
            try:
                sf_id = sf_record.get("Id")
                sf_name = sf_record.get("Name", "")  # e.g., "Joseph Riley - Loan # RCA0000010075"

                # Extract loan number from Name field (format: "Borrower Name - Loan # XXXXXX")
                loan_number = None
                if "Loan #" in sf_name:
                    match = re.search(r'Loan #\s*(\S+)', sf_name)
                    if match:
                        loan_number = match.group(1)
                elif "RCA" in sf_name:
                    match = re.search(r'(RCA\d+)', sf_name)
                    if match:
                        loan_number = match.group(1)
                else:
                    # Use the full Name if no loan number pattern found
                    loan_number = sf_name

                # Try to find existing CRM loan by salesforce_id first, then by loan_number
                existing_loan = db.execute(text("""
                    SELECT id, loan_number, salesforce_id FROM loans
                    WHERE salesforce_id = :sf_id
                       OR (loan_number = :loan_number AND loan_number IS NOT NULL)
                    LIMIT 1
                """), {"sf_id": sf_id, "loan_number": loan_number}).fetchone()

                # Map Salesforce fields to CRM fields
                sf_status = sf_record.get("MtgPlanner_CRM__Status__c") or sf_record.get("MtgPlanner_CRM__Stage__c") or "Processing"
                crm_stage = stage_mapping.get(sf_status, "PROCESSING")

                # Parse dates
                def parse_date(date_str):
                    if date_str:
                        try:
                            return date_str[:10]  # YYYY-MM-DD
                        except:
                            return None
                    return None

                # Build loan data
                loan_data = {
                    "salesforce_id": sf_id,
                    "loan_number": loan_number,
                    "borrower_name": sf_record.get("MtgPlanner_CRM__Borrower_Name__c"),
                    "borrower_email": sf_record.get("MtgPlanner_CRM__Borrower_Email__c"),
                    "borrower_phone": sf_record.get("MtgPlanner_CRM__Borrower_Phone__c"),
                    "coborrower_name": sf_record.get("MtgPlanner_CRM__CoBorrower_Name__c"),
                    "amount": sf_record.get("MtgPlanner_CRM__Loan_Amount__c"),
                    "loan_type": sf_record.get("MtgPlanner_CRM__Loan_Type__c"),
                    "program": sf_record.get("MtgPlanner_CRM__Loan_Program__c"),
                    "interest_rate": sf_record.get("MtgPlanner_CRM__Note_Rate__c") or sf_record.get("MtgPlanner_CRM__Interest_Rate__c"),
                    "property_address": sf_record.get("MtgPlanner_CRM__Property_Address__c"),
                    "property_city": sf_record.get("MtgPlanner_CRM__Property_City__c"),
                    "property_state": sf_record.get("MtgPlanner_CRM__Property_State__c"),
                    "property_zip": sf_record.get("MtgPlanner_CRM__Property_Zip__c"),
                    "purchase_price": sf_record.get("MtgPlanner_CRM__Purchase_Price__c"),
                    "down_payment": sf_record.get("MtgPlanner_CRM__Down_Payment__c"),
                    "stage": crm_stage,
                    "loan_purpose": sf_record.get("MtgPlanner_CRM__Loan_Purpose__c"),
                    "ltv": sf_record.get("MtgPlanner_CRM__LTV__c"),
                    "cltv": sf_record.get("MtgPlanner_CRM__CLTV__c"),
                    "property_type": sf_record.get("MtgPlanner_CRM__Property_Type__c"),
                    "occupancy_type": sf_record.get("MtgPlanner_CRM__Occupancy_Type__c"),
                    "mortgage_insurance": sf_record.get("MtgPlanner_CRM__Mortgage_Ins_1st_TD__c"),
                    "property_tax": sf_record.get("MtgPlanner_CRM__Property_Tax_1st_TD__c"),
                    "hazard_insurance": sf_record.get("MtgPlanner_CRM__Hazard_Ins_1st_TD__c"),
                    "hoa_amount": sf_record.get("MtgPlanner_CRM__HOA_1st_TD__c"),
                    "monthly_payment": sf_record.get("MtgPlanner_CRM__Monthly_Payment_1st_TD__c"),
                    "closing_date": parse_date(sf_record.get("MtgPlanner_CRM__Closing_Date__c")),
                    "application_date": parse_date(sf_record.get("MtgPlanner_CRM__Application_Date__c")),
                    "lock_date": parse_date(sf_record.get("MtgPlanner_CRM__Lock_Date__c")),
                    "lock_expiration_date": parse_date(sf_record.get("MtgPlanner_CRM__Lock_Expiration__c")),
                    "funded_date": parse_date(sf_record.get("MtgPlanner_CRM__Funded_Date__c")),
                    "clear_to_close_date": parse_date(sf_record.get("MtgPlanner_CRM__Clear_To_Close_Date__c")),
                    "uw_received_date": parse_date(sf_record.get("MtgPlanner_CRM__UW_Received_Date__c")),
                    "loan_approved_date": parse_date(sf_record.get("MtgPlanner_CRM__Loan_Approved_Date__c")),
                    "appraisal_ordered_date": parse_date(sf_record.get("MtgPlanner_CRM__Appraisal_Ordered_Date__c")),
                    "appraisal_received_date": parse_date(sf_record.get("MtgPlanner_CRM__Appraisal_Received_Date__c")),
                    "cd_sent_to_borrower_date": parse_date(sf_record.get("MtgPlanner_CRM__CD_Sent_To_Borrower_Date__c")),
                    "scheduled_closing_date": parse_date(sf_record.get("MtgPlanner_CRM__Scheduled_Closing_Date__c")),
                    "first_payment_date": parse_date(sf_record.get("MtgPlanner_CRM__First_Payment_Date__c")),
                    "salesforce_last_synced_at": datetime.utcnow(),
                    "salesforce_sync_status": "synced",
                }

                # Remove None values to avoid overwriting with nulls
                loan_data = {k: v for k, v in loan_data.items() if v is not None}

                if existing_loan:
                    # Update existing loan
                    loan_id = existing_loan[0]
                    was_linked = existing_loan[2] is not None

                    # Build UPDATE statement
                    update_parts = [f"{k} = :{k}" for k in loan_data.keys()]
                    update_sql = f"UPDATE loans SET {', '.join(update_parts)}, updated_at = CURRENT_TIMESTAMP WHERE id = :loan_id"
                    loan_data["loan_id"] = loan_id

                    db.execute(text(update_sql), loan_data)

                    if was_linked:
                        results['updated'] += 1
                    else:
                        results['linked'] += 1
                        results['details'].append(f"Linked: {loan_number} -> {sf_id}")
                else:
                    # Create new loan
                    loan_data["organization_id"] = org_id
                    loan_data["loan_officer_id"] = user_id

                    if not loan_data.get("amount"):
                        loan_data["amount"] = 0  # Required field

                    fields = list(loan_data.keys())
                    placeholders = [f":{f}" for f in fields]

                    db.execute(text(f"""
                        INSERT INTO loans ({', '.join(fields)})
                        VALUES ({', '.join(placeholders)})
                    """), loan_data)

                    results['created'] += 1
                    results['details'].append(f"Created: {loan_number}")

            except Exception as e:
                results['errors'].append(f"Error processing {sf_record.get('Name', 'unknown')}: {str(e)}")
                logger.error(f"Error syncing loan: {e}")

        db.commit()

        return {
            "status": "success",
            "message": f"Synced {len(sf_records)} loans from Salesforce. Linked: {results['linked']}, Created: {results['created']}, Updated: {results['updated']}",
            "total_salesforce_records": len(sf_records),
            "linked": results['linked'],
            "created": results['created'],
            "updated": results['updated'],
            "errors": results['errors'][:10],  # Limit error details
            "details": results['details'][:20]  # Limit details
        }

    except requests.RequestException as e:
        logger.error(f"Salesforce request error: {e}")
        raise HTTPException(status_code=500, detail="Salesforce connection error")


@router.get("/debug/connection")
async def debug_salesforce_connection(
    db: Session = Depends(get_db)
):
    """
    Debug endpoint to check Salesforce connection status.
    No auth required for debugging.
    """
    result = {"sources_checked": []}

    try:
        # Check new integration_profiles table first (OAuth flow stores here)
        profile = db.execute(text("""
            SELECT user_id, status, instance_url, sf_username,
                   CASE WHEN access_token_encrypted IS NOT NULL THEN 'has_token' ELSE 'no_token' END as token_status,
                   updated_at, connected_at
            FROM integration_profiles
            WHERE provider = 'salesforce'
            ORDER BY updated_at DESC
            LIMIT 1
        """)).fetchone()

        if profile:
            result["integration_profiles"] = {
                "status": "found",
                "user_id": profile[0],
                "connection_status": profile[1],
                "instance_url": profile[2][:50] if profile[2] else None,
                "sf_username": profile[3],
                "token_status": profile[4],
                "updated_at": str(profile[5]) if profile[5] else None,
                "connected_at": str(profile[6]) if profile[6] else None
            }
            result["sources_checked"].append("integration_profiles")
        else:
            result["integration_profiles"] = {"status": "not_found"}

        # Also check old user_integrations table
        integration = db.execute(text("""
            SELECT user_id,
                   CASE WHEN access_token IS NOT NULL THEN 'has_token' ELSE 'no_token' END as token_status,
                   scopes,
                   updated_at
            FROM user_integrations
            WHERE provider = 'salesforce'
            ORDER BY updated_at DESC
            LIMIT 1
        """)).fetchone()

        if integration:
            scopes = integration[2] or ""
            instance_url = None
            if "instance_url:" in scopes:
                instance_url = parse_instance_url_from_scopes(scopes).strip()

            result["user_integrations"] = {
                "status": "found",
                "user_id": integration[0],
                "token_status": integration[1],
                "instance_url": instance_url[:50] if instance_url else None,
                "updated_at": str(integration[3]) if integration[3] else None
            }
            result["sources_checked"].append("user_integrations")
        else:
            result["user_integrations"] = {"status": "not_found"}

        # Determine overall status
        if profile and profile[4] == "has_token":
            result["recommended_source"] = "integration_profiles"
            result["overall_status"] = "connected"
        elif integration and integration[1] == "has_token":
            result["recommended_source"] = "user_integrations"
            result["overall_status"] = "connected"
        else:
            result["overall_status"] = "disconnected"

        return result

    except Exception as e:
        return {
            "status": "error",
            "error": "Internal server error"
        }


@router.get("/debug/token-refresh")
async def debug_token_refresh(
    db: Session = Depends(get_db)
):
    """
    Debug endpoint to explicitly test token refresh.
    Shows detailed info about why refresh might fail.
    """
    try:
        # Get integration with refresh_token
        integration = db.execute(text("""
            SELECT access_token, refresh_token, scopes, user_id
            FROM user_integrations
            WHERE provider = 'salesforce' AND access_token IS NOT NULL
            ORDER BY updated_at DESC
            LIMIT 1
        """)).fetchone()

        if not integration:
            return {"status": "error", "message": "No Salesforce integration found"}

        access_token = integration[0]
        refresh_token = integration[1]
        integration_user_id = integration[3]

        result = {
            "has_access_token": bool(access_token),
            "access_token_length": len(access_token) if access_token else 0,
            "has_refresh_token": bool(refresh_token),
            "refresh_token_length": len(refresh_token) if refresh_token else 0,
            "user_id": integration_user_id,
        }

        if not refresh_token:
            result["status"] = "error"
            result["message"] = "No refresh_token stored - cannot refresh"
            return result

        # Try to refresh
        try:
            from integrations.salesforce_service import salesforce_client
            result["salesforce_client_enabled"] = salesforce_client.enabled

            if not salesforce_client.enabled:
                result["status"] = "error"
                result["message"] = "Salesforce client not enabled"
                return result

            # Try to decrypt refresh token (it might be encrypted)
            token_to_use = refresh_token
            try:
                decrypted = decrypt_token(refresh_token)
                if decrypted and decrypted != refresh_token:
                    token_to_use = decrypted
                    result["token_was_encrypted"] = True
            except Exception as decrypt_err:
                result["decrypt_error"] = str(decrypt_err)
                result["token_was_encrypted"] = False

            # Try refresh with potentially decrypted token
            # First, try a direct request to see the actual error response
            import requests as req
            direct_response = req.post(
                "https://login.salesforce.com/services/oauth2/token",
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": token_to_use,
                    "client_id": salesforce_client.client_id,
                    "client_secret": salesforce_client.client_secret
                },
                timeout=30
            )
            result["direct_refresh_status"] = direct_response.status_code
            result["direct_refresh_response"] = direct_response.text[:500]

            new_tokens = salesforce_client.refresh_access_token(token_to_use)

            if new_tokens and new_tokens.get("access_token"):
                new_access_token = new_tokens["access_token"]
                result["refresh_success"] = True
                result["new_token_length"] = len(new_access_token)

                # Update in database
                db.execute(text("""
                    UPDATE user_integrations
                    SET access_token = :access_token, updated_at = CURRENT_TIMESTAMP
                    WHERE user_id = :user_id AND provider = 'salesforce'
                """), {
                    "access_token": new_access_token,
                    "user_id": integration_user_id
                })
                db.commit()
                result["status"] = "success"
                result["message"] = "Token refreshed and saved"
            else:
                result["refresh_success"] = False
                result["status"] = "error"
                result["message"] = "Refresh token has expired. User must reconnect Salesforce at Settings > Integrations."

        except Exception as refresh_error:
            result["status"] = "error"
            result["refresh_error"] = str(refresh_error)
            result["message"] = f"Refresh failed: {str(refresh_error)}"

        return result

    except Exception as e:
        return {
            "status": "error",
            "error": "Internal server error"
        }


@router.get("/debug/test-query")
async def debug_test_salesforce_query(
    db: Session = Depends(get_db)
):
    """
    Debug endpoint to test an actual Salesforce query.
    Includes automatic token refresh on 401 errors.
    No auth required for debugging.
    """
    try:
        # Get Salesforce integration with refresh_token
        integration = db.execute(text("""
            SELECT access_token, refresh_token, scopes, user_id
            FROM user_integrations
            WHERE provider = 'salesforce' AND access_token IS NOT NULL
            ORDER BY updated_at DESC
            LIMIT 1
        """)).fetchone()

        if not integration:
            return {"status": "error", "message": "No Salesforce integration found"}

        access_token = integration[0]
        refresh_token = integration[1]
        scopes = integration[2] or ""
        integration_user_id = integration[3]

        # Parse instance_url
        if "instance_url:" not in scopes:
            return {"status": "error", "message": "No instance URL in scopes"}

        instance_url = parse_instance_url_from_scopes(scopes).strip()

        # Try a simple query
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }

        # Simple query - just get 1 record
        soql = "SELECT Id, Name FROM MtgPlanner_CRM__Transaction_Property__c LIMIT 1"
        query_url = f"{instance_url}/services/data/{SALESFORCE_API_VERSION}/query/"

        response = await _async_get(query_url, headers=headers, params={"q": soql}, timeout=30)

        # Handle 401 with token refresh
        token_refreshed = False
        if response.status_code == 401 and refresh_token:
            try:
                from integrations.salesforce_service import salesforce_client
                new_tokens = salesforce_client.refresh_access_token(refresh_token)

                if new_tokens and new_tokens.get("access_token"):
                    access_token = new_tokens["access_token"]
                    token_refreshed = True

                    # Update token in database
                    db.execute(text("""
                        UPDATE user_integrations
                        SET access_token = :access_token, updated_at = CURRENT_TIMESTAMP
                        WHERE user_id = :user_id AND provider = 'salesforce'
                    """), {
                        "access_token": access_token,
                        "user_id": integration_user_id
                    })
                    db.commit()

                    # Retry with new token
                    headers["Authorization"] = f"Bearer {access_token}"
                    response = await _async_get(query_url, headers=headers, params={"q": soql}, timeout=30)
            except Exception as refresh_error:
                return {
                    "status": "error",
                    "message": "Token expired and refresh failed",
                    "refresh_error": str(refresh_error)
                }

        if response.status_code == 200:
            data = response.json()
            return {
                "status": "success",
                "message": "Salesforce query successful",
                "token_refreshed": token_refreshed,
                "total_size": data.get("totalSize", 0),
                "records": data.get("records", [])[:3]
            }
        else:
            return {
                "status": "error",
                "http_status": response.status_code,
                "response": response.text[:500],
                "token_refreshed": token_refreshed
            }

    except Exception as e:
        return {
            "status": "error",
            "error": "Internal server error"
        }


@router.get("/debug/all-statuses")
async def debug_all_statuses(
    db: Session = Depends(get_db)
):
    """
    Debug endpoint to query ALL records and show their statuses.
    This helps identify what status values actually exist in Salesforce.
    No auth required for debugging.
    """
    try:
        access_token = None
        refresh_token = None
        instance_url = None
        token_source = None

        # First try the new integration_profiles table (OAuth flow stores here)
        try:
            from services.salesforce.oauth_service import decrypt_value
            profile = db.execute(text("""
                SELECT access_token_encrypted, refresh_token_encrypted, instance_url, user_id
                FROM integration_profiles
                WHERE provider = 'salesforce' AND access_token_encrypted IS NOT NULL
                ORDER BY updated_at DESC
                LIMIT 1
            """)).fetchone()

            if profile and profile[0]:
                access_token = decrypt_value(profile[0])
                refresh_token = decrypt_value(profile[1]) if profile[1] else None
                instance_url = profile[2]
                token_source = "integration_profiles"
        except Exception as e:
            logger.warning(f"Could not check integration_profiles: {e}")

        # Fallback to old user_integrations table
        if not access_token:
            integration = db.execute(text("""
                SELECT access_token, refresh_token, scopes, user_id
                FROM user_integrations
                WHERE provider = 'salesforce' AND access_token IS NOT NULL
                ORDER BY updated_at DESC
                LIMIT 1
            """)).fetchone()

            if integration:
                access_token = integration[0]
                refresh_token = integration[1]
                scopes = integration[2] or ""
                if "instance_url:" in scopes:
                    instance_url = parse_instance_url_from_scopes(scopes).strip()
                token_source = "user_integrations"

        if not access_token:
            return {"status": "error", "message": "No Salesforce integration found in either table"}

        if not instance_url:
            return {"status": "error", "message": "No instance URL found"}

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }

        # Query ALL records without any WHERE clause, just get status field
        # Note: Some fields may not exist in all orgs, use simple query
        soql = """
            SELECT Id, Name, MtgPlanner_CRM__Status__c,
                   MtgPlanner_CRM__Borrower_Name__c, LastModifiedDate
            FROM MtgPlanner_CRM__Transaction_Property__c
            ORDER BY LastModifiedDate DESC
            LIMIT 100
        """
        query_url = f"{instance_url}/services/data/{SALESFORCE_API_VERSION}/query/"

        response = await _async_get(query_url, headers=headers, params={"q": soql}, timeout=60)

        # Handle 401 with token refresh
        if response.status_code == 401 and refresh_token:
            try:
                from integrations.salesforce_service import salesforce_client
                new_tokens = salesforce_client.refresh_access_token(refresh_token)
                if new_tokens and new_tokens.get('access_token'):
                    access_token = new_tokens['access_token']
                    headers["Authorization"] = f"Bearer {access_token}"
                    response = await _async_get(query_url, headers=headers, params={"q": soql}, timeout=60)
            except Exception:
                pass

        if response.status_code == 200:
            data = response.json()
            records = data.get('records', [])

            # Count statuses
            status_counts = {}
            sample_records = []

            for r in records:
                status = r.get('MtgPlanner_CRM__Status__c', 'NULL/EMPTY')
                status_counts[status] = status_counts.get(status, 0) + 1

                if len(sample_records) < 20:
                    sample_records.append({
                        "Id": r.get("Id"),
                        "Name": r.get("Name"),
                        "Status": r.get("MtgPlanner_CRM__Status__c"),
                        "Borrower": r.get("MtgPlanner_CRM__Borrower_Name__c"),
                        "LastModified": r.get("LastModifiedDate"),
                    })

            return {
                "status": "success",
                "token_source": token_source,
                "total_records": data.get('totalSize', len(records)),
                "records_in_batch": len(records),
                "status_distribution": status_counts,
                "sample_records": sample_records,
                "query_used": soql
            }
        else:
            return {
                "status": "error",
                "token_source": token_source,
                "http_status": response.status_code,
                "response": response.text[:1000]
            }

    except Exception as e:
        logger.error(f"Debug all-statuses failed: {e}")
        return {"status": "error", "error": "Internal server error"}
