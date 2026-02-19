"""
MFA Routes - Multi-Factor Authentication Endpoints
Enterprise Readiness Check 4.6

Provides endpoints for TOTP-based MFA setup, verification, and management.
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
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


class MFAVerifyRequest(BaseModel):
    """Request to verify and enable MFA."""
    token: str  # 6-digit TOTP token


class MFAVerifyResponse(BaseModel):
    """Response after MFA verification/enablement."""
    enabled: bool
    backup_codes: Optional[list] = None
    message: str


class MFADisableRequest(BaseModel):
    """Request to disable MFA (requires current token for security)."""
    token: str  # 6-digit TOTP token to confirm identity


class MFAStatusResponse(BaseModel):
    """Response for MFA status check."""
    enabled: bool
    enabled_at: Optional[str] = None
    has_backup_codes: bool = False


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
    Authy, 1Password, etc.) and then call /verify with the generated token to enable MFA.
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


@router.post("/verify", response_model=MFAVerifyResponse)
async def verify_and_enable_mfa(
    request: MFAVerifyRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep()),
):
    """
    Verify a TOTP token and enable MFA for the user.

    This should be called after /setup with a valid token from the authenticator app.
    On success, MFA is permanently enabled and backup codes are returned.
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

    return MFAVerifyResponse(
        enabled=True,
        backup_codes=plain_codes,
        message="MFA enabled successfully. Save your backup codes in a secure location. They will not be shown again.",
    )


@router.post("/disable")
async def disable_mfa(
    request: MFADisableRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep()),
):
    """
    Disable MFA for the user.

    Requires a valid current TOTP token to confirm identity before disabling.
    """
    from auth.mfa import verify_mfa_token

    if not current_user.mfa_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MFA is not currently enabled.",
        )

    # Verify current token before disabling
    if not verify_mfa_token(current_user.mfa_secret, request.token):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid MFA token. Cannot disable MFA without valid authentication.",
        )

    # Disable MFA
    current_user.mfa_enabled = False
    current_user.mfa_secret = None
    current_user.mfa_backup_codes = None
    current_user.mfa_enabled_at = None
    db.commit()

    logger.info(f"MFA disabled for user {current_user.email}")

    return {"enabled": False, "message": "MFA has been disabled."}


@router.get("/status", response_model=MFAStatusResponse)
async def get_mfa_status(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep()),
):
    """
    Check if MFA is enabled for the current user.
    """
    return MFAStatusResponse(
        enabled=current_user.mfa_enabled or False,
        enabled_at=current_user.mfa_enabled_at.isoformat() if current_user.mfa_enabled_at else None,
        has_backup_codes=bool(current_user.mfa_backup_codes),
    )
