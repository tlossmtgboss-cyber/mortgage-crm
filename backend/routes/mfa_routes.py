"""
MFA Routes - Multi-Factor Authentication Endpoints
Enterprise Readiness Check 4.6

Provides endpoints for TOTP-based MFA setup, verification, and management.

Endpoints:
    POST   /api/v1/auth/mfa/setup        - Generate secret + QR code
    POST   /api/v1/auth/mfa/verify-setup  - Confirm setup with first TOTP code
    POST   /api/v1/auth/mfa/verify        - Verify TOTP during login flow
    POST   /api/v1/auth/mfa/backup-codes  - Regenerate backup codes
    DELETE /api/v1/auth/mfa               - Disable MFA (requires TOTP or backup code)
    GET    /api/v1/auth/mfa/status        - Check MFA status
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/auth/mfa", tags=["MFA - Multi-Factor Authentication"])


# =============================================================================
# REQUEST/RESPONSE SCHEMAS
# =============================================================================

class MFASetupResponse(BaseModel):
    """Response from MFA setup containing secret and QR code."""
    secret: str
    provisioning_uri: str
    qr_code_base64: Optional[str] = None
    message: str = "Scan the QR code with your authenticator app, then verify with a token."


class MFAVerifySetupRequest(BaseModel):
    """Request to verify and enable MFA after scanning QR code."""
    token: str  # 6-digit TOTP token


class MFAVerifySetupResponse(BaseModel):
    """Response after MFA verification/enablement."""
    enabled: bool
    backup_codes: Optional[List[str]] = None
    message: str


class MFADisableRequest(BaseModel):
    """Request to disable MFA (requires current token or backup code for security)."""
    token: str  # 6-digit TOTP token or backup code to confirm identity


class MFAStatusResponse(BaseModel):
    """Response for MFA status check."""
    enabled: bool
    enabled_at: Optional[str] = None
    has_backup_codes: bool = False
    backup_codes_remaining: int = 0
    org_mfa_required: bool = False


class MFABackupCodesResponse(BaseModel):
    """Response containing newly generated backup codes."""
    backup_codes: List[str]
    count: int
    message: str = "Save these backup codes in a secure location. They will not be shown again."


# =============================================================================
# RUNTIME IMPORTS TO AVOID CIRCULAR DEPENDENCIES
# =============================================================================

def get_current_user_dep():
    """Get current user dependency at runtime to avoid circular imports."""
    import main
    return main.get_current_user


# =============================================================================
# ENDPOINTS
# =============================================================================

@router.post("/setup", response_model=MFASetupResponse)
async def setup_mfa(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep()),
):
    """
    Generate MFA secret and QR code for initial setup.

    The user should scan the QR code with their authenticator app (Google Authenticator,
    Authy, 1Password, etc.) and then call /verify-setup with the generated token to
    enable MFA.
    """
    from auth.mfa import generate_mfa_secret

    if current_user.mfa_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MFA is already enabled. Disable it first to reconfigure.",
        )

    result = generate_mfa_secret(current_user.email)

    # Store the secret temporarily (not yet enabled)
    current_user.mfa_secret = result["secret"]
    db.commit()

    return MFASetupResponse(
        secret=result["secret"],
        provisioning_uri=result["provisioning_uri"],
        qr_code_base64=result.get("qr_code_base64"),
    )


@router.post("/verify-setup", response_model=MFAVerifySetupResponse)
async def verify_and_enable_mfa(
    request: MFAVerifySetupRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep()),
):
    """
    Verify a TOTP token and enable MFA for the user.

    This should be called after /setup with a valid token from the authenticator app.
    On success, MFA is permanently enabled and backup codes are returned.
    The backup codes are shown only once and must be saved by the user.
    """
    from auth.mfa import verify_mfa_token, generate_backup_codes

    if not current_user.mfa_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MFA setup not initiated. Call /setup first.",
        )

    if current_user.mfa_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MFA is already enabled.",
        )

    # Verify the token
    if not verify_mfa_token(current_user.mfa_secret, request.token):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid MFA token. Please try again with a current code from your authenticator app.",
        )

    # Generate backup codes
    plain_codes, hashed_codes = generate_backup_codes()

    # Enable MFA
    current_user.mfa_enabled = True
    current_user.mfa_enabled_at = datetime.now(timezone.utc)
    current_user.mfa_backup_codes = hashed_codes
    db.commit()

    logger.info(f"MFA enabled for user {current_user.email}")

    return MFAVerifySetupResponse(
        enabled=True,
        backup_codes=plain_codes,
        message="MFA enabled successfully. Save your backup codes in a secure location. They will not be shown again.",
    )


# Keep /verify as an alias for /verify-setup for backward compatibility
@router.post("/verify", response_model=MFAVerifySetupResponse, include_in_schema=False)
async def verify_and_enable_mfa_compat(
    request: MFAVerifySetupRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep()),
):
    """Backward-compatible alias for /verify-setup."""
    return await verify_and_enable_mfa(request, db, current_user)


@router.delete("", status_code=status.HTTP_200_OK)
async def disable_mfa_delete(
    request: MFADisableRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep()),
):
    """
    Disable MFA for the user via DELETE method.

    Requires a valid current TOTP token or backup code to confirm identity before
    disabling. Admin and site_admin users cannot disable MFA (it is mandatory for them).
    Org-enforced MFA also cannot be disabled by individual users.
    """
    return await _disable_mfa_impl(request, db, current_user)


@router.post("/disable")
async def disable_mfa_post(
    request: MFADisableRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep()),
):
    """
    Disable MFA for the user (POST endpoint, kept for backward compatibility).

    Requires a valid current TOTP token or backup code to confirm identity before
    disabling. Admin and site_admin users cannot disable MFA (it is mandatory for them).
    """
    return await _disable_mfa_impl(request, db, current_user)


async def _disable_mfa_impl(request: MFADisableRequest, db: Session, current_user):
    """Shared implementation for MFA disable (DELETE and POST /disable)."""
    from auth.mfa import verify_mfa_token, verify_backup_code

    if not current_user.mfa_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MFA is not currently enabled.",
        )

    # Enterprise Security - Domain 4: Admins cannot disable MFA
    permission_role = getattr(current_user, 'permission_role', '') or ''
    legacy_role = getattr(current_user, 'role', '') or ''
    admin_roles = ['admin', 'site_admin']
    if permission_role.lower() in admin_roles or legacy_role.lower() in admin_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin accounts cannot disable MFA. Multi-factor authentication "
                   "is mandatory for all administrator accounts.",
        )

    # Check org-level MFA enforcement
    org_id = getattr(current_user, 'organization_id', None)
    if org_id:
        try:
            import main
            Organization = main.Organization
            org = db.query(Organization).filter(Organization.id == org_id).first()
            if org and getattr(org, 'mfa_required', False):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Your organization requires MFA for all users. "
                           "Contact your administrator to change this policy.",
                )
        except HTTPException:
            raise
        except Exception as e:
            logger.debug(f"Org MFA enforcement check skipped during disable: {e}")

    # Verify identity with TOTP token or backup code
    token_str = request.token.strip()
    verified = False

    # Try TOTP verification first
    if len(token_str) == 6 and token_str.isdigit():
        verified = verify_mfa_token(current_user.mfa_secret, token_str)

    if not verified and current_user.mfa_backup_codes:
        # Try backup code
        code_index = verify_backup_code(token_str, current_user.mfa_backup_codes)
        if code_index is not None:
            verified = True

    if not verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid MFA token or backup code. Cannot disable MFA without valid authentication.",
        )

    # Disable MFA
    current_user.mfa_enabled = False
    current_user.mfa_secret = None
    current_user.mfa_backup_codes = None
    current_user.mfa_enabled_at = None
    db.commit()

    logger.info(f"MFA disabled for user {current_user.email}")

    return {"enabled": False, "message": "MFA has been disabled."}


@router.post("/backup-codes", response_model=MFABackupCodesResponse)
async def regenerate_backup_codes(
    request: MFAVerifySetupRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep()),
):
    """
    Regenerate backup codes for MFA recovery.

    Requires a valid current TOTP token to confirm identity. This invalidates
    all previous backup codes and generates a fresh set of 10 codes.
    """
    from auth.mfa import verify_mfa_token, generate_backup_codes

    if not current_user.mfa_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MFA is not enabled. Enable MFA first.",
        )

    if not current_user.mfa_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MFA configuration is invalid. Please disable and re-enable MFA.",
        )

    # Verify identity with current TOTP token
    if not verify_mfa_token(current_user.mfa_secret, request.token):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid MFA token. Please provide a valid code from your authenticator app.",
        )

    # Generate new backup codes (replaces all existing ones)
    plain_codes, hashed_codes = generate_backup_codes()

    current_user.mfa_backup_codes = hashed_codes
    db.commit()

    logger.info(f"Backup codes regenerated for user {current_user.email}")

    return MFABackupCodesResponse(
        backup_codes=plain_codes,
        count=len(plain_codes),
    )


@router.get("/status", response_model=MFAStatusResponse)
async def get_mfa_status(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep()),
):
    """
    Check MFA status for the current user.

    Returns whether MFA is enabled, when it was enabled, the number of remaining
    backup codes, and whether the user's organization requires MFA.
    """
    # Check org-level MFA requirement
    org_mfa_required = False
    org_id = getattr(current_user, 'organization_id', None)
    if org_id:
        try:
            import main
            Organization = main.Organization
            org = db.query(Organization).filter(Organization.id == org_id).first()
            if org and getattr(org, 'mfa_required', False):
                org_mfa_required = True
        except Exception as e:
            logger.debug(f"Org MFA check skipped in status: {e}")

    backup_codes = current_user.mfa_backup_codes or []
    return MFAStatusResponse(
        enabled=current_user.mfa_enabled or False,
        enabled_at=current_user.mfa_enabled_at.isoformat() if current_user.mfa_enabled_at else None,
        has_backup_codes=bool(backup_codes),
        backup_codes_remaining=len(backup_codes),
        org_mfa_required=org_mfa_required,
    )


# =============================================================================
# MFA LOGIN VERIFICATION (Enterprise Check 4.6)
# =============================================================================

class MFALoginVerifyRequest(BaseModel):
    """Request to verify MFA token during login."""
    email: str
    mfa_token: str  # 6-digit TOTP token or backup code
    access_token: str  # The MFA-scoped provisional token from /token endpoint


@router.post("/login-verify")
async def verify_mfa_login(
    http_request: Request,
    request: MFALoginVerifyRequest,
    db: Session = Depends(get_db),
):
    """
    Verify MFA token during the login flow.

    After /token returns mfa_required=true, the frontend sends the user's
    TOTP code here along with the MFA-scoped provisional token.
    On success, returns a new fully-authenticated token pair.

    This endpoint accepts either a 6-digit TOTP code or a backup code.
    The provisional token is short-lived (5 min) and only valid for this endpoint.
    """
    # Rate limit MFA verification — 5/minute and 15/hour per IP to prevent brute force
    from routes.auth_routes import (
        _get_real_client_ip, _check_auth_rate_limit_multi, _raise_rate_limit,
        _AUTH_RATE_MAX_MFA_VERIFY, _AUTH_RATE_WINDOW,
        _AUTH_RATE_MAX_MFA_VERIFY_HOUR, _AUTH_RATE_WINDOW_HOUR,
    )
    client_ip = _get_real_client_ip(http_request)
    allowed, retry_after = _check_auth_rate_limit_multi(client_ip, [
        (_AUTH_RATE_MAX_MFA_VERIFY, _AUTH_RATE_WINDOW, "mfa_verify"),
        (_AUTH_RATE_MAX_MFA_VERIFY_HOUR, _AUTH_RATE_WINDOW_HOUR, "mfa_verify_hour"),
    ])
    if not allowed:
        logger.warning(f"MFA verify rate limit exceeded for {client_ip}")
        _raise_rate_limit(retry_after, "Too many MFA verification attempts. Please try again later.")

    from auth.mfa import verify_mfa_token, verify_backup_code

    # Lazy imports for auth functions
    import main
    User = main.User

    # Validate the MFA-scoped provisional token using centralized auth
    try:
        from auth.tokens import decode_token
        payload = decode_token(request.access_token)
        if not payload:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired MFA session token",
            )
        token_scope = payload.get("scope", "")
        token_email = payload.get("sub", "")
        if token_scope != "mfa_verify" or token_email != request.email:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired MFA session token",
            )
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired MFA session token",
        )

    user = db.query(User).filter(User.email == request.email).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    if not user.mfa_enabled or not user.mfa_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MFA is not enabled for this account.",
        )

    # Try TOTP verification first
    token_str = request.mfa_token.strip()
    verified = False

    if len(token_str) == 6 and token_str.isdigit():
        # Looks like a TOTP code
        verified = verify_mfa_token(user.mfa_secret, token_str)

    if not verified:
        # Try backup code
        if user.mfa_backup_codes:
            code_index = verify_backup_code(token_str, user.mfa_backup_codes)
            if code_index is not None:
                # Remove used backup code
                codes = list(user.mfa_backup_codes)
                codes.pop(code_index)
                user.mfa_backup_codes = codes
                db.flush()
                verified = True
                logger.info(f"MFA backup code used for user {user.email} (codes remaining: {len(codes)})")

    if not verified:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid MFA token. Please try again.",
        )

    # MFA verified - issue fully authenticated tokens
    tenant_id = str(user.organization_id) if user.organization_id else None
    access_token = main.create_access_token(
        data={"sub": user.email, "mfa_verified": True},
        user_id=user.id,
        tenant_id=tenant_id,
    )
    refresh_token = main.create_refresh_token(
        data={"sub": user.email},
        user_id=user.id,
    )

    # Update last activity
    user.last_activity_at = datetime.now(timezone.utc)
    db.commit()

    logger.info(f"MFA login verified for user {user.email}")

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "mfa_verified": True,
        "user": {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role,
            "permission_role": user.permission_role,
            "onboarding_completed": user.onboarding_completed,
        },
    }
