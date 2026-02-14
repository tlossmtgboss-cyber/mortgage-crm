"""
Authentication Routes
Perennia AI - Mortgage CRM

Handles all authentication-related endpoints:
- /token (login)
- /token/refresh
- /logout
- /logout/all
- Password reset (forgot-password, reset-password)
- Admin password reset
- Public registration
- Promo code management
- Push notification token registration
- Admin setup utilities
"""

import os
import re
import secrets
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

import time
from collections import defaultdict
from fastapi import APIRouter, Depends, HTTPException, status, Body, Query, Request
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from sqlalchemy import text, func
import jwt
from jwt import PyJWTError as JWTError

from db import get_db

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Authentication"])

# In-memory rate limiter for auth endpoints
_auth_rate_store: dict = defaultdict(list)
_AUTH_RATE_WINDOW = 60  # seconds
_AUTH_RATE_MAX_LOGIN = 5  # max login attempts per window per IP
_AUTH_RATE_MAX_RESET = 3  # max password reset requests per window per IP
_AUTH_RATE_MAX_REGISTER = 3  # max registration attempts per window per IP
_AUTH_RATE_MAX_KEYS = 10000  # max tracked IPs before forced cleanup


def _get_real_client_ip(request: Request) -> str:
    """Get real client IP, accounting for reverse proxies (Railway, etc.)."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip
    return request.client.host if request.client else "unknown"


def _check_auth_rate_limit(client_ip: str, max_requests: int) -> bool:
    """Check if client IP is within auth rate limit. Returns True if allowed."""
    now = time.time()
    key = f"auth:{client_ip}"
    _auth_rate_store[key] = [t for t in _auth_rate_store[key] if now - t < _AUTH_RATE_WINDOW]
    if len(_auth_rate_store) > _AUTH_RATE_MAX_KEYS:
        stale = [k for k, v in _auth_rate_store.items() if not v or now - v[-1] > _AUTH_RATE_WINDOW]
        for k in stale:
            del _auth_rate_store[k]
    if len(_auth_rate_store[key]) >= max_requests:
        return False
    _auth_rate_store[key].append(now)
    return True


# =============================================================================
# RUNTIME IMPORTS TO AVOID CIRCULAR DEPENDENCIES
# =============================================================================

def get_models():
    """Get models at runtime to avoid circular imports"""
    import main
    return {
        'User': main.User,
        'Organization': main.Organization,
        'PromoCode': main.PromoCode,
        'Subscription': main.Subscription,
        'SubscriptionPlan': main.SubscriptionPlan,
    }


def get_current_user_dep():
    """Get current user dependency at runtime"""
    import main
    return main.get_current_user


def get_oauth2_scheme():
    """Get OAuth2 scheme at runtime"""
    import main
    return main.oauth2_scheme


def get_auth_functions():
    """Get auth functions at runtime"""
    import main
    return {
        'create_access_token': main.create_access_token,
        'create_refresh_token': main.create_refresh_token,
        'verify_password': main.verify_password,
        'get_password_hash': main.get_password_hash,
    }


def get_auth_config():
    """Get auth configuration at runtime"""
    import main
    return {
        'SECRET_KEY': main.SECRET_KEY,
        'ALGORITHM': main.ALGORITHM,
        'ACCESS_TOKEN_EXPIRE_MINUTES': main.ACCESS_TOKEN_EXPIRE_MINUTES,
        '_USE_SECURE_TOKENS': main._USE_SECURE_TOKENS,
        'token_blacklist': getattr(main, 'token_blacklist', None),
        '_verify_secure_token': getattr(main, '_verify_secure_token', None),
        'TokenType': getattr(main, 'TokenType', None),
    }


def get_security_stats():
    """Get security stats at runtime"""
    import main
    return getattr(main, 'security_stats', None)


# =============================================================================
# PASSWORD RESET TOKEN CONFIGURATION
# =============================================================================

PASSWORD_RESET_TOKEN_EXPIRE_MINUTES = 60  # 1 hour


def create_password_reset_token(email: str) -> str:
    """Create a JWT token for password reset with issued-at for single-use enforcement"""
    config = get_auth_config()
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=PASSWORD_RESET_TOKEN_EXPIRE_MINUTES)
    to_encode = {
        "sub": email,
        "exp": expire,
        "iat": now,
        "type": "password_reset"
    }
    return jwt.encode(to_encode, config['SECRET_KEY'], algorithm=config['ALGORITHM'])


def verify_password_reset_token(token: str) -> Optional[dict]:
    """Verify password reset token and return payload dict with 'sub' and 'iat' if valid"""
    config = get_auth_config()
    try:
        payload = jwt.decode(token, config['SECRET_KEY'], algorithms=[config['ALGORITHM']], options={"verify_aud": False})
        if payload.get("type") != "password_reset":
            return None
        email = payload.get("sub")
        iat = payload.get("iat")
        if not email:
            return None
        return {"email": email, "iat": iat}
    except jwt.ExpiredSignatureError:
        return None
    except jwt.JWTError:
        return None


# =============================================================================
# PYDANTIC SCHEMAS
# =============================================================================

class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


class AdminPasswordResetRequest(BaseModel):
    email: str
    new_password: str
    admin_key: str


class RegisterRequest(BaseModel):
    """Request schema for public registration"""
    full_name: str
    email: EmailStr
    password: str
    company_name: Optional[str] = None
    phone: Optional[str] = None
    plan: Optional[str] = "professional"
    promo_code: Optional[str] = None


class ValidatePromoCodeRequest(BaseModel):
    code: str


class CreatePromoCodeRequest(BaseModel):
    code: str
    description: Optional[str] = None
    discount_type: str = "percentage"  # percentage, fixed, trial_extension, free_access
    discount_value: float = 0
    trial_days: int = 0
    max_uses: Optional[int] = None


class UpdatePromoCodeRequest(BaseModel):
    description: Optional[str] = None
    discount_type: Optional[str] = None
    discount_value: Optional[float] = None
    trial_days: Optional[int] = None
    max_uses: Optional[int] = None
    is_active: Optional[bool] = None


class PushRegisterRequest(BaseModel):
    device_token: str
    platform: str = "ios"


# =============================================================================
# AUTH ROUTES
# =============================================================================

@router.post("/token")
async def login(http_request: Request, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    # Rate limit login attempts
    client_ip = _get_real_client_ip(http_request)
    if not _check_auth_rate_limit(client_ip, _AUTH_RATE_MAX_LOGIN):
        logger.warning(f"Login rate limit exceeded for {client_ip}")
        raise HTTPException(status_code=429, detail="Too many login attempts. Please try again later.")

    try:
        models = get_models()
        User = models['User']
        auth_funcs = get_auth_functions()
        config = get_auth_config()

        user = db.query(User).filter(User.email == form_data.username).first()

        # Check user exists and has a valid hashed_password before verification
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if not user.hashed_password:
            logger.warning(f"User {form_data.username} has no password set")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if not auth_funcs['verify_password'](form_data.password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Update last_activity_at on successful login
        user.last_activity_at = datetime.now(timezone.utc)
        db.commit()

        # Create tokens with user context for proper security
        tenant_id = str(user.organization_id) if hasattr(user, 'organization_id') and user.organization_id else None
        access_token = auth_funcs['create_access_token'](
            data={"sub": user.email},
            user_id=user.id,
            tenant_id=tenant_id
        )
        refresh_token = auth_funcs['create_refresh_token'](
            data={"sub": user.email},
            user_id=user.id
        )

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": config['ACCESS_TOKEN_EXPIRE_MINUTES'] * 60,  # seconds
            "user": {
                "id": user.id,
                "email": user.email,
                "full_name": user.full_name,
                "role": user.role,
                "permission_role": user.permission_role,
                "onboarding_completed": user.onboarding_completed
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error for {form_data.username}: {type(e).__name__}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Login service temporarily unavailable. Please try again.",
        )


@router.post("/token/refresh")
async def refresh_access_token(
    refresh_token: str = Body(..., embed=True),
    db: Session = Depends(get_db)
):
    """
    Exchange a refresh token for a new access token.

    This allows clients to get new access tokens without re-authenticating.
    The refresh token must be valid and not blacklisted.
    """
    models = get_models()
    User = models['User']
    auth_funcs = get_auth_functions()
    config = get_auth_config()

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired refresh token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if config['_USE_SECURE_TOKENS']:
        # Verify refresh token with blacklist check
        TokenType = config['TokenType']
        _verify_secure_token = config['_verify_secure_token']
        token_data = _verify_secure_token(refresh_token, expected_type=TokenType.REFRESH)
        if not token_data:
            raise credentials_exception

        # Get user from token
        user = db.query(User).filter(User.email == token_data.sub).first()
        if not user:
            raise credentials_exception

        # Create new access token
        tenant_id = str(user.organization_id) if hasattr(user, 'organization_id') and user.organization_id else None
        new_access_token = auth_funcs['create_access_token'](
            data={"sub": user.email},
            user_id=user.id,
            tenant_id=tenant_id
        )

        return {
            "access_token": new_access_token,
            "token_type": "bearer",
            "expires_in": config['ACCESS_TOKEN_EXPIRE_MINUTES'] * 60,
        }
    else:
        # Legacy fallback
        try:
            payload = jwt.decode(refresh_token, config['SECRET_KEY'], algorithms=[config['ALGORITHM']], options={"verify_aud": False})
            if payload.get("type") != "refresh":
                raise credentials_exception

            email = payload.get("sub")
            if not email:
                raise credentials_exception

            user = db.query(User).filter(User.email == email).first()
            if not user:
                raise credentials_exception

            new_access_token = auth_funcs['create_access_token'](data={"sub": user.email})
            return {
                "access_token": new_access_token,
                "token_type": "bearer",
                "expires_in": config['ACCESS_TOKEN_EXPIRE_MINUTES'] * 60,
            }
        except JWTError:
            raise credentials_exception


# Note: Logout endpoints require token and current_user dependencies
# These are created as factory functions and added in main.py after import
# See create_logout_routes() below

def create_logout_routes(app, oauth2_scheme, get_current_user):
    """
    Create logout routes with proper dependencies.
    Called from main.py after importing the router.
    """
    from fastapi import Depends

    @app.post("/logout")
    async def logout(
        token: str = Depends(oauth2_scheme),
        current_user = Depends(get_current_user),
    ):
        """
        Logout the current user by blacklisting their token.

        This immediately invalidates the token, preventing reuse.
        """
        config = get_auth_config()
        token_blacklist = config['token_blacklist']
        _USE_SECURE_TOKENS = config['_USE_SECURE_TOKENS']

        if _USE_SECURE_TOKENS and token_blacklist and token_blacklist._enabled:
            # Add token to blacklist
            token_blacklist.add(token, reason="user_logout")
            logger.info(f"User ID {current_user.id} logged out, token blacklisted")
            return {"message": "Successfully logged out"}
        else:
            # Without Redis, we can't truly invalidate the token
            # Client should discard the token
            logger.info(f"User ID {current_user.id} logged out (token not blacklisted - no Redis)")
            return {"message": "Successfully logged out (token should be discarded by client)"}

    @app.post("/logout/all")
    async def logout_all_sessions(
        current_user = Depends(get_current_user),
    ):
        """
        Logout all sessions for the current user.

        This revokes all tokens for the user, forcing re-authentication on all devices.
        """
        config = get_auth_config()
        token_blacklist = config['token_blacklist']
        _USE_SECURE_TOKENS = config['_USE_SECURE_TOKENS']

        if _USE_SECURE_TOKENS and token_blacklist and token_blacklist._enabled:
            token_blacklist.revoke_all_for_user(current_user.id)
            logger.info(f"All sessions revoked for user ID {current_user.id}")
            return {"message": "All sessions have been logged out"}
        else:
            return {"message": "Session revocation not available (no Redis)"}


# =============================================================================
# PASSWORD RESET ROUTES
# =============================================================================

@router.post("/api/v1/auth/forgot-password")
async def forgot_password(http_request: Request, request: ForgotPasswordRequest, db: Session = Depends(get_db)):
    """
    Request a password reset email.
    Always returns success to prevent email enumeration attacks.
    """
    # Rate limit password reset requests
    client_ip = _get_real_client_ip(http_request)
    if not _check_auth_rate_limit(client_ip, _AUTH_RATE_MAX_RESET):
        logger.warning(f"Forgot-password rate limit exceeded for {client_ip}")
        raise HTTPException(status_code=429, detail="Too many requests. Please try again later.")

    try:
        models = get_models()
        User = models['User']

        # Check if user exists
        user = db.query(User).filter(User.email == request.email).first()

        if user:
            # Generate reset token
            reset_token = create_password_reset_token(request.email)

            # Build reset URL
            frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
            reset_url = f"{frontend_url}/reset-password?token={reset_token}"

            # Send email
            try:
                from email_service import EmailService
                email_service = EmailService()

                # Log email service configuration status
                logger.info(f"Email service config - SendGrid: {email_service.use_sendgrid}, SMTP User: {bool(email_service.smtp_user)}")

                html_body = f"""
                <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                    <h2 style="color: #218D8D;">Reset Your Password</h2>
                    <p>Hi {user.full_name or 'there'},</p>
                    <p>We received a request to reset your password. Click the button below to create a new password:</p>

                    <!-- Outlook-compatible button using table -->
                    <table cellpadding="0" cellspacing="0" border="0" style="margin: 30px auto;">
                        <tr>
                            <td align="center" bgcolor="#218D8D" style="border-radius: 8px;">
                                <a href="{reset_url}" target="_blank" style="display: inline-block; padding: 14px 32px; font-family: Arial, sans-serif; font-size: 16px; color: #ffffff; text-decoration: none; font-weight: bold; border-radius: 8px;">
                                    Reset Password
                                </a>
                            </td>
                        </tr>
                    </table>

                    <p style="color: #666; font-size: 14px;">
                        This link will expire in 1 hour. If you didn't request this, you can safely ignore this email.
                    </p>
                    <p style="color: #666; font-size: 14px;">
                        If the button doesn't work, copy and paste this link into your browser:<br>
                        <a href="{reset_url}" style="color: #218D8D; word-break: break-all;">{reset_url}</a>
                    </p>
                    <hr style="border: none; border-top: 1px solid #eee; margin: 30px 0;">
                    <p style="color: #999; font-size: 12px;">
                        Perennia AI - Mortgage CRM
                    </p>
                </div>
                """

                email_sent = email_service.send_html_email(
                    to_email=request.email,
                    subject="Reset Your Password - Perennia AI",
                    html_body=html_body,
                    plain_text_body=f"Reset your password by visiting: {reset_url}"
                )
                if email_sent:
                    logger.info("Password reset email sent successfully")
                else:
                    logger.warning("Password reset email FAILED to send - Check SENDGRID_API_KEY or SMTP credentials")
            except Exception as e:
                logger.error(f"Failed to send password reset email: {str(e)}")
                # Still return success to prevent email enumeration
        else:
            logger.info("Password reset requested for non-existent account")

        # Always return success to prevent email enumeration
        return {
            "message": "If an account exists with this email, you will receive a password reset link shortly.",
            "success": True
        }
    except Exception as e:
        logger.error(f"Forgot password error: {str(e)}")
        # Return success even on error to prevent information leakage
        return {
            "message": "If an account exists with this email, you will receive a password reset link shortly.",
            "success": True
        }


# admin-reset-link endpoint REMOVED — it was unauthenticated and generated
# password reset tokens for any email address (open to abuse).


@router.post("/api/v1/auth/reset-password")
async def reset_password(http_request: Request, request: ResetPasswordRequest, db: Session = Depends(get_db)):
    """
    Reset password using a valid reset token.
    """
    # Rate limit password reset attempts
    client_ip = _get_real_client_ip(http_request)
    if not _check_auth_rate_limit(client_ip, _AUTH_RATE_MAX_RESET):
        logger.warning(f"Reset-password rate limit exceeded for {client_ip}")
        raise HTTPException(status_code=429, detail="Too many requests. Please try again later.")
    try:
        models = get_models()
        User = models['User']
        auth_funcs = get_auth_functions()

        # Verify token
        token_data = verify_password_reset_token(request.token)
        if not token_data:
            raise HTTPException(
                status_code=400,
                detail="Invalid or expired reset token. Please request a new password reset."
            )
        email = token_data["email"]
        token_iat = token_data.get("iat")

        # Find user
        user = db.query(User).filter(User.email == email).first()
        if not user:
            raise HTTPException(
                status_code=400,
                detail="Invalid reset token."
            )

        # Prevent token reuse: if password was changed after token was issued, reject
        if token_iat and hasattr(user, 'password_changed_at') and user.password_changed_at:
            changed_ts = user.password_changed_at.timestamp() if hasattr(user.password_changed_at, 'timestamp') else 0
            if changed_ts > token_iat:
                raise HTTPException(
                    status_code=400,
                    detail="This reset token has already been used. Please request a new password reset."
                )

        # Validate password strength
        if len(request.new_password) < 6:
            raise HTTPException(
                status_code=400,
                detail="Password must be at least 6 characters long."
            )

        # Update password and record timestamp to prevent token reuse
        user.hashed_password = auth_funcs['get_password_hash'](request.new_password)
        if hasattr(user, 'password_changed_at'):
            user.password_changed_at = datetime.now(timezone.utc)
        db.commit()

        logger.info(f"Password reset successful for user ID {user.id}")

        return {
            "message": "Password has been reset successfully. You can now log in with your new password.",
            "success": True
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Reset password error: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="An error occurred while resetting your password. Please try again."
        )


@router.post("/api/v1/admin/force-password-reset")
async def admin_force_password_reset(request: AdminPasswordResetRequest, db: Session = Depends(get_db)):
    """
    Admin endpoint to force reset a user's password.
    Requires ADMIN_RESET_KEY environment variable to be set.
    """
    models = get_models()
    User = models['User']
    auth_funcs = get_auth_functions()

    # Verify admin key
    expected_key = os.getenv("ADMIN_RESET_KEY", "")
    if not expected_key or request.admin_key != expected_key:
        logger.warning("Invalid admin reset attempt (bad admin key)")
        raise HTTPException(status_code=403, detail="Invalid admin key")

    # Find user
    user = db.query(User).filter(func.lower(User.email) == request.email.lower()).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Validate password
    if len(request.new_password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    # Update password
    user.hashed_password = auth_funcs['get_password_hash'](request.new_password)
    db.commit()

    logger.info(f"Admin forced password reset for user ID {user.id}")

    return {
        "success": True,
        "message": "Password reset successful"
    }


# =============================================================================
# ADMIN UTILITY ROUTES
# =============================================================================

@router.post("/api/v1/admin/kill-idle-connections")
async def kill_idle_connections():
    """Emergency endpoint to kill idle database connections. Temporary - remove after use."""
    from sqlalchemy import create_engine as _ce
    from sqlalchemy.pool import NullPool
    try:
        db_url = os.getenv("DATABASE_URL", "").replace("postgres://", "postgresql://", 1)
        temp_engine = _ce(db_url, poolclass=NullPool, connect_args={"connect_timeout": 5})
        with temp_engine.connect() as conn:
            stats = conn.execute(text(
                "SELECT count(*) as total, "
                "count(*) FILTER (WHERE state = 'idle') as idle, "
                "count(*) FILTER (WHERE state = 'active') as active, "
                "count(*) FILTER (WHERE state = 'idle in transaction') as idle_in_tx "
                "FROM pg_stat_activity WHERE datname = current_database()"
            )).fetchone()
            total, idle, active, idle_in_tx = stats

            # Kill idle connections
            killed = conn.execute(text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = current_database() AND state = 'idle' AND pid != pg_backend_pid()"
            )).fetchall()

            # Also kill idle in transaction
            killed_tx = conn.execute(text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = current_database() AND state = 'idle in transaction' AND pid != pg_backend_pid()"
            )).fetchall()
            conn.commit()

        temp_engine.dispose()
        return {
            "status": "success",
            "before": {"total": total, "idle": idle, "active": active, "idle_in_tx": idle_in_tx},
            "killed_idle": len(killed),
            "killed_idle_in_tx": len(killed_tx)
        }
    except Exception as e:
        return {"status": "error", "error": "Internal server error"}


@router.post("/api/v1/admin/normalize-loan-stages")
async def normalize_loan_stages(db: Session = Depends(get_db)):
    """Normalize all loan stage values to uppercase. Fixes mixed-case data from legacy imports."""
    try:
        stage_map = {
            'Application': 'APPLICATION',
            'Disclosed': 'DISCLOSED',
            'Processing': 'PROCESSING',
            'In Processing': 'PROCESSING',
            'Submitted': 'SUBMITTED',
            'Underwriting': 'UNDERWRITING',
            'In Underwriting': 'UNDERWRITING',
            'UW Received': 'UW_RECEIVED',
            'Conditional Approval': 'CONDITIONAL_APPROVAL',
            'Approved': 'APPROVED',
            'Suspended': 'SUSPENDED',
            'CTC': 'CTC',
            'Clear to Close': 'CLEAR_TO_CLOSE',
            'Closing': 'CLOSING',
            'Docs': 'DOCS',
            'Docs Out': 'DOCS_OUT',
            'Funded': 'FUNDED',
            'Cancelled': 'CANCELLED',
            'Denied': 'DENIED',
            'Dead': 'DEAD',
            'Nurture': 'NURTURE',
            'Withdrawn': 'WITHDRAWN',
            'Does Not Qualify': 'DOES_NOT_QUALIFY',
        }
        total_updated = 0
        for old_val, new_val in stage_map.items():
            result = db.execute(
                text("UPDATE loans SET stage = :new_val WHERE stage = :old_val"),
                {"old_val": old_val, "new_val": new_val}
            )
            count = result.rowcount
            if count > 0:
                total_updated += count
                logger.info(f"Normalized {count} loans: '{old_val}' -> '{new_val}'")
        db.commit()
        return {"status": "success", "total_updated": total_updated, "message": f"Normalized {total_updated} loan stage values to uppercase"}
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to normalize stages: {e}")
        return {"status": "error", "error": "Internal server error"}


# =============================================================================
# PUBLIC REGISTRATION ROUTES
# =============================================================================

@router.post("/api/v1/auth/register")
async def register_account(
    http_request: Request,
    request: RegisterRequest,
    db: Session = Depends(get_db)
):
    """
    Public registration endpoint for new accounts.
    Creates a new organization and admin user.
    """
    # Rate limit registration attempts
    client_ip = _get_real_client_ip(http_request)
    if not _check_auth_rate_limit(client_ip, _AUTH_RATE_MAX_REGISTER):
        logger.warning(f"Registration rate limit exceeded for {client_ip}")
        raise HTTPException(status_code=429, detail="Too many requests. Please try again later.")

    try:
        models = get_models()
        User = models['User']
        Organization = models['Organization']
        PromoCode = models['PromoCode']
        Subscription = models['Subscription']
        SubscriptionPlan = models['SubscriptionPlan']
        auth_funcs = get_auth_functions()

        # Validate email doesn't already exist
        existing_user = db.query(User).filter(User.email == request.email).first()
        if existing_user:
            raise HTTPException(
                status_code=400,
                detail="An account with this email already exists. Please log in or use a different email."
            )

        # Validate password strength
        if len(request.password) < 8:
            raise HTTPException(
                status_code=400,
                detail="Password must be at least 8 characters long."
            )

        # Validate promo code if provided
        promo = None
        promo_discount = None
        if request.promo_code:
            # Use FOR UPDATE to lock the row and prevent race conditions on max_uses
            promo = db.query(PromoCode).filter(
                PromoCode.code == request.promo_code.upper(),
                PromoCode.is_active == True
            ).with_for_update().first()

            if not promo:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid promo code. Please check and try again."
                )

            # Check if promo is valid
            now = datetime.now(timezone.utc)
            if promo.valid_from and promo.valid_from > now:
                raise HTTPException(
                    status_code=400,
                    detail="This promo code is not yet active."
                )
            if promo.valid_until and promo.valid_until < now:
                raise HTTPException(
                    status_code=400,
                    detail="This promo code has expired."
                )
            if promo.max_uses and promo.current_uses >= promo.max_uses:
                raise HTTPException(
                    status_code=400,
                    detail="This promo code has reached its maximum uses."
                )

            promo_discount = {
                "code": promo.code,
                "type": promo.discount_type,
                "value": promo.discount_value,
                "trial_days": promo.trial_days,
                "description": promo.description
            }

        # Create organization if company name provided
        organization = None
        if request.company_name:
            # Generate a URL-friendly slug
            slug = re.sub(r'[^a-z0-9]+', '-', request.company_name.lower()).strip('-')
            # Add random suffix to ensure uniqueness
            slug = f"{slug}-{secrets.token_hex(4)}"

            organization = Organization(
                name=request.company_name,
                slug=slug,
                subscription_tier=request.plan or "professional",
                is_active=True
            )
            db.add(organization)
            db.flush()

        # Create user
        # Split full_name into first/last for User columns
        _name_parts = (request.full_name or '').strip().split(' ', 1)
        new_user = User(
            email=request.email,
            hashed_password=auth_funcs['get_password_hash'](request.password),
            first_name=_name_parts[0] if _name_parts else '',
            last_name=_name_parts[1] if len(_name_parts) > 1 else '',
            phone=request.phone,
            role="site_admin",
            permission_role="site_admin",
            organization_id=organization.id if organization else None,
            is_active=True,
            onboarding_completed=False,
            user_metadata={
                "registered_at": datetime.now(timezone.utc).isoformat(),
                "plan": request.plan,
                "promo_code": request.promo_code.upper() if request.promo_code else None
            }
        )
        db.add(new_user)
        db.flush()

        # Create subscription
        trial_days = 14  # Default trial
        if promo and promo.trial_days:
            trial_days += promo.trial_days

        # Find the plan — validate against known plan names
        valid_plans = {"starter", "professional", "enterprise", "free", "trial"}
        plan_name = request.plan.lower() if request.plan else "professional"
        if plan_name not in valid_plans:
            plan_name = "professional"
        plan = db.query(SubscriptionPlan).filter(
            SubscriptionPlan.name.ilike(f"%{plan_name}%")
        ).first()

        subscription = Subscription(
            user_id=new_user.id,
            plan_id=plan.id if plan else None,
            status="trialing",
            trial_end=datetime.now(timezone.utc) + timedelta(days=trial_days),
            current_period_start=datetime.now(timezone.utc),
            current_period_end=datetime.now(timezone.utc) + timedelta(days=trial_days)
        )
        db.add(subscription)

        # Increment promo code usage
        if promo:
            promo.current_uses += 1

        db.commit()

        # Generate access token
        access_token = auth_funcs['create_access_token'](data={"sub": new_user.email})

        logger.info(f"New account registered: user ID {new_user.id} (org ID: {organization.id if organization else 'none'})")

        return {
            "success": True,
            "message": "Account created successfully!",
            "access_token": access_token,
            "token_type": "bearer",
            "user": {
                "id": new_user.id,
                "email": new_user.email,
                "full_name": new_user.full_name,
                "role": new_user.role,
                "permission_role": new_user.permission_role,
                "onboarding_completed": new_user.onboarding_completed,
                "organization_id": organization.id if organization else None
            },
            "trial_days": trial_days,
            "promo_applied": promo_discount
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Registration error: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="An error occurred during registration. Please try again."
        )


@router.post("/api/v1/auth/validate-promo")
async def validate_promo_code(
    request: ValidatePromoCodeRequest,
    db: Session = Depends(get_db)
):
    """
    Validate a promo code before registration.
    """
    models = get_models()
    PromoCode = models['PromoCode']

    promo = db.query(PromoCode).filter(
        PromoCode.code == request.code.upper(),
        PromoCode.is_active == True
    ).first()

    if not promo:
        raise HTTPException(
            status_code=400,
            detail="Invalid promo code."
        )

    now = datetime.now(timezone.utc)
    if promo.valid_from and promo.valid_from > now:
        raise HTTPException(
            status_code=400,
            detail="This promo code is not yet active."
        )
    if promo.valid_until and promo.valid_until < now:
        raise HTTPException(
            status_code=400,
            detail="This promo code has expired."
        )
    if promo.max_uses and promo.current_uses >= promo.max_uses:
        raise HTTPException(
            status_code=400,
            detail="This promo code has reached its maximum uses."
        )

    return {
        "valid": True,
        "code": promo.code,
        "description": promo.description,
        "discount_type": promo.discount_type,
        "discount_value": promo.discount_value,
        "trial_days": promo.trial_days
    }


# =============================================================================
# PROMO CODE MANAGEMENT ROUTES (require authentication)
# =============================================================================

def create_admin_promo_routes(app, get_current_user):
    """
    Create admin promo code routes with proper authentication.
    Called from main.py after importing the router.
    """
    from fastapi import Depends

    @app.put("/api/v1/admin/promo-codes/{code}")
    async def update_promo_code(
        code: str,
        request: UpdatePromoCodeRequest,
        current_user = Depends(get_current_user),
        db: Session = Depends(get_db)
    ):
        """Update an existing promo code."""
        from utils.auth import require_admin
        require_admin(current_user)

        models = get_models()
        PromoCode = models['PromoCode']

        promo = db.query(PromoCode).filter(PromoCode.code == code.upper()).first()
        if not promo:
            raise HTTPException(status_code=404, detail="Promo code not found")

        if request.description is not None:
            promo.description = request.description
        if request.discount_type is not None:
            promo.discount_type = request.discount_type
        if request.discount_value is not None:
            promo.discount_value = request.discount_value
        if request.trial_days is not None:
            promo.trial_days = request.trial_days
        if request.max_uses is not None:
            promo.max_uses = request.max_uses
        if request.is_active is not None:
            promo.is_active = request.is_active

        db.commit()
        db.refresh(promo)

        logger.info(f"Promo code updated: {promo.code} by user ID {current_user.id}")

        return {
            "success": True,
            "promo_code": {
                "id": promo.id,
                "code": promo.code,
                "description": promo.description,
                "discount_type": promo.discount_type,
                "discount_value": promo.discount_value,
                "trial_days": promo.trial_days,
                "max_uses": promo.max_uses,
                "is_active": promo.is_active
            }
        }

    @app.post("/api/v1/admin/promo-codes")
    async def create_promo_code(
        request: CreatePromoCodeRequest,
        current_user = Depends(get_current_user),
        db: Session = Depends(get_db)
    ):
        """
        Admin endpoint to create promo codes.
        Requires admin role.
        """
        from utils.auth import require_admin
        require_admin(current_user)

        models = get_models()
        PromoCode = models['PromoCode']

        # Check if code already exists
        existing = db.query(PromoCode).filter(PromoCode.code == request.code.upper()).first()
        if existing:
            raise HTTPException(status_code=400, detail="Promo code already exists")

        promo = PromoCode(
            code=request.code.upper(),
            description=request.description,
            discount_type=request.discount_type,
            discount_value=request.discount_value,
            trial_days=request.trial_days,
            max_uses=request.max_uses,
            current_uses=0,
            is_active=True
        )
        db.add(promo)
        db.commit()
        db.refresh(promo)

        logger.info(f"Promo code created: {promo.code} by user ID {current_user.id}")

        return {
            "success": True,
            "promo_code": {
                "id": promo.id,
                "code": promo.code,
                "description": promo.description,
                "discount_type": promo.discount_type,
                "discount_value": promo.discount_value,
                "trial_days": promo.trial_days,
                "max_uses": promo.max_uses
            }
        }


# =============================================================================
# PUSH NOTIFICATION ROUTES (require authentication)
# =============================================================================

def create_push_notification_routes(app, get_current_user, DeviceToken):
    """
    Create push notification routes with proper authentication.
    Called from main.py after importing the router.
    """
    from fastapi import Depends

    @app.post("/api/v1/push/register")
    async def register_push_token(
        request: PushRegisterRequest,
        current_user = Depends(get_current_user),
        db: Session = Depends(get_db)
    ):
        """
        Register a device token for push notifications.
        Called from the mobile app after getting APNs token.
        """
        try:
            # Check if token already exists for this user
            existing = db.query(DeviceToken).filter(
                DeviceToken.user_id == current_user.id,
                DeviceToken.device_token == request.device_token
            ).first()

            if existing:
                # Update existing token
                existing.is_active = True
                existing.platform = request.platform
                existing.updated_at = datetime.now(timezone.utc)
            else:
                # Create new token
                new_token = DeviceToken(
                    user_id=current_user.id,
                    device_token=request.device_token,
                    platform=request.platform,
                    is_active=True
                )
                db.add(new_token)

            db.commit()
            logger.info(f"Push token registered for user {current_user.id} on {request.platform}")

            return {
                "success": True,
                "message": "Device token registered successfully"
            }
        except Exception as e:
            logger.error(f"Error registering push token: {str(e)}")
            db.rollback()
            raise HTTPException(
                status_code=500,
                detail="Failed to register device token"
            )

    @app.delete("/api/v1/push/unregister")
    async def unregister_push_token(
        device_token: str,
        current_user = Depends(get_current_user),
        db: Session = Depends(get_db)
    ):
        """
        Unregister a device token (e.g., on logout).
        """
        try:
            db.query(DeviceToken).filter(
                DeviceToken.user_id == current_user.id,
                DeviceToken.device_token == device_token
            ).update({"is_active": False})
            db.commit()

            return {
                "success": True,
                "message": "Device token unregistered"
            }
        except Exception as e:
            logger.error(f"Error unregistering push token: {str(e)}")
            db.rollback()
            raise HTTPException(
                status_code=500,
                detail="Failed to unregister device token"
            )


# =============================================================================
# ADMIN SETUP ROUTES
# =============================================================================

@router.post("/api/v1/setup-admin")
async def setup_admin_user(
    admin_key: str = Query(..., description="Admin API key for authorization"),
    db: Session = Depends(get_db),
):
    """
    One-time setup: Create or reset admin user password.
    Requires ADMIN_API_KEY and ADMIN_SETUP_PASSWORD env vars.
    """
    import os as _os
    _ADMIN_API_KEY = _os.getenv("ADMIN_API_KEY")
    if not _ADMIN_API_KEY or admin_key != _ADMIN_API_KEY:
        raise HTTPException(status_code=403, detail="Forbidden")

    admin_email = "admin@perenniaai.com"
    admin_setup_password = _os.getenv("ADMIN_SETUP_PASSWORD")
    if not admin_setup_password:
        raise HTTPException(status_code=500, detail="ADMIN_SETUP_PASSWORD env var not set")

    try:
        from passlib.context import CryptContext
        _pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
        new_hash = _pwd_context.hash(admin_setup_password)

        # Use raw SQL to update password directly to avoid ORM issues
        result = db.execute(
            text("UPDATE users SET hashed_password = :hash, is_active = true WHERE email = :email"),
            {"hash": new_hash, "email": admin_email}
        )
        db.commit()

        if result.rowcount > 0:
            return {
                "message": f"Password reset for {admin_email}",
                "status": "updated",
            }

        # User doesn't exist, create new one
        db.execute(
            text("""
                INSERT INTO users (email, hashed_password, full_name, role, is_active, email_verified, onboarding_completed, created_at)
                VALUES (:email, :hash, 'Admin User', 'admin', true, true, true, NOW())
            """),
            {"email": admin_email, "hash": new_hash}
        )
        db.commit()

        return {
            "message": f"Admin user created: {admin_email}",
            "status": "created",
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Setup admin error: {str(e)}")
        raise HTTPException(status_code=500, detail="Admin setup failed")


# =============================================================================
# SECURITY DASHBOARD ROUTES (require authentication)
# =============================================================================

def create_security_dashboard_routes(app, get_current_user):
    """
    Create security dashboard routes with proper authentication.
    Called from main.py after importing the router.
    """
    from fastapi import Depends

    @app.get("/api/v1/admin/security/dashboard")
    async def get_security_dashboard(current_user = Depends(get_current_user)):
        """
        Get security dashboard metrics including blocked IPs, rate limits, and failed logins.
        Requires admin or management role.
        """
        if current_user.role not in ['admin', 'management']:
            raise HTTPException(status_code=403, detail="Admin access required")

        security_stats = get_security_stats()
        if security_stats:
            return security_stats.get_dashboard_data()
        return {"message": "Security stats not available"}

    @app.post("/api/v1/admin/security/unblock-ip/{ip}")
    async def unblock_ip_address(ip: str, current_user = Depends(get_current_user)):
        """
        Unblock a blocked IP address.
        Requires admin or management role.
        """
        if current_user.role not in ['admin', 'management']:
            raise HTTPException(status_code=403, detail="Admin access required")

        security_stats = get_security_stats()
        if security_stats and security_stats.unblock_ip(ip):
            logger.info(f"IP {ip} unblocked by user ID {current_user.id}")
            return {"message": f"IP {ip} has been unblocked", "success": True}
        else:
            return {"message": f"Could not unblock IP {ip}", "success": False}


# =============================================================================
# SETUP HELPER FUNCTION
# =============================================================================

def setup_auth_routes(app, oauth2_scheme, get_current_user, DeviceToken=None):
    """
    Set up all auth routes that require authentication dependencies.

    Call this from main.py after including the router:

    Example:
        from routes.auth_routes import router as auth_router, setup_auth_routes
        app.include_router(auth_router)
        setup_auth_routes(app, oauth2_scheme, get_current_user, DeviceToken)

    Args:
        app: FastAPI application instance
        oauth2_scheme: OAuth2PasswordBearer scheme
        get_current_user: Dependency function for current user
        DeviceToken: DeviceToken model class (optional, for push notifications)
    """
    # Set up logout routes
    create_logout_routes(app, oauth2_scheme, get_current_user)

    # Set up admin promo code routes
    create_admin_promo_routes(app, get_current_user)

    # Set up push notification routes (if DeviceToken model available)
    if DeviceToken is not None:
        create_push_notification_routes(app, get_current_user, DeviceToken)

    # Set up security dashboard routes
    create_security_dashboard_routes(app, get_current_user)

    logger.info("Auth routes with authentication dependencies set up successfully")
