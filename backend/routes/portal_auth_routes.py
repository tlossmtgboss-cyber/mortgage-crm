"""
Portal Authentication Routes
Perennia AI - Mortgage CRM

Magic link authentication for the borrower portal.
Handles:
- Magic link generation and sending
- Token verification and session creation
- Session management and refresh
- Logout and token revocation
"""

import os
import secrets
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, Request, BackgroundTasks
from fastapi.responses import RedirectResponse, JSONResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/auth/portal", tags=["Portal Authentication"])


# =============================================================================
# DEPENDENCY INJECTION
# =============================================================================

from db import get_db

_email_service = None


def set_dependencies(get_db_func, email_service=None):
    """Set dependencies from main.py."""
    global _email_service
    _email_service = email_service
    logger.info("Portal Auth routes dependencies set")


# =============================================================================
# CONFIGURATION
# =============================================================================

PORTAL_BASE_URL = os.getenv('PORTAL_BASE_URL', 'http://localhost:3000/portal')
MAGIC_LINK_EXPIRY_HOURS = int(os.getenv('MAGIC_LINK_EXPIRY_HOURS', '1'))
SESSION_EXPIRY_HOURS = int(os.getenv('PORTAL_SESSION_EXPIRY_HOURS', '24'))
SESSION_COOKIE_NAME = 'perennia_portal_session'
SESSION_COOKIE_DOMAIN = os.getenv('SESSION_COOKIE_DOMAIN', None)
SESSION_COOKIE_SECURE = os.getenv('ENVIRONMENT', 'development') == 'production'


def _safe_portal_redirect(redirect: Optional[str], workspace_slug: str) -> str:
    """Validate redirect URL — only allow relative /portal/ paths."""
    default = f"/portal/{workspace_slug}"
    if not redirect:
        return default
    # Block absolute URLs, protocol-relative, and special chars
    if redirect.startswith("//") or redirect.startswith("http") or "@" in redirect or "\\" in redirect:
        return default
    # Only allow paths under /portal/
    if redirect.startswith("/portal/"):
        return redirect
    return default


# =============================================================================
# REQUEST/RESPONSE MODELS
# =============================================================================

class SendMagicLinkRequest(BaseModel):
    """Request to send a magic link."""
    workspace_id: int
    email: EmailStr
    redirect_path: Optional[str] = None


class SendMagicLinkResponse(BaseModel):
    """Response after sending magic link."""
    success: bool
    message: str
    expires_at: str
    email_masked: str


class VerifyTokenRequest(BaseModel):
    """Request to verify a magic link token."""
    token: str


class VerifyTokenResponse(BaseModel):
    """Response after verifying token."""
    valid: bool
    workspace_id: Optional[int] = None
    workspace_slug: Optional[str] = None
    session_token: Optional[str] = None
    session_expires_at: Optional[str] = None
    borrower: Optional[Dict[str, Any]] = None
    redirect_url: Optional[str] = None


class SessionInfo(BaseModel):
    """Current session information."""
    valid: bool
    workspace_id: Optional[int] = None
    workspace_slug: Optional[str] = None
    contact_id: Optional[int] = None
    borrower_name: Optional[str] = None
    expires_at: Optional[str] = None
    permissions: list = []


class RefreshSessionResponse(BaseModel):
    """Response after session refresh."""
    success: bool
    new_expires_at: str


# =============================================================================
# MAGIC LINK GENERATION
# =============================================================================

@router.post("/send-link", response_model=SendMagicLinkResponse)
async def send_magic_link(
    request: SendMagicLinkRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Generate and send a magic link to the borrower's email.

    The magic link allows passwordless authentication to the borrower portal.
    Links expire after MAGIC_LINK_EXPIRY_HOURS (default 72 hours).
    """
    # Get workspace and verify email belongs to a contact
    workspace = db.execute(text("""
        SELECT w.id, w.slug, w.display_name, w.organization_id,
               c.id as contact_id, c.first_name, c.last_name
        FROM purl_workspaces w
        JOIN purl_contacts c ON c.workspace_id = w.id
        WHERE w.id = :workspace_id
          AND LOWER(c.email) = LOWER(:email)
          AND c.is_primary = true
    """), {
        "workspace_id": request.workspace_id,
        "email": request.email
    }).fetchone()

    if not workspace:
        # Don't reveal if email exists or not for security
        logger.warning(f"Magic link request for non-existent workspace/email: {request.workspace_id}")
        # Still return success to prevent email enumeration
        return SendMagicLinkResponse(
            success=True,
            message="If this email is associated with an account, a magic link has been sent.",
            expires_at=(datetime.now(timezone.utc) + timedelta(hours=MAGIC_LINK_EXPIRY_HOURS)).isoformat(),
            email_masked=_mask_email(request.email)
        )

    # Generate secure token
    token = secrets.token_urlsafe(48)  # 64 characters, URL-safe
    expires_at = datetime.now(timezone.utc) + timedelta(hours=MAGIC_LINK_EXPIRY_HOURS)

    try:
        # Invalidate any existing tokens for this contact
        db.execute(text("""
            UPDATE purl_access_tokens
            SET revoked_at = NOW()
            WHERE workspace_id = :workspace_id
              AND contact_id = :contact_id
              AND scope = 'magic_link'
              AND revoked_at IS NULL
        """), {
            "workspace_id": request.workspace_id,
            "contact_id": workspace[4]
        })

        # Create new token
        db.execute(text("""
            INSERT INTO purl_access_tokens (
                organization_id, workspace_id, contact_id,
                name, scope, token_value, token_prefix,
                expires_at, created_at, updated_at
            ) VALUES (
                :org_id, :workspace_id, :contact_id,
                'Magic Link', 'magic_link', :token, :prefix,
                :expires_at, NOW(), NOW()
            )
        """), {
            "org_id": workspace[3],
            "workspace_id": request.workspace_id,
            "contact_id": workspace[4],
            "token": token,
            "prefix": token[:8],
            "expires_at": expires_at
        })

        # Log the event
        db.execute(text("""
            INSERT INTO purl_audit_log (
                organization_id, workspace_id, action, actor_type,
                metadata, created_at
            ) VALUES (
                :org_id, :workspace_id, 'magic_link_sent', 'system',
                :metadata, NOW()
            )
        """), {
            "org_id": workspace[3],
            "workspace_id": request.workspace_id,
            "metadata": {
                "email": request.email,
                "contact_id": workspace[4]
            }
        })

        db.commit()

        # Build magic link URL
        redirect_path = request.redirect_path or ""
        magic_link = f"{PORTAL_BASE_URL}/auth/verify?token={token}"
        if redirect_path:
            magic_link += f"&redirect={redirect_path}"

        # Send email (in background)
        if _email_service:
            background_tasks.add_task(
                _send_magic_link_email,
                email=request.email,
                first_name=workspace[5],
                magic_link=magic_link,
                expires_at=expires_at
            )
        else:
            logger.info(f"Magic link generated (email service not configured): {magic_link}")

        return SendMagicLinkResponse(
            success=True,
            message="Magic link sent successfully",
            expires_at=expires_at.isoformat(),
            email_masked=_mask_email(request.email)
        )

    except Exception as e:
        db.rollback()
        logger.error(f"Failed to generate magic link: {e}")
        raise HTTPException(status_code=500, detail="Failed to send magic link")


async def _send_magic_link_email(email: str, first_name: str, magic_link: str, expires_at: datetime):
    """Send magic link email (placeholder for actual email service)."""
    if _email_service:
        try:
            await _email_service.send_email(
                to=email,
                subject="Access Your Loan Portal",
                template="magic_link",
                data={
                    "first_name": first_name,
                    "magic_link": magic_link,
                    "expires_at": expires_at.strftime("%B %d, %Y at %I:%M %p"),
                }
            )
        except Exception as e:
            logger.error(f"Failed to send magic link email: {e}")


def _mask_email(email: str) -> str:
    """Mask email for display (e.g., j***@example.com)."""
    parts = email.split('@')
    if len(parts) != 2:
        return '***'
    local = parts[0]
    domain = parts[1]
    if len(local) <= 2:
        masked_local = local[0] + '***'
    else:
        masked_local = local[0] + '***' + local[-1]
    return f"{masked_local}@{domain}"


# =============================================================================
# TOKEN VERIFICATION
# =============================================================================

@router.get("/verify")
async def verify_magic_link(
    token: str = Query(..., min_length=32),
    redirect: Optional[str] = Query(None),
    response: Response = None,
    db: Session = Depends(get_db)
):
    """
    Verify a magic link token and create a session.

    If valid:
    1. Creates a session token
    2. Sets session cookie
    3. Redirects to portal (or returns JSON if Accept: application/json)
    """
    # Look up token
    token_record = db.execute(text("""
        SELECT t.id, t.workspace_id, t.contact_id, t.expires_at, t.revoked_at,
               w.slug, w.display_name, w.organization_id,
               c.first_name, c.last_name, c.email
        FROM purl_access_tokens t
        JOIN purl_workspaces w ON w.id = t.workspace_id
        JOIN purl_contacts c ON c.id = t.contact_id
        WHERE t.token_value = :token
          AND t.scope = 'magic_link'
    """), {"token": token}).fetchone()

    if not token_record:
        raise HTTPException(status_code=401, detail="Invalid or expired link")

    # Check if expired or revoked
    if token_record[4]:  # revoked_at
        raise HTTPException(status_code=401, detail="This link has already been used")

    if token_record[3] < datetime.now(timezone.utc):  # expires_at
        raise HTTPException(status_code=401, detail="This link has expired")

    token_id = token_record[0]
    workspace_id = token_record[1]
    contact_id = token_record[2]
    workspace_slug = token_record[5]
    org_id = token_record[7]

    try:
        # Mark magic link token as used
        db.execute(text("""
            UPDATE purl_access_tokens
            SET revoked_at = NOW(), use_count = use_count + 1
            WHERE id = :token_id
        """), {"token_id": token_id})

        # Create session token
        session_token = secrets.token_urlsafe(48)
        session_expires = datetime.now(timezone.utc) + timedelta(hours=SESSION_EXPIRY_HOURS)

        db.execute(text("""
            INSERT INTO purl_access_tokens (
                organization_id, workspace_id, contact_id,
                name, scope, token_value, token_prefix,
                expires_at, created_at, updated_at
            ) VALUES (
                :org_id, :workspace_id, :contact_id,
                'Portal Session', 'full', :token, :prefix,
                :expires_at, NOW(), NOW()
            )
        """), {
            "org_id": org_id,
            "workspace_id": workspace_id,
            "contact_id": contact_id,
            "token": session_token,
            "prefix": session_token[:8],
            "expires_at": session_expires
        })

        # Log login
        db.execute(text("""
            INSERT INTO purl_audit_log (
                organization_id, workspace_id, action, actor_type, actor_id,
                metadata, created_at
            ) VALUES (
                :org_id, :workspace_id, 'portal_login', 'contact', :contact_id,
                :metadata, NOW()
            )
        """), {
            "org_id": org_id,
            "workspace_id": workspace_id,
            "contact_id": contact_id,
            "metadata": {"method": "magic_link"}
        })

        db.commit()

        # Build response
        result = VerifyTokenResponse(
            valid=True,
            workspace_id=workspace_id,
            workspace_slug=workspace_slug,
            session_token=session_token,
            session_expires_at=session_expires.isoformat(),
            borrower={
                "contact_id": contact_id,
                "first_name": token_record[8],
                "last_name": token_record[9],
                "email": token_record[10],
            },
            redirect_url=_safe_portal_redirect(redirect, workspace_slug)
        )

        # Set session cookie
        response = JSONResponse(content=result.dict())
        response.set_cookie(
            key=SESSION_COOKIE_NAME,
            value=session_token,
            httponly=True,
            secure=SESSION_COOKIE_SECURE,
            samesite="lax",
            max_age=SESSION_EXPIRY_HOURS * 3600,
            domain=SESSION_COOKIE_DOMAIN
        )

        return response

    except Exception as e:
        db.rollback()
        logger.error(f"Failed to verify magic link: {e}")
        raise HTTPException(status_code=500, detail="Failed to verify link")


@router.post("/verify", response_model=VerifyTokenResponse)
async def verify_magic_link_post(
    request: VerifyTokenRequest,
    response: Response,
    db: Session = Depends(get_db)
):
    """POST version of verify for API clients."""
    return await verify_magic_link(
        token=request.token,
        redirect=None,
        response=response,
        db=db
    )


# =============================================================================
# SESSION MANAGEMENT
# =============================================================================

@router.get("/session", response_model=SessionInfo)
async def get_session_info(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Get current session information.

    Uses session cookie or Authorization header.
    """
    session_token = _extract_session_token(request)

    if not session_token:
        return SessionInfo(valid=False)

    # Look up session
    session = db.execute(text("""
        SELECT t.id, t.workspace_id, t.contact_id, t.expires_at, t.revoked_at,
               w.slug, c.first_name, c.last_name
        FROM purl_access_tokens t
        JOIN purl_workspaces w ON w.id = t.workspace_id
        JOIN purl_contacts c ON c.id = t.contact_id
        WHERE t.token_value = :token
          AND t.scope = 'full'
          AND t.revoked_at IS NULL
          AND t.expires_at > NOW()
    """), {"token": session_token}).fetchone()

    if not session:
        return SessionInfo(valid=False)

    # Update last used
    db.execute(text("""
        UPDATE purl_access_tokens
        SET last_used_at = NOW(), use_count = use_count + 1
        WHERE id = :token_id
    """), {"token_id": session[0]})
    db.commit()

    return SessionInfo(
        valid=True,
        workspace_id=session[1],
        workspace_slug=session[5],
        contact_id=session[2],
        borrower_name=f"{session[6]} {session[7]}",
        expires_at=session[3].isoformat(),
        permissions=["read", "write", "upload"]
    )


@router.post("/refresh", response_model=RefreshSessionResponse)
async def refresh_session(
    request: Request,
    response: Response,
    db: Session = Depends(get_db)
):
    """
    Refresh the current session, extending its expiry.

    Only works if session is still valid.
    """
    session_token = _extract_session_token(request)

    if not session_token:
        raise HTTPException(status_code=401, detail="No session found")

    # Look up and extend session
    session = db.execute(text("""
        SELECT id, expires_at
        FROM purl_access_tokens
        WHERE token_value = :token
          AND scope = 'full'
          AND revoked_at IS NULL
          AND expires_at > NOW()
    """), {"token": session_token}).fetchone()

    if not session:
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    new_expires = datetime.now(timezone.utc) + timedelta(hours=SESSION_EXPIRY_HOURS)

    db.execute(text("""
        UPDATE purl_access_tokens
        SET expires_at = :new_expires, updated_at = NOW()
        WHERE id = :token_id
    """), {"token_id": session[0], "new_expires": new_expires})
    db.commit()

    # Update cookie
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_token,
        httponly=True,
        secure=SESSION_COOKIE_SECURE,
        samesite="lax",
        max_age=SESSION_EXPIRY_HOURS * 3600,
        domain=SESSION_COOKIE_DOMAIN
    )

    return RefreshSessionResponse(
        success=True,
        new_expires_at=new_expires.isoformat()
    )


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db)
):
    """
    Logout and invalidate the current session.
    """
    session_token = _extract_session_token(request)

    if session_token:
        # Revoke session token
        result = db.execute(text("""
            UPDATE purl_access_tokens
            SET revoked_at = NOW()
            WHERE token_value = :token
              AND scope = 'full'
              AND revoked_at IS NULL
            RETURNING workspace_id, contact_id
        """), {"token": session_token}).fetchone()

        if result:
            # Log logout
            db.execute(text("""
                INSERT INTO purl_audit_log (
                    organization_id, workspace_id, action, actor_type, actor_id,
                    created_at
                ) VALUES (
                    (SELECT organization_id FROM purl_workspaces WHERE id = :workspace_id),
                    :workspace_id, 'portal_logout', 'contact', :contact_id,
                    NOW()
                )
            """), {
                "workspace_id": result[0],
                "contact_id": result[1]
            })

        db.commit()

    # Clear cookie
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        domain=SESSION_COOKIE_DOMAIN
    )

    return {"success": True, "message": "Logged out successfully"}


def _extract_session_token(request: Request) -> Optional[str]:
    """Extract session token from cookie or Authorization header."""
    # Check cookie first
    session_token = request.cookies.get(SESSION_COOKIE_NAME)
    if session_token:
        return session_token

    # Check Authorization header
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:]

    return None


# =============================================================================
# TOKEN VALIDATION MIDDLEWARE HELPER
# =============================================================================

async def validate_portal_session(
    request: Request,
    db: Session
) -> Optional[Dict[str, Any]]:
    """
    Validate portal session and return session info.

    Use this as a dependency in protected endpoints.
    Returns None if session is invalid.
    """
    session_token = _extract_session_token(request)

    if not session_token:
        return None

    session = db.execute(text("""
        SELECT t.id, t.workspace_id, t.contact_id, t.scope, t.expires_at,
               w.slug, w.organization_id,
               c.first_name, c.last_name, c.email
        FROM purl_access_tokens t
        JOIN purl_workspaces w ON w.id = t.workspace_id
        JOIN purl_contacts c ON c.id = t.contact_id
        WHERE t.token_value = :token
          AND t.revoked_at IS NULL
          AND t.expires_at > NOW()
    """), {"token": session_token}).fetchone()

    if not session:
        return None

    # Update last used (fire and forget)
    db.execute(text("""
        UPDATE purl_access_tokens
        SET last_used_at = NOW(), use_count = use_count + 1
        WHERE id = :token_id
    """), {"token_id": session[0]})

    return {
        "token_id": session[0],
        "workspace_id": session[1],
        "contact_id": session[2],
        "scope": session[3],
        "expires_at": session[4],
        "workspace_slug": session[5],
        "organization_id": session[6],
        "borrower": {
            "first_name": session[7],
            "last_name": session[8],
            "email": session[9],
        }
    }


# =============================================================================
# HEALTH CHECK
# =============================================================================

@router.get("/health")
async def portal_auth_health():
    """Portal auth health check."""
    return {
        "status": "healthy",
        "service": "portal_auth",
        "magic_link_expiry_hours": MAGIC_LINK_EXPIRY_HOURS,
        "session_expiry_hours": SESSION_EXPIRY_HOURS,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
