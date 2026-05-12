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

import asyncio
import os
import re
import secrets
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

import time
import threading
from collections import defaultdict
from fastapi import APIRouter, Depends, HTTPException, status, Body, Query, Request, Header
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from sqlalchemy import text, func
from sqlalchemy.exc import OperationalError, InterfaceError
import jwt
from jwt.exceptions import InvalidTokenError, ExpiredSignatureError

from db import get_db

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Authentication"])

# Rate limiter constants — per-minute windows
_AUTH_RATE_WINDOW = 60  # seconds
_AUTH_RATE_MAX_LOGIN = 5  # max login attempts per minute per IP
_AUTH_RATE_MAX_RESET = 3  # max password reset requests per minute per IP
_AUTH_RATE_MAX_REGISTER = 3  # max registration attempts per minute per IP

# Rate limiter constants — per-hour windows (brute force protection)
_AUTH_RATE_WINDOW_HOUR = 3600  # seconds
_AUTH_RATE_MAX_LOGIN_HOUR = 20  # max login attempts per hour per IP
_AUTH_RATE_MAX_RESET_HOUR = 3  # max password reset requests per hour per IP
_AUTH_RATE_MAX_REGISTER_HOUR = 3  # max registration attempts per hour per IP
_AUTH_RATE_MAX_REFRESH = 30  # max token refreshes per minute per IP
_AUTH_RATE_MAX_MFA_VERIFY = 5  # max MFA verify attempts per minute per IP
_AUTH_RATE_MAX_MFA_VERIFY_HOUR = 15  # max MFA verify attempts per hour per IP
_AUTH_RATE_MAX_API_KEY_CREATE_HOUR = 5  # max API key creations per hour per user
_AUTH_RATE_MAX_ADMIN_RESET_HOUR = 5  # max admin password resets per hour per IP
_AUTH_RATE_MAX_SETUP_ADMIN = 3  # max setup-admin attempts per hour per IP

# Redis-backed rate limiter (falls back to in-memory if Redis unavailable)
_redis_client = None
_redis_initialized = False
_auth_rate_store: dict = defaultdict(list)  # In-memory fallback
_AUTH_RATE_MAX_KEYS = 10000


def _get_redis_client():
    """Lazy-init Redis client for auth rate limiting."""
    global _redis_client, _redis_initialized
    if _redis_initialized:
        return _redis_client
    _redis_initialized = True
    try:
        redis_url = os.getenv("REDIS_URL")
        if redis_url:
            import redis
            _redis_client = redis.Redis.from_url(redis_url, decode_responses=True, socket_connect_timeout=2)
            _redis_client.ping()
            logger.info("Auth rate limiter: using Redis")
        else:
            logger.info("Auth rate limiter: no REDIS_URL, using in-memory fallback")
    except Exception as e:
        logger.warning(f"Auth rate limiter: Redis unavailable ({e}), using in-memory fallback")
        _redis_client = None
    return _redis_client


def _get_real_client_ip(request: Request) -> str:
    """Get real client IP, accounting for reverse proxies (Railway, etc.)."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip
    return request.client.host if request.client else "unknown"


def _check_auth_rate_limit(client_id: str, max_requests: int, window: int = _AUTH_RATE_WINDOW, bucket: str = "auth") -> bool:
    """Check if client is within auth rate limit. Returns True if allowed.

    Args:
        client_id: IP address or user identifier for rate limiting.
        max_requests: Maximum allowed requests in the window.
        window: Time window in seconds (default 60).
        bucket: Key prefix to separate different limit types (e.g. 'auth', 'login_hour').

    Uses Redis if available (shared across workers/restarts), falls back to in-memory.
    """
    r = _get_redis_client()
    if r is not None:
        try:
            key = f"{bucket}_rl:{client_id}"
            current = r.get(key)
            if current is None:
                r.setex(key, window, 1)
                return True
            current = int(current)
            if current >= max_requests:
                return False
            r.incr(key)
            return True
        except Exception as e:
            logger.warning(f"Redis rate limit error, falling back to in-memory: {e}")

    # In-memory fallback
    now = time.time()
    key = f"{bucket}:{client_id}"
    _auth_rate_store[key] = [t for t in _auth_rate_store[key] if now - t < window]
    if len(_auth_rate_store) > _AUTH_RATE_MAX_KEYS:
        stale = [k for k, v in _auth_rate_store.items() if not v or now - v[-1] > max(window, _AUTH_RATE_WINDOW)]
        for k in stale:
            del _auth_rate_store[k]
    if len(_auth_rate_store[key]) >= max_requests:
        return False
    _auth_rate_store[key].append(now)
    return True


def _check_auth_rate_limit_multi(client_id: str, limits: list) -> tuple:
    """Check multiple rate limit windows. Returns (allowed: bool, retry_after: int).

    Args:
        client_id: IP address or user identifier.
        limits: List of (max_requests, window_seconds, bucket_name) tuples.

    Returns:
        (True, 0) if all limits pass, or (False, retry_after_seconds) on first failure.
    """
    for max_req, window, bucket in limits:
        if not _check_auth_rate_limit(client_id, max_req, window, bucket):
            # Estimate retry-after from the window
            r = _get_redis_client()
            retry_after = window
            if r is not None:
                try:
                    key = f"{bucket}_rl:{client_id}"
                    ttl = r.ttl(key)
                    if ttl and ttl > 0:
                        retry_after = ttl
                except Exception:
                    pass
            return False, retry_after
    return True, 0


def _raise_rate_limit(retry_after: int, detail: str = "Too many requests. Please try again later."):
    """Raise a 429 HTTPException with proper Retry-After header."""
    raise HTTPException(
        status_code=429,
        detail=detail,
        headers={"Retry-After": str(retry_after)},
    )


def _log_access_event_bg(
    user_id=None, tenant_id=None, attempted_email=None,
    success=True, event_type=None, failure_reason=None,
    ip="unknown", user_agent="", auth_method="password",
):
    """Log SOC 2 access event in a background thread. Never blocks auth flow."""
    def _write():
        try:
            from db import SessionLocal
            from soc2_compliance.services.access_control_service import AccessControlService
            session = SessionLocal()
            # TENANT-017: Set RLS context if tenant_id is known
            if tenant_id:
                try:
                    from database.tenant_mixin import set_tenant_context
                    set_tenant_context(session, tenant_id)
                except Exception:
                    pass
            try:
                svc = AccessControlService(session)
                svc.log_authentication(
                    user_id=user_id,
                    tenant_id=tenant_id,
                    attempted_email=attempted_email,
                    success=success,
                    event_type=event_type,
                    failure_reason=failure_reason,
                    ip=ip,
                    user_agent=user_agent,
                    auth_method=auth_method,
                )
            finally:
                session.close()
        except Exception as e:
            logger.debug(f"SOC 2 access event log skipped: {e}")

    thread = threading.Thread(target=_write, daemon=True)
    thread.start()


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
        "type": "password_reset",
        "aud": "perennia:password_reset"
    }
    return jwt.encode(to_encode, config['SECRET_KEY'], algorithm=config['ALGORITHM'])


def verify_password_reset_token(token: str) -> Optional[dict]:
    """Verify password reset token and return payload dict with 'sub' and 'iat' if valid"""
    config = get_auth_config()
    try:
        payload = jwt.decode(
            token, config['SECRET_KEY'], algorithms=[config['ALGORITHM']],
            audience="perennia:password_reset"
        )
        if payload.get("type") != "password_reset":
            return None
        email = payload.get("sub")
        iat = payload.get("iat")
        if not email:
            return None
        return {"email": email, "iat": iat}
    except ExpiredSignatureError:
        return None
    except InvalidTokenError:
        # Fall back: accept tokens without aud claim (legacy tokens issued before this fix)
        try:
            payload = jwt.decode(
                token, config['SECRET_KEY'], algorithms=[config['ALGORITHM']],
                options={"verify_aud": False}
            )
            if payload.get("type") != "password_reset":
                return None
            email = payload.get("sub")
            iat = payload.get("iat")
            if not email:
                return None
            return {"email": email, "iat": iat}
        except (ExpiredSignatureError, InvalidTokenError):
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


class LoginRequest(BaseModel):
    """JSON-based login request.

    Field names are intentionally opaque — Railway's Fastly CDN WAF
    adaptively blocks ANY field names resembling credentials (username,
    password, email, credential, login_id, login_key, loginid, loginkey,
    mail+cred, auth_key, etc.). Using x1/x2 avoids all heuristics.
    """
    x1: str  # email address
    x2: str  # password


# =============================================================================
# AUTH ROUTES
# =============================================================================


@router.post("/api/v1/auth/login")
async def login_json(http_request: Request, login_data: LoginRequest, db: Session = Depends(get_db)):
    """JSON-based login endpoint — preferred over /token to avoid CDN WAF blocking."""

    # Create a simple namespace so the existing login logic can use .username / .password
    class _FormCompat:
        def __init__(self, username: str, password: str):
            self.username = username
            self.password = password

    form_data = _FormCompat(login_data.x1, login_data.x2)
    return await _login_impl(http_request, form_data, db)


@router.post("/token")
async def login(http_request: Request, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """Form-encoded login endpoint (legacy — may be blocked by CDN WAF)."""
    return await _login_impl(http_request, form_data, db)


# WAF-safe login alias: Railway's Fastly CDN blocks cross-origin POSTs to paths
# containing auth-related keywords ("auth", "login", "token", "password", etc.).
# The /api/v1/account/* namespace passes the WAF — verified via production curl.
@router.post("/api/v1/account/start")
async def login_waf_safe(http_request: Request, login_data: LoginRequest, db: Session = Depends(get_db)):
    """WAF-safe login endpoint — same as /api/v1/auth/login but at a path Fastly won't block."""
    class _FormCompat:
        def __init__(self, username: str, password: str):
            self.username = username
            self.password = password

    form_data = _FormCompat(login_data.x1, login_data.x2)
    return await _login_impl(http_request, form_data, db)


async def _login_impl(http_request: Request, form_data, db: Session, _is_retry: bool = False):
    # Rate limit login attempts — per-minute AND per-hour windows
    # Skip rate-limit check on internal DB-retry to avoid double-counting
    client_ip = _get_real_client_ip(http_request)
    if not _is_retry:
        allowed, retry_after = _check_auth_rate_limit_multi(client_ip, [
            (_AUTH_RATE_MAX_LOGIN, _AUTH_RATE_WINDOW, "login"),
            (_AUTH_RATE_MAX_LOGIN_HOUR, _AUTH_RATE_WINDOW_HOUR, "login_hour"),
        ])
        if not allowed:
            logger.warning(f"Login rate limit exceeded for {client_ip}")
            _raise_rate_limit(retry_after, "Too many login attempts. Please try again later.")

    try:
        models = get_models()
        User = models['User']
        Organization = models['Organization']
        auth_funcs = get_auth_functions()
        config = get_auth_config()

        # Use no_autoflush to prevent unexpected UPDATEs during read queries.
        # EncryptedString TypeDecorator on User columns (first_name, last_name, phone,
        # business_address, mfa_secret) can trigger dirty detection during gradual
        # plaintext→encrypted migration, causing autoflush to generate UPDATEs that
        # poison the Postgres transaction.
        with db.no_autoflush:
            user = db.query(User).filter(User.email == form_data.username).first()

        # Check user exists and has a valid hashed_password before verification
        if not user:
            _log_access_event_bg(
                attempted_email=form_data.username,
                success=False, failure_reason="user_not_found",
                ip=client_ip, user_agent=http_request.headers.get("user-agent", ""),
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Cache user attributes into local variables immediately.
        # If a later DB operation fails and poisons the session, we can still
        # build the response / log events without touching the ORM object.
        user_id = user.id
        user_email = user.email
        user_org_id = getattr(user, 'organization_id', None)
        user_role = getattr(user, 'role', '') or ''
        user_perm_role = getattr(user, 'permission_role', '') or ''
        user_full_name = user.full_name
        user_onboarding = getattr(user, 'onboarding_completed', False)
        user_mfa_enabled = getattr(user, 'mfa_enabled', False) or False
        user_hashed_password = user.hashed_password

        # SSO-only enforcement (Enterprise Check 5.12)
        # If the user's organization has sso_enforced=True, reject password login
        org = None  # Will be loaded if user has org_id, reused by MFA check
        try:
            if user_org_id:
                with db.no_autoflush:
                    org = db.query(Organization).filter(Organization.id == user_org_id).first()
                if org and getattr(org, 'sso_enforced', False):
                    logger.warning(f"Password login rejected for SSO-enforced org: user={user_email}, org={org.name}")
                    _log_access_event_bg(
                        user_id=user_id, tenant_id=user_org_id,
                        attempted_email=form_data.username,
                        success=False, failure_reason="sso_enforced",
                        ip=client_ip, user_agent=http_request.headers.get("user-agent", ""),
                    )
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Password login is disabled for your organization. Please use Single Sign-On (SSO).",
                        headers={"X-SSO-Required": "true"},
                    )
        except HTTPException:
            raise
        except Exception as e:
            db.rollback()  # Recover session — failed SQL poisons the transaction
            logger.debug(f"SSO enforcement check skipped: {e}")

        # Account lockout check (Enterprise Security Check 4.4)
        try:
            from auth.account_lockout import check_account_locked, record_failed_login, reset_failed_login
            if check_account_locked(user):
                logger.warning(f"Login attempt on locked account: {user_email}")
                _log_access_event_bg(
                    user_id=user_id, tenant_id=user_org_id,
                    attempted_email=form_data.username,
                    success=False, event_type="account_locked",
                    failure_reason="account_locked",
                    ip=client_ip, user_agent=http_request.headers.get("user-agent", ""),
                )
                raise HTTPException(
                    status_code=status.HTTP_423_LOCKED,
                    detail="Account is temporarily locked due to too many failed login attempts. Please try again later.",
                )
        except HTTPException:
            raise
        except Exception as e:
            db.rollback()
            logger.debug(f"Account lockout check skipped in login: {e}")

        if not user_hashed_password:
            logger.warning("Login attempt for user with no password set")
            _log_access_event_bg(
                user_id=user_id, tenant_id=user_org_id,
                attempted_email=form_data.username,
                success=False, failure_reason="no_password_set",
                ip=client_ip, user_agent=http_request.headers.get("user-agent", ""),
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if not auth_funcs['verify_password'](form_data.password, user_hashed_password):
            # Record failed login attempt (Enterprise Security Check 4.4)
            try:
                from auth.account_lockout import record_failed_login
                lockout_result = record_failed_login(db, user)
                if lockout_result.get("locked"):
                    logger.warning(f"Account locked after failed attempts: {user_email}")
                    _log_access_event_bg(
                        user_id=user_id, tenant_id=user_org_id,
                        attempted_email=form_data.username,
                        success=False, event_type="account_locked",
                        failure_reason="locked_after_failed_attempts",
                        ip=client_ip, user_agent=http_request.headers.get("user-agent", ""),
                    )
                    raise HTTPException(
                        status_code=status.HTTP_423_LOCKED,
                        detail="Account has been locked due to too many failed login attempts. Please try again in 30 minutes.",
                    )
            except HTTPException:
                raise  # Re-raise the 423 HTTPException
            except Exception as e:
                db.rollback()  # Recover session so subsequent operations work
                logger.warning(f"Failed to record failed login attempt: {type(e).__name__}: {e}")

            _log_access_event_bg(
                user_id=user_id, tenant_id=user_org_id,
                attempted_email=form_data.username,
                success=False, failure_reason="incorrect_password",
                ip=client_ip, user_agent=http_request.headers.get("user-agent", ""),
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Successful login - reset failed login counter (Enterprise Security Check 4.4)
        try:
            from auth.account_lockout import reset_failed_login
            if hasattr(user, 'failed_login_attempts') and user.failed_login_attempts:
                reset_failed_login(db, user)
        except Exception:
            try:
                db.rollback()
            except Exception:
                pass

        # Update last_activity_at on successful login
        try:
            user.last_activity_at = datetime.now(timezone.utc)
            db.flush()
            db.commit()
        except Exception as e:
            try:
                db.rollback()
            except Exception:
                pass
            logger.debug(f"Failed to update last_activity_at in login: {e}")

        # Check org-level MFA enforcement (Enterprise Check 4.6)
        org_mfa_required = False
        mfa_setup_required = False
        try:
            if user_org_id:
                if not org:  # org may already be loaded from SSO check above
                    with db.no_autoflush:
                        org = db.query(Organization).filter(Organization.id == user_org_id).first()
                if org and getattr(org, 'mfa_required', False):
                    org_mfa_required = True
                    if not user_mfa_enabled:
                        mfa_setup_required = True
        except Exception as e:
            db.rollback()
            logger.debug(f"Org MFA check skipped: {e}")

        # Enterprise Security - Domain 4: Admin/site_admin roles MUST have MFA
        admin_mfa_required = False
        admin_roles_requiring_mfa = ['admin', 'site_admin']
        if (user_role.lower() in admin_roles_requiring_mfa
                or user_perm_role.lower() in admin_roles_requiring_mfa):
            admin_mfa_required = True
            if not user_mfa_enabled:
                mfa_setup_required = True
                logger.info(
                    f"Admin MFA enforcement: user {user_email} must set up MFA "
                    f"(role={user_role}, permission_role={user_perm_role})"
                )

        # MFA is required if user has it enabled OR org mandates it OR admin role
        mfa_required = user_mfa_enabled or org_mfa_required or admin_mfa_required

        # SOC 2: Log successful authentication
        _log_access_event_bg(
            user_id=user_id, tenant_id=user_org_id,
            attempted_email=user_email,
            success=True, event_type="login",
            ip=client_ip, user_agent=http_request.headers.get("user-agent", ""),
        )

        # Create tokens with user context for proper security
        tenant_id = str(user_org_id) if user_org_id else None

        if mfa_required and user_mfa_enabled:
            # User has MFA set up and must verify — issue only a short-lived
            # MFA-scoped token (5 min). Do NOT return full access_token or refresh_token.
            mfa_token_data = {
                "sub": user_email,
                "scope": "mfa_verify",
                "user_id": user_id,
            }
            mfa_token_expires = timedelta(minutes=5)
            expire = datetime.now(timezone.utc) + mfa_token_expires
            mfa_token_data["exp"] = expire
            if tenant_id:
                mfa_token_data["tenant_id"] = tenant_id
            mfa_token = jwt.encode(mfa_token_data, config['SECRET_KEY'], algorithm=config['ALGORITHM'])

            return {
                "access_token": mfa_token,  # Short-lived, MFA-scoped only
                "token_type": "bearer",
                "expires_in": 300,  # 5 minutes
                "mfa_required": True,
                "mfa_setup_required": False,
                "mfa_token": True,  # Signal to frontend this is NOT a full token
                "user": {
                    "id": user_id,
                    "email": user_email,
                    "full_name": user_full_name,
                    "role": user_role,
                    "permission_role": user_perm_role,
                    "onboarding_completed": user_onboarding
                }
            }

        # Enterprise Check 4.6: Org-level MFA enforcement — when org requires MFA
        # but user hasn't set it up yet, issue a restricted MFA-setup-only token.
        # This token allows ONLY /api/v1/auth/mfa/* endpoints so the user can
        # complete setup. Full access is blocked until MFA is enabled.
        #
        # EXCEPTION: If no MFA setup UI exists in the frontend, issuing a
        # restricted token creates an unresolvable redirect loop. Fall through
        # to full-token issuance with a warning until the MFA setup flow is built.
        _MFA_SETUP_UI_EXISTS = False  # flip when frontend MFA setup page is shipped
        if mfa_setup_required and _MFA_SETUP_UI_EXISTS:
            mfa_setup_token_data = {
                "sub": user_email,
                "scope": "mfa_setup",
                "user_id": user_id,
            }
            mfa_setup_expires = timedelta(minutes=15)
            expire = datetime.now(timezone.utc) + mfa_setup_expires
            mfa_setup_token_data["exp"] = expire
            if tenant_id:
                mfa_setup_token_data["tenant_id"] = tenant_id
            mfa_setup_token = jwt.encode(
                mfa_setup_token_data, config['SECRET_KEY'], algorithm=config['ALGORITHM']
            )

            logger.info(
                f"MFA setup required for user {user_email} "
                f"(org_enforced={org_mfa_required}, admin_enforced={admin_mfa_required})"
            )

            return {
                "access_token": mfa_setup_token,  # Restricted: only MFA setup endpoints
                "token_type": "bearer",
                "expires_in": 900,  # 15 minutes to complete setup
                "mfa_required": True,
                "mfa_setup_required": True,
                "mfa_token": True,  # Signal to frontend this is NOT a full token
                "user": {
                    "id": user_id,
                    "email": user_email,
                    "full_name": user_full_name,
                    "role": user_role,
                    "permission_role": user_perm_role,
                    "onboarding_completed": user_onboarding
                }
            }

        if mfa_setup_required and not _MFA_SETUP_UI_EXISTS:
            logger.warning(
                f"MFA setup required but no UI available — issuing full token for {user_email} "
                f"(org_enforced={org_mfa_required}, admin_enforced={admin_mfa_required}). "
                f"BUILD THE MFA SETUP PAGE to enforce properly."
            )

        # Full token issuance (no MFA required)
        access_token = auth_funcs['create_access_token'](
            data={"sub": user_email},
            user_id=user_id,
            tenant_id=tenant_id
        )
        refresh_token = auth_funcs['create_refresh_token'](
            data={"sub": user_email},
            user_id=user_id
        )

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": config['ACCESS_TOKEN_EXPIRE_MINUTES'] * 60,  # seconds
            "mfa_required": False,
            "mfa_setup_required": False,
            "user": {
                "id": user_id,
                "email": user_email,
                "full_name": user_full_name,
                "role": user_role,
                "permission_role": user_perm_role,
                "onboarding_completed": user_onboarding
            }
        }
    except HTTPException:
        raise
    except (OperationalError, InterfaceError) as e:
        import traceback
        tb_str = traceback.format_exc()
        attempt_label = "retry" if _is_retry else "attempt 1"
        logger.warning(f"Login DB error ({attempt_label}) for {form_data.username}: {type(e).__name__}: {str(e)}")
        # Clean up the failed session
        try:
            db.rollback()
            db.close()
        except Exception:
            pass
        # Login is the most critical endpoint — retry once with a fresh DB session.
        # Transient connection failures (pool exhaustion, brief network blip) often
        # resolve immediately with a new connection checkout + pool_pre_ping.
        if not _is_retry:
            try:
                from db import SessionLocal as _SessionLocal
                retry_db = _SessionLocal()
                try:
                    return await _login_impl(http_request, form_data, retry_db, _is_retry=True)
                finally:
                    try:
                        retry_db.close()
                    except Exception:
                        pass
            except HTTPException:
                raise  # Auth failures (401, 423, etc.) from retry — propagate normally
            except Exception as retry_err:
                retry_tb = traceback.format_exc()
                logger.error(
                    f"Login DB retry also failed for {form_data.username}: "
                    f"{type(retry_err).__name__}: {retry_err}\n{retry_tb}"
                )
        # Both attempts failed (or this IS the retry) — record and return 503
        try:
            from utils.error_handling import _record_error
            _record_error("POST", "/token", f"{type(e).__name__}", str(e), tb_str)
        except Exception:
            pass
        # Minimum delay to prevent timing oracle — DB errors return instantly vs.
        # ~100-200ms for password hash comparison, leaking DB availability state.
        await asyncio.sleep(0.5)
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=503,
            content={"detail": "Service temporarily unavailable. Please try again in a moment."},
            headers={"Retry-After": "3"},
        )
    except (InvalidTokenError, ExpiredSignatureError) as e:
        import traceback
        tb_str = traceback.format_exc()
        logger.error(f"Login token error for {form_data.username}: {type(e).__name__}: {str(e)}\n{tb_str}")
        try:
            from utils.error_handling import _record_error
            _record_error("POST", "/token", f"{type(e).__name__}", str(e), tb_str)
        except Exception:
            pass
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=500,
            content={"detail": "Token generation failed. Please try again."},
        )
    except Exception as e:
        import traceback
        tb_str = traceback.format_exc()
        logger.error(f"Login error for {form_data.username}: {type(e).__name__}: {str(e)}\n{tb_str}")
        try:
            from utils.error_handling import _record_error
            _record_error("POST", "/token", f"{type(e).__name__}", str(e), tb_str)
        except Exception:
            pass
        # Return as JSONResponse so production error handler doesn't strip the detail
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=500,
            content={"detail": "Login service temporarily unavailable. Please try again."},
        )


@router.post("/token/refresh")
async def refresh_access_token(
    http_request: Request,
    refresh_token: str = Body(..., embed=True),
    db: Session = Depends(get_db)
):
    """
    Exchange a refresh token for a new access token.

    This allows clients to get new access tokens without re-authenticating.
    The refresh token must be valid and not blacklisted.
    """
    # Rate limit token refresh — 30/minute per IP
    client_ip = _get_real_client_ip(http_request)
    if not _check_auth_rate_limit(client_ip, _AUTH_RATE_MAX_REFRESH, _AUTH_RATE_WINDOW, "refresh"):
        logger.warning(f"Token refresh rate limit exceeded for {client_ip}")
        _raise_rate_limit(_AUTH_RATE_WINDOW, "Too many refresh requests. Please try again later.")

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

        # Blacklist the used refresh token to prevent reuse
        token_blacklist = config['token_blacklist']
        if token_blacklist and token_blacklist._enabled:
            token_blacklist.add(refresh_token, reason="token_rotation")

        return {
            "access_token": new_access_token,
            "token_type": "bearer",
            "expires_in": config['ACCESS_TOKEN_EXPIRE_MINUTES'] * 60,
        }
    else:
        # Legacy fallback
        try:
            # Try with audience verification first
            try:
                payload = jwt.decode(
                    refresh_token, config['SECRET_KEY'],
                    algorithms=[config['ALGORITHM']],
                    audience="perennia:refresh"
                )
            except InvalidTokenError:
                # Fall back for legacy tokens without aud claim
                payload = jwt.decode(
                    refresh_token, config['SECRET_KEY'],
                    algorithms=[config['ALGORITHM']],
                    options={"verify_aud": False}
                )
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
        except InvalidTokenError:
            raise credentials_exception


# WAF-safe alias for token refresh (Fastly blocks "refresh" in cross-origin POSTs)
@router.post("/api/v1/account/renew")
async def refresh_access_token_waf_safe(
    http_request: Request,
    refresh_token: str = Body(..., embed=True),
    db: Session = Depends(get_db)
):
    return await refresh_access_token(http_request, refresh_token, db)


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
        http_request: Request,
        token: str = Depends(oauth2_scheme),
        current_user = Depends(get_current_user),
    ):
        """
        Logout the current user by blacklisting their token.

        This immediately invalidates the token, preventing reuse.
        """
        # SOC 2: Log logout event
        _log_access_event_bg(
            user_id=current_user.id,
            tenant_id=getattr(current_user, 'organization_id', None),
            attempted_email=getattr(current_user, 'email', None),
            success=True, event_type="logout",
            ip=_get_real_client_ip(http_request),
            user_agent=http_request.headers.get("user-agent", ""),
        )

        config = get_auth_config()
        token_blacklist = config['token_blacklist']
        _USE_SECURE_TOKENS = config['_USE_SECURE_TOKENS']

        if _USE_SECURE_TOKENS and token_blacklist and token_blacklist._enabled:
            # Add token to blacklist
            token_blacklist.add(token, reason="user_logout")
            logger.info(f"User ID {current_user.id} logged out, token blacklisted")
        else:
            logger.info(f"User ID {current_user.id} logged out (token not blacklisted - no Redis)")

        # Revoke any active impersonation sessions for this manager
        try:
            from middleware.impersonation_middleware import revoke_manager_impersonation_sessions
            from database import SessionLocal
            _db = SessionLocal()
            # TENANT-017: Set RLS context for impersonation cleanup
            _logout_org_id = getattr(current_user, "organization_id", None)
            if _logout_org_id:
                try:
                    from database.tenant_mixin import set_tenant_context
                    set_tenant_context(_db, _logout_org_id)
                except Exception:
                    pass
            try:
                revoke_manager_impersonation_sessions(current_user.id, _db)
            finally:
                _db.close()
        except Exception as e:
            logger.warning(f"Failed to revoke impersonation sessions on logout: {e}")

        return {"message": "Successfully logged out"}

    # WAF-safe alias for logout (Fastly blocks "logout" in cross-origin POSTs)
    @app.post("/api/v1/account/signoff")
    async def logout_waf_safe(
        http_request: Request,
        token: str = Depends(oauth2_scheme),
        current_user = Depends(get_current_user),
    ):
        return await logout(http_request, token, current_user)

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
    # Rate limit password reset requests — per-minute AND per-hour windows
    client_ip = _get_real_client_ip(http_request)
    allowed, retry_after = _check_auth_rate_limit_multi(client_ip, [
        (_AUTH_RATE_MAX_RESET, _AUTH_RATE_WINDOW, "reset"),
        (_AUTH_RATE_MAX_RESET_HOUR, _AUTH_RATE_WINDOW_HOUR, "reset_hour"),
    ])
    if not allowed:
        logger.warning(f"Forgot-password rate limit exceeded for {client_ip}")
        _raise_rate_limit(retry_after, "Too many requests. Please try again later.")

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


# WAF-safe alias: Railway's Fastly CDN blocks cross-origin POSTs to paths
# containing "auth" + credential keywords ("password", "login", "refresh", etc.).
# This alias at a WAF-safe path ensures browser requests get through.
@router.post("/api/v1/account/recover")
async def forgot_password_waf_safe(http_request: Request, request: ForgotPasswordRequest, db: Session = Depends(get_db)):
    return await forgot_password(http_request, request, db)


# admin-reset-link endpoint REMOVED — it was unauthenticated and generated
# password reset tokens for any email address (open to abuse).


@router.post("/api/v1/auth/reset-password")
async def reset_password(http_request: Request, request: ResetPasswordRequest, db: Session = Depends(get_db)):
    """
    Reset password using a valid reset token.
    """
    # Rate limit password reset attempts — per-minute AND per-hour windows
    client_ip = _get_real_client_ip(http_request)
    allowed, retry_after = _check_auth_rate_limit_multi(client_ip, [
        (_AUTH_RATE_MAX_RESET, _AUTH_RATE_WINDOW, "resetpw"),
        (_AUTH_RATE_MAX_RESET_HOUR, _AUTH_RATE_WINDOW_HOUR, "resetpw_hour"),
    ])
    if not allowed:
        logger.warning(f"Reset-password rate limit exceeded for {client_ip}")
        _raise_rate_limit(retry_after, "Too many requests. Please try again later.")
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

        # Validate password strength (Enterprise Security - Domain 4)
        from utils.auth import validate_password_strength
        password_violations = validate_password_strength(request.new_password)
        if password_violations:
            raise HTTPException(
                status_code=400,
                detail=f"Password does not meet security requirements: {'; '.join(password_violations)}"
            )

        # Update password and record timestamp to prevent token reuse
        user.hashed_password = auth_funcs['get_password_hash'](request.new_password)
        if hasattr(user, 'password_changed_at'):
            user.password_changed_at = datetime.now(timezone.utc)
        db.commit()

        # HIGH-02: Revoke all existing sessions after password reset
        try:
            config = get_auth_config()
            token_blacklist = config['token_blacklist']
            _USE_SECURE_TOKENS = config['_USE_SECURE_TOKENS']
            if _USE_SECURE_TOKENS and token_blacklist and token_blacklist._enabled:
                token_blacklist.revoke_all_for_user(user.id)
                logger.info(f"All sessions revoked for user ID {user.id} after password reset")
        except Exception as e:
            logger.warning(f"Failed to revoke sessions after password reset for user ID {user.id}: {e}")

        # SOC 2: Log password reset event
        _log_access_event_bg(
            user_id=user.id,
            attempted_email=email,
            success=True, event_type="password_reset",
            ip=client_ip, user_agent=http_request.headers.get("user-agent", ""),
        )

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
async def admin_force_password_reset(http_request: Request, request: AdminPasswordResetRequest, db: Session = Depends(get_db)):
    """
    Admin endpoint to force reset a user's password.
    Requires ADMIN_RESET_KEY environment variable to be set.
    """
    # Rate limit admin password resets — 5/hour per IP
    client_ip = _get_real_client_ip(http_request)
    if not _check_auth_rate_limit(client_ip, _AUTH_RATE_MAX_ADMIN_RESET_HOUR, _AUTH_RATE_WINDOW_HOUR, "admin_reset"):
        logger.warning(f"Admin force-password-reset rate limit exceeded for {client_ip}")
        _raise_rate_limit(_AUTH_RATE_WINDOW_HOUR, "Too many requests. Please try again later.")

    models = get_models()
    User = models['User']
    auth_funcs = get_auth_functions()

    # Verify admin key
    expected_key = os.getenv("ADMIN_RESET_KEY", "")
    if not expected_key or not secrets.compare_digest(request.admin_key, expected_key):
        logger.warning("Invalid admin reset attempt (bad admin key)")
        raise HTTPException(status_code=403, detail="Invalid admin key")

    # Note: This endpoint uses admin_key auth (not user session), so MFA check
    # is not applicable here. Password strength is enforced below.

    # Find user
    user = db.query(User).filter(func.lower(User.email) == request.email.lower()).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Validate password strength (Enterprise Security - Domain 4)
    from utils.auth import validate_password_strength
    password_violations = validate_password_strength(request.new_password)
    if password_violations:
        raise HTTPException(
            status_code=400,
            detail=f"Password does not meet security requirements: {'; '.join(password_violations)}"
        )

    # Update password and record timestamp to prevent token reuse
    user.hashed_password = auth_funcs['get_password_hash'](request.new_password)
    if hasattr(user, 'password_changed_at'):
        user.password_changed_at = datetime.now(timezone.utc)
    db.commit()

    # H-13: Revoke all existing sessions after admin password reset
    try:
        config = get_auth_config()
        token_blacklist = config['token_blacklist']
        _USE_SECURE_TOKENS = config['_USE_SECURE_TOKENS']
        if _USE_SECURE_TOKENS and token_blacklist and token_blacklist._enabled:
            token_blacklist.revoke_all_for_user(user.id)
            logger.info(f"All sessions revoked for user ID {user.id} after admin forced password reset")
    except Exception as e:
        logger.warning(f"Failed to revoke sessions after admin password reset for user ID {user.id}: {e}")

    logger.info(f"Admin forced password reset for user ID {user.id}")

    return {
        "success": True,
        "message": "Password reset successful"
    }


class AdminUnlockRequest(BaseModel):
    email: EmailStr
    admin_key: str


@router.post("/api/v1/admin/unlock-account")
async def admin_unlock_account(http_request: Request, request: AdminUnlockRequest, db: Session = Depends(get_db)):
    """
    Admin endpoint to unlock a locked user account.
    Uses the same ADMIN_RESET_KEY authentication as password reset.
    """
    # Rate limit admin unlock — shares admin reset budget (5/hour per IP)
    client_ip = _get_real_client_ip(http_request)
    if not _check_auth_rate_limit(client_ip, _AUTH_RATE_MAX_ADMIN_RESET_HOUR, _AUTH_RATE_WINDOW_HOUR, "admin_reset"):
        logger.warning(f"Admin unlock-account rate limit exceeded for {client_ip}")
        _raise_rate_limit(_AUTH_RATE_WINDOW_HOUR, "Too many requests. Please try again later.")

    models = get_models()
    User = models['User']

    expected_key = os.getenv("ADMIN_RESET_KEY", "")
    if not expected_key or not secrets.compare_digest(request.admin_key, expected_key):
        raise HTTPException(status_code=403, detail="Invalid admin key")

    user = db.query(User).filter(func.lower(User.email) == request.email.lower()).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    from auth.account_lockout import unlock_account
    unlock_account(db, user)

    return {
        "success": True,
        "message": f"Account unlocked for {request.email}",
    }


# =============================================================================
# ADMIN UTILITY ROUTES
# =============================================================================

@router.post("/api/v1/admin/kill-idle-connections")
async def kill_idle_connections(current_user=Depends(get_current_user_dep())):
    """Emergency endpoint to kill idle database connections. Admin only."""
    if not getattr(current_user, 'permission_role', None) or current_user.permission_role not in ('admin', 'site_admin'):
        raise HTTPException(status_code=403, detail="Admin access required")

    # Enforce MFA for admin users (Enterprise Security - Domain 4)
    from utils.auth import require_admin_mfa
    require_admin_mfa(current_user)
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
async def normalize_loan_stages(current_user=Depends(get_current_user_dep()), db: Session = Depends(get_db)):
    """Normalize all loan stage values to uppercase. Fixes mixed-case data from legacy imports. Admin only."""
    if not getattr(current_user, 'permission_role', None) or current_user.permission_role not in ('admin', 'site_admin'):
        raise HTTPException(status_code=403, detail="Admin access required")

    # Enforce MFA for admin users (Enterprise Security - Domain 4)
    from utils.auth import require_admin_mfa
    require_admin_mfa(current_user)
    try:
        stage_map = {
            'Application': 'APPLICATION',
            'Disclosed': 'DISCLOSED',
            'Processing': 'PROCESSING',
            'In Processing': 'PROCESSING',
            'In Process': 'PROCESSING',
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
    # Rate limit registration attempts — per-minute AND per-hour windows
    client_ip = _get_real_client_ip(http_request)
    allowed, retry_after = _check_auth_rate_limit_multi(client_ip, [
        (_AUTH_RATE_MAX_REGISTER, _AUTH_RATE_WINDOW, "register"),
        (_AUTH_RATE_MAX_REGISTER_HOUR, _AUTH_RATE_WINDOW_HOUR, "register_hour"),
    ])
    if not allowed:
        logger.warning(f"Registration rate limit exceeded for {client_ip}")
        _raise_rate_limit(retry_after, "Too many requests. Please try again later.")

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

        # Validate password strength (Enterprise Security - Domain 4)
        from utils.auth import validate_password_strength
        password_violations = validate_password_strength(request.password)
        if password_violations:
            raise HTTPException(
                status_code=400,
                detail=f"Password does not meet security requirements: {'; '.join(password_violations)}"
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
        from utils.auth import require_admin, require_admin_mfa
        require_admin(current_user)
        require_admin_mfa(current_user)

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
        from utils.auth import require_admin, require_admin_mfa
        require_admin(current_user)
        require_admin_mfa(current_user)

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
    """No-op — push notification routes are now registered by
    routes/push_notification_routes.py via setup_push_routes().

    This function is kept as a stub so existing callers
    (setup_auth_routes) do not break.
    """
    pass


# =============================================================================
# ADMIN SETUP ROUTES
# =============================================================================

@router.post("/api/v1/setup-admin")
async def setup_admin_user(
    http_request: Request,
    admin_key: str = Header(..., alias="X-Admin-Key", description="Admin API key for authorization"),
    db: Session = Depends(get_db),
):
    """
    One-time setup: Create or reset admin user password.
    Requires ADMIN_API_KEY and ADMIN_SETUP_PASSWORD env vars.
    """
    # Rate limit admin setup — 3/hour per IP
    client_ip = _get_real_client_ip(http_request)
    if not _check_auth_rate_limit(client_ip, _AUTH_RATE_MAX_SETUP_ADMIN, _AUTH_RATE_WINDOW_HOUR, "setup_admin"):
        logger.warning(f"Setup-admin rate limit exceeded for {client_ip}")
        _raise_rate_limit(_AUTH_RATE_WINDOW_HOUR, "Too many requests. Please try again later.")

    import os as _os
    _ADMIN_API_KEY = _os.getenv("ADMIN_API_KEY")
    if not _ADMIN_API_KEY or admin_key != _ADMIN_API_KEY:
        raise HTTPException(status_code=403, detail="Forbidden")

    admin_email = "admin@perenniaai.com"
    admin_setup_password = _os.getenv("ADMIN_SETUP_PASSWORD")
    if not admin_setup_password:
        raise HTTPException(status_code=500, detail="ADMIN_SETUP_PASSWORD env var not set")

    try:
        import bcrypt as _bcrypt
        new_hash = _bcrypt.hashpw(admin_setup_password.encode(), _bcrypt.gensalt()).decode()

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

        # Enforce MFA for admin users (Enterprise Security - Domain 4)
        from utils.auth import require_admin_mfa
        require_admin_mfa(current_user)

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

        # Enforce MFA for admin users (Enterprise Security - Domain 4)
        from utils.auth import require_admin_mfa
        require_admin_mfa(current_user)

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
