"""
Borrower Social Authentication Routes

Handles OAuth flows for borrowers to:
1. Sign in with Google, Apple, Facebook, LinkedIn
2. Create or resume mortgage applications
3. Capture consent for communication and marketing

This is separate from internal user authentication (LO/staff login).
"""

from fastapi import APIRouter, Request, HTTPException, Depends, Query, Body, UploadFile, File
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
import httpx
from datetime import datetime, timedelta, timezone
import uuid
import secrets
import logging
import jwt
import json
import tempfile
from urllib.parse import urlencode, quote
import os
from typing import Optional, Any, Dict
from pydantic import BaseModel, EmailStr

import time
from collections import defaultdict

from database import get_db
from email_service import email_service

# Rate limiting for public borrower endpoints
_borrower_rate_store: dict = defaultdict(list)
_BORROWER_RATE_WINDOW = 3600  # 1 hour
_BORROWER_RATE_MAX = 5  # max requests per window per IP
_BORROWER_RATE_MAX_KEYS = 10000

# Per-email rate limiting for OAuth/login attempts
_borrower_email_rate_store: Dict[str, list] = defaultdict(list)
_BORROWER_EMAIL_RATE_MAX = 10  # max 10 OAuth attempts per email per hour


def _get_client_ip(request) -> str:
    """Extract real client IP, accounting for reverse proxy."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _check_borrower_rate_limit(client_ip: str) -> bool:
    """Check if client IP is within rate limit for borrower auth endpoints."""
    now = time.time()
    key = f"borrower:{client_ip}"
    _borrower_rate_store[key] = [t for t in _borrower_rate_store[key] if now - t < _BORROWER_RATE_WINDOW]
    if len(_borrower_rate_store) > _BORROWER_RATE_MAX_KEYS:
        stale = [k for k, v in _borrower_rate_store.items() if not v or now - v[-1] > _BORROWER_RATE_WINDOW]
        for k in stale:
            del _borrower_rate_store[k]
    if len(_borrower_rate_store[key]) >= _BORROWER_RATE_MAX:
        return False
    _borrower_rate_store[key].append(now)
    return True


def _check_email_rate_limit(email: str) -> bool:
    """Check if email has exceeded OAuth attempt limit."""
    now = time.time()
    key = f"email:{email.lower()}"
    _borrower_email_rate_store[key] = [t for t in _borrower_email_rate_store[key] if now - t < 3600]
    if len(_borrower_email_rate_store[key]) >= _BORROWER_EMAIL_RATE_MAX:
        return False
    _borrower_email_rate_store[key].append(now)
    return True
import hmac
import hashlib


def _sign_borrower_state(data: str) -> str:
    """Create HMAC-signed OAuth state to prevent CSRF/tampering."""
    key = os.getenv("SECRET_KEY", "").encode()
    sig = hmac.new(key, data.encode(), hashlib.sha256).hexdigest()[:16]
    return f"{data}|{sig}"


def _verify_borrower_state(signed_state: str) -> str:
    """Verify HMAC signature on OAuth state. Returns data or raises ValueError."""
    if len(signed_state) > 4096:
        raise ValueError("State parameter too large")
    if "|" not in signed_state:
        raise ValueError("Unsigned state parameter rejected")
    data, sig = signed_state.rsplit("|", 1)
    key = os.getenv("SECRET_KEY", "").encode()
    expected = hmac.new(key, data.encode(), hashlib.sha256).hexdigest()[:16]
    if not hmac.compare_digest(sig, expected):
        raise ValueError("Invalid state signature")
    return data

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/borrower-auth", tags=["borrower-auth"])


def _safe_redirect_path(redirect_to: Optional[str]) -> str:
    """Validate redirect_to is a safe relative path to prevent open redirect attacks."""
    if not redirect_to:
        return "/apply/start"
    # Must start with / and not with // (protocol-relative URL)
    if not redirect_to.startswith("/") or redirect_to.startswith("//"):
        return "/apply/start"
    # Block @ (credential-based URL bypass) and \ (backslash normalization)
    if "@" in redirect_to or "\\" in redirect_to:
        return "/apply/start"
    # Only allow paths under /apply/
    if not redirect_to.startswith("/apply/"):
        return "/apply/start"
    return redirect_to

# =============================================================================
# CONFIGURATION
# =============================================================================

FRONTEND_URL = os.getenv("FRONTEND_URL", "https://perenniaai.com")
JWT_SECRET = os.getenv("JWT_SECRET")
if not JWT_SECRET:
    logger.critical("JWT_SECRET environment variable is not set! Authentication will fail.")
    JWT_SECRET = None  # Will cause explicit failures rather than silent insecurity
JWT_ALGORITHM = "HS256"
BORROWER_TOKEN_EXPIRY_DAYS = 14

# Google OAuth
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
# Callback goes to backend, which then redirects to frontend with token
BACKEND_URL = os.getenv("BACKEND_URL", "https://app.perenniaai.com")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_BORROWER_REDIRECT_URI", f"{BACKEND_URL}/api/v1/borrower-auth/google/callback")

# Facebook OAuth
FACEBOOK_APP_ID = os.getenv("FACEBOOK_APP_ID", "")
FACEBOOK_APP_SECRET = os.getenv("FACEBOOK_APP_SECRET", "")
FACEBOOK_REDIRECT_URI = os.getenv("FACEBOOK_BORROWER_REDIRECT_URI", f"{BACKEND_URL}/api/v1/borrower-auth/facebook/callback")

# LinkedIn OAuth
LINKEDIN_CLIENT_ID = os.getenv("LINKEDIN_CLIENT_ID", "")
LINKEDIN_CLIENT_SECRET = os.getenv("LINKEDIN_CLIENT_SECRET", "")
LINKEDIN_REDIRECT_URI = os.getenv("LINKEDIN_BORROWER_REDIRECT_URI", f"{BACKEND_URL}/api/v1/borrower-auth/linkedin/callback")

# Apple Sign In
APPLE_CLIENT_ID = os.getenv("APPLE_CLIENT_ID", "")  # Service ID
APPLE_TEAM_ID = os.getenv("APPLE_TEAM_ID", "")
APPLE_KEY_ID = os.getenv("APPLE_KEY_ID", "")
APPLE_PRIVATE_KEY = os.getenv("APPLE_PRIVATE_KEY", "")  # Contents of .p8 file
APPLE_REDIRECT_URI = os.getenv("APPLE_BORROWER_REDIRECT_URI", f"{BACKEND_URL}/api/v1/borrower-auth/apple/callback")

# Cache for Apple's public signing keys (JWKS)
_apple_jwks_cache: Dict[str, Any] = {"keys": None, "fetched_at": 0.0}


async def _get_apple_public_key(kid: str):
    """Fetch Apple's JWKS and return the public key matching the given kid."""
    import time
    # Cache keys for 1 hour
    if _apple_jwks_cache["keys"] and time.time() - _apple_jwks_cache["fetched_at"] < 3600:
        keys = _apple_jwks_cache["keys"]
    else:
        async with httpx.AsyncClient() as client:
            resp = await client.get("https://appleid.apple.com/auth/keys", timeout=10.0)
            resp.raise_for_status()
            keys = resp.json()["keys"]
            _apple_jwks_cache["keys"] = keys
            _apple_jwks_cache["fetched_at"] = time.time()

    for key in keys:
        if key["kid"] == kid:
            return jwt.algorithms.RSAAlgorithm.from_jwk(key)

    return None


# =============================================================================
# MODELS
# =============================================================================

class ConsentCapture(BaseModel):
    communication_consent: bool = True
    marketing_consent: bool = False


class BorrowerProfile(BaseModel):
    email: EmailStr
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    profile_photo: Optional[str] = None
    provider: str
    provider_user_id: str
    raw_profile: Optional[dict] = None


class EmailLoginRequest(BaseModel):
    email: EmailStr
    first_name: Optional[str] = None
    last_name: Optional[str] = None


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def generate_borrower_token(borrower_id: str, email: str) -> str:
    """Generate a JWT token for borrower session."""
    payload = {
        "sub": borrower_id,
        "email": email,
        "type": "borrower",
        "aud": "borrower-portal",
        "jti": str(uuid.uuid4()),
        "exp": datetime.now(timezone.utc) + timedelta(days=BORROWER_TOKEN_EXPIRY_DAYS),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_borrower_token(token: str) -> Optional[dict]:
    """Verify and decode a borrower JWT token."""
    try:
        _borrower_aud = os.getenv("JWT_BORROWER_AUDIENCE", "perennia-borrower")
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM], audience=_borrower_aud, options={"verify_aud": True})
        if payload.get("type") != "borrower":
            return None
        # Check token blacklist (requires jti claim — older tokens without jti skip this check)
        jti = payload.get("jti")
        if jti:
            try:
                from auth.tokens import token_blacklist
                if token_blacklist.is_blacklisted(token):
                    logger.warning(f"Rejected blacklisted borrower token: {jti[:8]}...")
                    return None
            except Exception:
                pass
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def get_or_create_borrower(db: Session, profile: BorrowerProfile) -> dict:
    """Get existing borrower or create new one from social profile."""

    # Check if borrower exists by provider ID
    existing = db.execute(text("""
        SELECT id, email, first_name, last_name, profile_photo,
               communication_consent, marketing_consent, created_at
        FROM borrower_profiles
        WHERE provider = :provider AND provider_user_id = :provider_user_id
    """), {
        "provider": profile.provider,
        "provider_user_id": profile.provider_user_id
    }).fetchone()

    if existing:
        # Update profile photo if changed
        if profile.profile_photo and profile.profile_photo != existing[4]:
            db.execute(text("""
                UPDATE borrower_profiles SET profile_photo = :photo, updated_at = :updated_at
                WHERE id = :id
            """), {
                "photo": profile.profile_photo,
                "updated_at": datetime.now(timezone.utc),
                "id": existing[0]
            })
            db.commit()

        return {
            "id": existing[0],
            "email": existing[1],
            "first_name": existing[2],
            "last_name": existing[3],
            "profile_photo": profile.profile_photo or existing[4],
            "communication_consent": existing[5],
            "marketing_consent": existing[6],
            "is_new": False,
        }

    # Check if borrower exists by email (may have signed up with different provider)
    existing_email = db.execute(text("""
        SELECT id, email, first_name, last_name, profile_photo,
               communication_consent, marketing_consent
        FROM borrower_profiles
        WHERE email = :email
    """), {"email": profile.email}).fetchone()

    if existing_email:
        # Link this provider to existing account
        db.execute(text("""
            UPDATE borrower_profiles
            SET provider = :provider, provider_user_id = :provider_user_id,
                profile_photo = COALESCE(:photo, profile_photo),
                updated_at = :updated_at
            WHERE id = :id
        """), {
            "provider": profile.provider,
            "provider_user_id": profile.provider_user_id,
            "photo": profile.profile_photo,
            "updated_at": datetime.now(timezone.utc),
            "id": existing_email[0]
        })
        db.commit()

        return {
            "id": existing_email[0],
            "email": existing_email[1],
            "first_name": existing_email[2],
            "last_name": existing_email[3],
            "profile_photo": profile.profile_photo or existing_email[4],
            "communication_consent": existing_email[5],
            "marketing_consent": existing_email[6],
            "is_new": False,
        }

    # Create new borrower
    borrower_id = str(uuid.uuid4())
    db.execute(text("""
        INSERT INTO borrower_profiles (
            id, email, first_name, last_name, profile_photo,
            provider, provider_user_id, raw_profile,
            communication_consent, marketing_consent,
            created_at, updated_at
        ) VALUES (
            :id, :email, :first_name, :last_name, :profile_photo,
            :provider, :provider_user_id, :raw_profile,
            true, false, :created_at, :updated_at
        )
    """), {
        "id": borrower_id,
        "email": profile.email,
        "first_name": profile.first_name,
        "last_name": profile.last_name,
        "profile_photo": profile.profile_photo,
        "provider": profile.provider,
        "provider_user_id": profile.provider_user_id,
        "raw_profile": json.dumps(profile.raw_profile) if profile.raw_profile else None,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    })
    db.commit()

    return {
        "id": borrower_id,
        "email": profile.email,
        "first_name": profile.first_name,
        "last_name": profile.last_name,
        "profile_photo": profile.profile_photo,
        "communication_consent": True,
        "marketing_consent": False,
        "is_new": True,
    }


def generate_state_token() -> str:
    """Generate a secure state token for OAuth CSRF protection."""
    return secrets.token_urlsafe(32)


def send_magic_link_email(to_email: str, first_name: str, magic_link: str) -> bool:
    """Send magic link login email to borrower."""
    subject = "🔐 Your Secure Login Link - The Tim Loss Team"

    html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 600px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
        }}
        .container {{
            background: white;
            border-radius: 12px;
            padding: 40px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }}
        .logo {{
            text-align: center;
            margin-bottom: 30px;
        }}
        .logo h1 {{
            color: #218D8D;
            font-size: 28px;
            margin: 0;
        }}
        h2 {{
            color: #1a1a2e;
            margin-top: 0;
        }}
        p {{
            color: #4b5563;
            font-size: 16px;
        }}
        .btn-login {{
            display: inline-block;
            background: linear-gradient(135deg, #10b981 0%, #059669 100%);
            color: white !important;
            padding: 16px 48px;
            border-radius: 8px;
            text-decoration: none;
            font-weight: 600;
            font-size: 18px;
            margin: 24px 0;
        }}
        .btn-login:hover {{
            background: linear-gradient(135deg, #059669 0%, #047857 100%);
        }}
        .info-box {{
            background: #f0fdf4;
            border-left: 4px solid #10b981;
            padding: 16px;
            margin: 24px 0;
            border-radius: 4px;
        }}
        .info-box p {{
            margin: 0;
            color: #065f46;
        }}
        .expires {{
            font-size: 14px;
            color: #6b7280;
            background: #fef3c7;
            padding: 12px 16px;
            border-radius: 8px;
            text-align: center;
        }}
        .footer {{
            margin-top: 32px;
            padding-top: 24px;
            border-top: 1px solid #e5e7eb;
            text-align: center;
            color: #9ca3af;
            font-size: 13px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="logo">
            <h1>The Tim Loss Team</h1>
        </div>

        <h2>Hi {first_name},</h2>

        <p>Click the button below to securely sign in to your mortgage application:</p>

        <div style="text-align: center; margin: 30px 0;">
            <a href="{magic_link}" class="btn-login" style="display: inline-block; background-color: #10b981; color: #ffffff; padding: 16px 48px; border-radius: 8px; text-decoration: none; font-weight: 600; font-size: 18px;">Sign In to Your Application</a>
        </div>

        <div class="info-box">
            <p>🔒 This is a secure, one-time login link that works only for your email address.</p>
        </div>

        <div class="expires">
            ⏰ This link expires in <strong>24 hours</strong>
        </div>

        <p style="text-align: center; color: #6b7280; font-size: 14px; margin-top: 24px;">
            Or copy and paste this link:<br>
            <a href="{magic_link}" style="color: #10b981; word-break: break-all;">{magic_link}</a>
        </p>

        <div class="footer">
            <p>If you didn't request this email, you can safely ignore it.</p>
            <p>This email was sent by The Tim Loss Team</p>
        </div>
    </div>
</body>
</html>
"""

    plain_text = f"""
Hi {first_name},

Click the link below to securely sign in to your mortgage application:

{magic_link}

This is a secure, one-time login link that expires in 24 hours.

If you didn't request this email, you can safely ignore it.

- The Tim Loss Team
"""

    try:
        return email_service.send_html_email(
            to_email=to_email,
            subject=subject,
            html_body=html_body,
            plain_text_body=plain_text
        )
    except Exception as e:
        logger.error(f"Failed to send magic link email: {e}")
        return False


# =============================================================================
# GOOGLE OAUTH
# =============================================================================

@router.get("/google/connect")
async def google_connect(
    request: Request,
    redirect_to: Optional[str] = Query(None, description="Where to redirect after auth"),
    lo_id: Optional[str] = Query(None, description="Loan officer ID for attribution"),
):
    """Initiate Google OAuth flow for borrower."""
    client_ip = _get_client_ip(request)
    if not _check_borrower_rate_limit(client_ip):
        raise HTTPException(status_code=429, detail="Too many requests. Please try again later.")

    if not GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=500, detail="Google OAuth not configured")

    state_data = json.dumps({
        "csrf": generate_state_token(),
        "redirect_to": redirect_to,
        "lo_id": lo_id,
    })
    state = _sign_borrower_state(state_data)

    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "offline",
        "prompt": "select_account",
    }

    auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"
    return {"auth_url": auth_url}


@router.get("/google/callback")
async def google_callback(
    code: str = Query(...),
    state: str = Query(...),
    error: str = Query(None),
    db: Session = Depends(get_db),
):
    """Handle Google OAuth callback."""
    if error:
        logger.error(f"Google OAuth error: {error}")
        return RedirectResponse(url=f"{FRONTEND_URL}/apply/login?error={error}")

    try:
        verified = _verify_borrower_state(state)
        state_data = json.loads(verified)
    except (json.JSONDecodeError, TypeError, ValueError) as e:
        logger.warning(f"Google OAuth invalid state (possible CSRF): {e}")
        return JSONResponse(status_code=400, content={"error": "Invalid OAuth state parameter"})

    try:
        # Exchange code for tokens
        async with httpx.AsyncClient() as client:
            token_response = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": GOOGLE_CLIENT_ID,
                    "client_secret": GOOGLE_CLIENT_SECRET,
                    "code": code,
                    "redirect_uri": GOOGLE_REDIRECT_URI,
                    "grant_type": "authorization_code",
                },
                timeout=30.0,
            )

            if token_response.status_code != 200:
                logger.error(f"Google token exchange failed: HTTP {token_response.status_code}")
                return RedirectResponse(url=f"{FRONTEND_URL}/apply/login?error=token_exchange_failed")

            tokens = token_response.json()

        # Get user info
        async with httpx.AsyncClient() as client:
            userinfo_response = await client.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {tokens['access_token']}"},
                timeout=10.0,
            )

            if userinfo_response.status_code != 200:
                return RedirectResponse(url=f"{FRONTEND_URL}/apply/login?error=userinfo_failed")

            userinfo = userinfo_response.json()

        # Create borrower profile
        profile = BorrowerProfile(
            email=userinfo["email"],
            first_name=userinfo.get("given_name"),
            last_name=userinfo.get("family_name"),
            profile_photo=userinfo.get("picture"),
            provider="google",
            provider_user_id=userinfo["id"],
            raw_profile=userinfo,
        )

        borrower = get_or_create_borrower(db, profile)
        token = generate_borrower_token(borrower["id"], borrower["email"])

        # Log the authentication event
        db.execute(text("""
            INSERT INTO borrower_auth_events (id, borrower_id, event_type, provider, ip_address, created_at)
            VALUES (:id, :borrower_id, 'login', 'google', :ip, :created_at)
        """), {
            "id": str(uuid.uuid4()),
            "borrower_id": borrower["id"],
            "ip": None,  # Would capture from request in production
            "created_at": datetime.now(timezone.utc),
        })
        db.commit()

        # Redirect with token
        redirect_to = _safe_redirect_path(state_data.get("redirect_to"))
        lo_id = state_data.get("lo_id")

        redirect_url = f"{FRONTEND_URL}{redirect_to}?token={token}"
        if lo_id:
            redirect_url += f"&lo_id={lo_id}"
        if borrower["is_new"]:
            redirect_url += "&new=1"

        return RedirectResponse(url=redirect_url)

    except Exception as e:
        logger.error(f"Google OAuth error: {e}")
        return RedirectResponse(url=f"{FRONTEND_URL}/apply/login?error=auth_failed")


# =============================================================================
# FACEBOOK OAUTH
# =============================================================================

@router.get("/facebook/connect")
async def facebook_connect(
    request: Request,
    redirect_to: Optional[str] = Query(None),
    lo_id: Optional[str] = Query(None),
):
    """Initiate Facebook OAuth flow for borrower."""
    client_ip = _get_client_ip(request)
    if not _check_borrower_rate_limit(client_ip):
        raise HTTPException(status_code=429, detail="Too many requests. Please try again later.")

    if not FACEBOOK_APP_ID:
        raise HTTPException(status_code=500, detail="Facebook OAuth not configured")

    state_data = json.dumps({
        "csrf": generate_state_token(),
        "redirect_to": redirect_to,
        "lo_id": lo_id,
    })
    state = _sign_borrower_state(state_data)

    params = {
        "client_id": FACEBOOK_APP_ID,
        "redirect_uri": FACEBOOK_REDIRECT_URI,
        "state": state,
        "scope": "email,public_profile",
        "response_type": "code",
    }

    auth_url = f"https://www.facebook.com/v18.0/dialog/oauth?{urlencode(params)}"
    return {"auth_url": auth_url}


@router.get("/facebook/callback")
async def facebook_callback(
    code: str = Query(...),
    state: str = Query(...),
    error: str = Query(None),
    db: Session = Depends(get_db),
):
    """Handle Facebook OAuth callback."""
    if error:
        logger.error(f"Facebook OAuth error: {error}")
        return RedirectResponse(url=f"{FRONTEND_URL}/apply/login?error={error}")

    try:
        verified = _verify_borrower_state(state)
        state_data = json.loads(verified)
    except (json.JSONDecodeError, TypeError, ValueError) as e:
        logger.warning(f"Facebook OAuth invalid state (possible CSRF): {e}")
        return JSONResponse(status_code=400, content={"error": "Invalid OAuth state parameter"})

    try:
        # Exchange code for token
        async with httpx.AsyncClient() as client:
            token_response = await client.get(
                "https://graph.facebook.com/v18.0/oauth/access_token",
                params={
                    "client_id": FACEBOOK_APP_ID,
                    "client_secret": FACEBOOK_APP_SECRET,
                    "code": code,
                    "redirect_uri": FACEBOOK_REDIRECT_URI,
                },
                timeout=30.0,
            )

            if token_response.status_code != 200:
                logger.error(f"Facebook token exchange failed: HTTP {token_response.status_code}")
                return RedirectResponse(url=f"{FRONTEND_URL}/apply/login?error=token_exchange_failed")

            tokens = token_response.json()

        # Get user info
        async with httpx.AsyncClient() as client:
            userinfo_response = await client.get(
                "https://graph.facebook.com/me",
                params={
                    "fields": "id,email,first_name,last_name,picture.type(large)",
                    "access_token": tokens["access_token"],
                },
                timeout=10.0,
            )

            if userinfo_response.status_code != 200:
                return RedirectResponse(url=f"{FRONTEND_URL}/apply/login?error=userinfo_failed")

            userinfo = userinfo_response.json()

        # Extract profile photo URL
        profile_photo = None
        if "picture" in userinfo and "data" in userinfo["picture"]:
            profile_photo = userinfo["picture"]["data"].get("url")

        profile = BorrowerProfile(
            email=userinfo.get("email", f"{userinfo['id']}@facebook.com"),
            first_name=userinfo.get("first_name"),
            last_name=userinfo.get("last_name"),
            profile_photo=profile_photo,
            provider="facebook",
            provider_user_id=userinfo["id"],
            raw_profile=userinfo,
        )

        borrower = get_or_create_borrower(db, profile)
        token = generate_borrower_token(borrower["id"], borrower["email"])

        # Log event
        db.execute(text("""
            INSERT INTO borrower_auth_events (id, borrower_id, event_type, provider, created_at)
            VALUES (:id, :borrower_id, 'login', 'facebook', :created_at)
        """), {
            "id": str(uuid.uuid4()),
            "borrower_id": borrower["id"],
            "created_at": datetime.now(timezone.utc),
        })
        db.commit()

        redirect_to = _safe_redirect_path(state_data.get("redirect_to"))
        lo_id = state_data.get("lo_id")

        redirect_url = f"{FRONTEND_URL}{redirect_to}?token={token}"
        if lo_id:
            redirect_url += f"&lo_id={lo_id}"
        if borrower["is_new"]:
            redirect_url += "&new=1"

        return RedirectResponse(url=redirect_url)

    except Exception as e:
        logger.error(f"Facebook OAuth error: {e}")
        return RedirectResponse(url=f"{FRONTEND_URL}/apply/login?error=auth_failed")


# =============================================================================
# LINKEDIN OAUTH
# =============================================================================

@router.get("/linkedin/connect")
async def linkedin_connect(
    request: Request,
    redirect_to: Optional[str] = Query(None),
    lo_id: Optional[str] = Query(None),
):
    """Initiate LinkedIn OAuth flow for borrower."""
    client_ip = _get_client_ip(request)
    if not _check_borrower_rate_limit(client_ip):
        raise HTTPException(status_code=429, detail="Too many requests. Please try again later.")

    if not LINKEDIN_CLIENT_ID:
        raise HTTPException(status_code=500, detail="LinkedIn OAuth not configured")

    state_data = json.dumps({
        "csrf": generate_state_token(),
        "redirect_to": redirect_to,
        "lo_id": lo_id,
    })
    state = _sign_borrower_state(state_data)

    params = {
        "response_type": "code",
        "client_id": LINKEDIN_CLIENT_ID,
        "redirect_uri": LINKEDIN_REDIRECT_URI,
        "state": state,
        "scope": "openid profile email",
    }

    auth_url = f"https://www.linkedin.com/oauth/v2/authorization?{urlencode(params)}"
    return {"auth_url": auth_url}


@router.get("/linkedin/callback")
async def linkedin_callback(
    code: str = Query(...),
    state: str = Query(...),
    error: str = Query(None),
    db: Session = Depends(get_db),
):
    """Handle LinkedIn OAuth callback."""
    if error:
        logger.error(f"LinkedIn OAuth error: {error}")
        return RedirectResponse(url=f"{FRONTEND_URL}/apply/login?error={error}")

    try:
        verified = _verify_borrower_state(state)
        state_data = json.loads(verified)
    except (json.JSONDecodeError, TypeError, ValueError) as e:
        logger.warning(f"LinkedIn OAuth invalid state (possible CSRF): {e}")
        return JSONResponse(status_code=400, content={"error": "Invalid OAuth state parameter"})

    try:
        # Exchange code for token
        async with httpx.AsyncClient() as client:
            token_response = await client.post(
                "https://www.linkedin.com/oauth/v2/accessToken",
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": LINKEDIN_REDIRECT_URI,
                    "client_id": LINKEDIN_CLIENT_ID,
                    "client_secret": LINKEDIN_CLIENT_SECRET,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=30.0,
            )

            if token_response.status_code != 200:
                logger.error(f"LinkedIn token exchange failed: HTTP {token_response.status_code}")
                return RedirectResponse(url=f"{FRONTEND_URL}/apply/login?error=token_exchange_failed")

            tokens = token_response.json()

        # Get user info using OpenID Connect userinfo endpoint
        async with httpx.AsyncClient() as client:
            userinfo_response = await client.get(
                "https://api.linkedin.com/v2/userinfo",
                headers={"Authorization": f"Bearer {tokens['access_token']}"},
                timeout=10.0,
            )

            if userinfo_response.status_code != 200:
                return RedirectResponse(url=f"{FRONTEND_URL}/apply/login?error=userinfo_failed")

            userinfo = userinfo_response.json()

        profile = BorrowerProfile(
            email=userinfo.get("email", f"{userinfo['sub']}@linkedin.com"),
            first_name=userinfo.get("given_name"),
            last_name=userinfo.get("family_name"),
            profile_photo=userinfo.get("picture"),
            provider="linkedin",
            provider_user_id=userinfo["sub"],
            raw_profile=userinfo,
        )

        borrower = get_or_create_borrower(db, profile)
        token = generate_borrower_token(borrower["id"], borrower["email"])

        # Log event
        db.execute(text("""
            INSERT INTO borrower_auth_events (id, borrower_id, event_type, provider, created_at)
            VALUES (:id, :borrower_id, 'login', 'linkedin', :created_at)
        """), {
            "id": str(uuid.uuid4()),
            "borrower_id": borrower["id"],
            "created_at": datetime.now(timezone.utc),
        })
        db.commit()

        redirect_to = _safe_redirect_path(state_data.get("redirect_to"))
        lo_id = state_data.get("lo_id")

        redirect_url = f"{FRONTEND_URL}{redirect_to}?token={token}"
        if lo_id:
            redirect_url += f"&lo_id={lo_id}"
        if borrower["is_new"]:
            redirect_url += "&new=1"

        return RedirectResponse(url=redirect_url)

    except Exception as e:
        logger.error(f"LinkedIn OAuth error: {e}")
        return RedirectResponse(url=f"{FRONTEND_URL}/apply/login?error=auth_failed")


# =============================================================================
# APPLE SIGN IN
# =============================================================================

def generate_apple_client_secret():
    """Generate Apple client secret JWT."""
    if not all([APPLE_TEAM_ID, APPLE_KEY_ID, APPLE_PRIVATE_KEY, APPLE_CLIENT_ID]):
        return None

    headers = {
        "alg": "ES256",
        "kid": APPLE_KEY_ID,
    }

    payload = {
        "iss": APPLE_TEAM_ID,
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(days=180),
        "aud": "https://appleid.apple.com",
        "sub": APPLE_CLIENT_ID,
    }

    return jwt.encode(payload, APPLE_PRIVATE_KEY, algorithm="ES256", headers=headers)


@router.get("/apple/connect")
async def apple_connect(
    request: Request,
    redirect_to: Optional[str] = Query(None),
    lo_id: Optional[str] = Query(None),
):
    """Initiate Apple Sign In flow for borrower."""
    client_ip = _get_client_ip(request)
    if not _check_borrower_rate_limit(client_ip):
        raise HTTPException(status_code=429, detail="Too many requests. Please try again later.")

    if not APPLE_CLIENT_ID:
        raise HTTPException(status_code=500, detail="Apple Sign In not configured")

    state_data = json.dumps({
        "csrf": generate_state_token(),
        "redirect_to": redirect_to,
        "lo_id": lo_id,
    })
    state = _sign_borrower_state(state_data)

    params = {
        "client_id": APPLE_CLIENT_ID,
        "redirect_uri": APPLE_REDIRECT_URI,
        "response_type": "code id_token",
        "scope": "name email",
        "response_mode": "form_post",
        "state": state,
    }

    auth_url = f"https://appleid.apple.com/auth/authorize?{urlencode(params)}"
    return {"auth_url": auth_url}


@router.post("/apple/callback")
async def apple_callback(
    request: Request,
    db: Session = Depends(get_db),
):
    """Handle Apple Sign In callback (uses form_post)."""
    form = await request.form()

    code = form.get("code")
    state = form.get("state", "{}")
    id_token = form.get("id_token")
    user_data = form.get("user")  # Only sent on first authorization
    error = form.get("error")

    if error:
        logger.error(f"Apple Sign In error: {error}")
        return RedirectResponse(url=f"{FRONTEND_URL}/apply/login?error={error}")

    try:
        verified = _verify_borrower_state(state)
        state_data = json.loads(verified)
    except (json.JSONDecodeError, TypeError, ValueError) as e:
        logger.warning(f"Apple OAuth invalid state (possible CSRF): {e}")
        return JSONResponse(status_code=400, content={"error": "Invalid OAuth state parameter"})

    try:
        # Generate client secret
        client_secret = generate_apple_client_secret()
        if not client_secret:
            return RedirectResponse(url=f"{FRONTEND_URL}/apply/login?error=apple_not_configured")

        # Exchange code for tokens
        async with httpx.AsyncClient() as client:
            token_response = await client.post(
                "https://appleid.apple.com/auth/token",
                data={
                    "client_id": APPLE_CLIENT_ID,
                    "client_secret": client_secret,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": APPLE_REDIRECT_URI,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=30.0,
            )

            if token_response.status_code != 200:
                logger.error(f"Apple token exchange failed: HTTP {token_response.status_code}")
                return RedirectResponse(url=f"{FRONTEND_URL}/apply/login?error=token_exchange_failed")

            tokens = token_response.json()

        # Verify and decode Apple ID token
        token_header = jwt.get_unverified_header(tokens["id_token"])
        apple_public_key = await _get_apple_public_key(token_header.get("kid", ""))
        if not apple_public_key:
            logger.error(f"Apple public key not found for kid: {token_header.get('kid')}")
            return RedirectResponse(url=f"{FRONTEND_URL}/apply/login?error=token_verification_failed")

        id_token_payload = jwt.decode(
            tokens["id_token"],
            key=apple_public_key,
            algorithms=[token_header.get("alg", "RS256")],
            audience=APPLE_CLIENT_ID,
            issuer="https://appleid.apple.com",
        )

        # Parse user data if provided (first sign-in only)
        first_name = None
        last_name = None
        if user_data:
            try:
                user_info = json.loads(user_data)
                if "name" in user_info:
                    first_name = user_info["name"].get("firstName")
                    last_name = user_info["name"].get("lastName")
            except (json.JSONDecodeError, TypeError, KeyError):
                pass  # Apple user data parsing failed, continue without name

        email = id_token_payload.get("email", f"{id_token_payload['sub']}@privaterelay.appleid.com")

        profile = BorrowerProfile(
            email=email,
            first_name=first_name,
            last_name=last_name,
            profile_photo=None,  # Apple doesn't provide profile photos
            provider="apple",
            provider_user_id=id_token_payload["sub"],
            raw_profile=id_token_payload,
        )

        borrower = get_or_create_borrower(db, profile)
        token = generate_borrower_token(borrower["id"], borrower["email"])

        # Log event
        db.execute(text("""
            INSERT INTO borrower_auth_events (id, borrower_id, event_type, provider, created_at)
            VALUES (:id, :borrower_id, 'login', 'apple', :created_at)
        """), {
            "id": str(uuid.uuid4()),
            "borrower_id": borrower["id"],
            "created_at": datetime.now(timezone.utc),
        })
        db.commit()

        redirect_to = _safe_redirect_path(state_data.get("redirect_to"))
        lo_id = state_data.get("lo_id")

        redirect_url = f"{FRONTEND_URL}{redirect_to}?token={token}"
        if lo_id:
            redirect_url += f"&lo_id={lo_id}"
        if borrower["is_new"]:
            redirect_url += "&new=1"

        return RedirectResponse(url=redirect_url, status_code=303)

    except Exception as e:
        logger.error(f"Apple Sign In error: {e}")
        return RedirectResponse(url=f"{FRONTEND_URL}/apply/login?error=auth_failed")


# =============================================================================
# EMAIL FALLBACK (Magic Link / Traditional)
# =============================================================================

@router.post("/email/request")
async def request_email_login(
    http_request: Request,
    request: EmailLoginRequest,
    db: Session = Depends(get_db),
):
    """Request email-based login (sends magic link)."""

    # Rate limit magic link requests by IP
    client_ip = _get_client_ip(http_request)
    if not _check_borrower_rate_limit(client_ip):
        logger.warning(f"Magic link rate limit exceeded for IP {client_ip}")
        raise HTTPException(status_code=429, detail="Too many requests. Please try again later.")

    # Rate limit by email to prevent abuse targeting a single address
    if not _check_email_rate_limit(request.email):
        logger.warning(f"Magic link rate limit exceeded for email {request.email}")
        raise HTTPException(status_code=429, detail="Too many requests for this email. Please try again later.")

    # Generate magic link token
    magic_token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=24)

    # Check if borrower exists
    existing = db.execute(text("""
        SELECT id FROM borrower_profiles WHERE email = :email
    """), {"email": request.email}).fetchone()

    borrower_id = existing[0] if existing else str(uuid.uuid4())

    if not existing:
        # Create new borrower profile
        db.execute(text("""
            INSERT INTO borrower_profiles (
                id, email, first_name, last_name, provider, provider_user_id,
                communication_consent, marketing_consent, created_at, updated_at
            ) VALUES (
                :id, :email, :first_name, :last_name, 'email', :email,
                true, false, :created_at, :updated_at
            )
        """), {
            "id": borrower_id,
            "email": request.email,
            "first_name": request.first_name,
            "last_name": request.last_name,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        })

    # Store magic link token
    db.execute(text("""
        INSERT INTO borrower_magic_links (id, borrower_id, token, expires_at, created_at)
        VALUES (:id, :borrower_id, :token, :expires_at, :created_at)
    """), {
        "id": str(uuid.uuid4()),
        "borrower_id": borrower_id,
        "token": magic_token,
        "expires_at": expires_at,
        "created_at": datetime.now(timezone.utc),
    })
    db.commit()

    # Magic link goes to frontend which redirects to backend API for verification
    # HARDCODED to ensure correct URL - do not change
    magic_link = f"https://www.perenniaai.com/apply/verify?token={magic_token}"

    # Send the magic link email
    first_name = request.first_name or "there"
    email_sent = send_magic_link_email(request.email, first_name, magic_link)

    if not email_sent:
        logger.error("Failed to send magic link email")
        # Still return success since link was created - user can request again

    logger.info("Magic link created successfully")

    return {
        "success": True,
        "message": "Check your email for a login link",
    }


@router.get("/email/verify")
async def verify_email_login(
    token: str = Query(...),
    db: Session = Depends(get_db),
):
    """Verify magic link and complete login."""

    # Atomic token consumption: UPDATE ... WHERE used_at IS NULL prevents race conditions
    now = datetime.now(timezone.utc)
    update_result = db.execute(text("""
        UPDATE borrower_magic_links
        SET used_at = :used_at
        WHERE token = :token AND used_at IS NULL
        RETURNING borrower_id, expires_at
    """), {"token": token, "used_at": now})
    updated_row = update_result.fetchone()

    if not updated_row:
        # Either token doesn't exist or was already used
        check = db.execute(text("""
            SELECT used_at FROM borrower_magic_links WHERE token = :token
        """), {"token": token}).fetchone()
        if check and check[0]:
            return RedirectResponse(url=f"{FRONTEND_URL}/apply/login?error=link_already_used")
        return RedirectResponse(url=f"{FRONTEND_URL}/apply/login?error=invalid_link")

    borrower_id, expires_at = updated_row
    borrower_id = str(borrower_id)

    if expires_at < now:
        return RedirectResponse(url=f"{FRONTEND_URL}/apply/login?error=link_expired")

    # Get email for JWT
    email_row = db.execute(text("""
        SELECT email FROM borrower_profiles WHERE id = :id
    """), {"id": borrower_id}).fetchone()
    email = email_row[0] if email_row else None

    # Log event
    db.execute(text("""
        INSERT INTO borrower_auth_events (id, borrower_id, event_type, provider, created_at)
        VALUES (:id, :borrower_id, 'login', 'email', :created_at)
    """), {
        "id": str(uuid.uuid4()),
        "borrower_id": borrower_id,
        "created_at": datetime.now(timezone.utc),
    })
    db.commit()

    auth_token = generate_borrower_token(borrower_id, email)

    # Redirect to the actual purchase application with the auth token
    return RedirectResponse(url=f"{FRONTEND_URL}/apply/purchase?auth={auth_token}")


# =============================================================================
# CONSENT MANAGEMENT
# =============================================================================

@router.post("/consent")
async def update_consent(
    consent: ConsentCapture,
    request: Request,
    db: Session = Depends(get_db),
):
    """Update borrower consent preferences."""

    # Get borrower from auth header
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")

    token = auth_header.replace("Bearer ", "")
    payload = verify_borrower_token(token)

    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    borrower_id = payload["sub"]

    db.execute(text("""
        UPDATE borrower_profiles
        SET communication_consent = :comm, marketing_consent = :mktg, updated_at = :updated_at
        WHERE id = :id
    """), {
        "comm": consent.communication_consent,
        "mktg": consent.marketing_consent,
        "updated_at": datetime.now(timezone.utc),
        "id": borrower_id,
    })
    db.commit()

    return {"success": True, "consents": consent.dict()}


# =============================================================================
# SESSION MANAGEMENT
# =============================================================================

@router.get("/me")
async def get_current_borrower(
    request: Request,
    db: Session = Depends(get_db),
):
    """Get current borrower profile."""

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")

    token = auth_header.replace("Bearer ", "")
    payload = verify_borrower_token(token)

    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    borrower_id = payload["sub"]

    borrower = db.execute(text("""
        SELECT id, email, first_name, last_name, profile_photo,
               provider, communication_consent, marketing_consent, created_at
        FROM borrower_profiles
        WHERE id = :id
    """), {"id": borrower_id}).fetchone()

    if not borrower:
        raise HTTPException(status_code=404, detail="Borrower not found")

    # Get any existing applications
    applications = db.execute(text("""
        SELECT id, status, current_step, progress_percentage, created_at, updated_at
        FROM borrower_applications
        WHERE borrower_profile_id = :borrower_id
        ORDER BY updated_at DESC
    """), {"borrower_id": borrower_id}).fetchall()

    return {
        "id": borrower[0],
        "email": borrower[1],
        "first_name": borrower[2],
        "last_name": borrower[3],
        "profile_photo": borrower[4],
        "provider": borrower[5],
        "communication_consent": borrower[6],
        "marketing_consent": borrower[7],
        "created_at": borrower[8].isoformat() if borrower[8] else None,
        "applications": [
            {
                "id": app[0],
                "status": app[1],
                "current_step": app[2],
                "progress_percentage": app[3],
                "created_at": app[4].isoformat() if app[4] else None,
                "updated_at": app[5].isoformat() if app[5] else None,
            }
            for app in applications
        ],
    }


@router.post("/logout")
async def logout_borrower(request: Request):
    """Logout borrower (client should clear token)."""
    # Server-side logout is a no-op for JWT tokens
    # Could add token to blacklist for extra security
    return {"success": True, "message": "Logged out successfully"}


# =============================================================================
# AI FOLLOW-UP QUESTIONS
# =============================================================================

class FollowupCheckRequest(BaseModel):
    """Request to check if a field triggers follow-up questions."""
    field_name: str
    field_value: Any
    application_type: str = "purchase"
    existing_answers: Optional[Dict[str, Any]] = None

# Rebuild for Python 3.14 compatibility
FollowupCheckRequest.model_rebuild()


@router.post("/check-followup")
async def check_followup_trigger(request: FollowupCheckRequest):
    """
    Check if a field value triggers AI follow-up questions.

    Called when user answers certain questions to determine if
    clarifying questions are needed for complex situations.
    """
    from services.application_followup_service import application_followup_service

    try:
        # Check if this answer triggers follow-up
        trigger_info = application_followup_service.check_triggers(
            field_name=request.field_name,
            field_value=request.field_value,
            all_answers=request.existing_answers
        )

        if not trigger_info:
            return {
                "needs_followup": False,
                "questions": []
            }

        # Generate follow-up questions
        questions = application_followup_service.generate_followup_questions(
            trigger_info=trigger_info,
            application_type=request.application_type,
            existing_answers=request.existing_answers
        )

        return {
            "needs_followup": True,
            "trigger": trigger_info["trigger"],
            "context": trigger_info["context"],
            "questions": questions
        }

    except Exception as e:
        logger.error(f"Follow-up check failed: {e}")
        return {
            "needs_followup": False,
            "questions": [],
            "error": "Internal server error"
        }


@router.get("/followup-triggers")
async def get_followup_triggers():
    """Get all available follow-up triggers for reference."""
    from services.application_followup_service import application_followup_service

    return {
        "triggers": application_followup_service.get_all_triggers()
    }


# =============================================================================
# MORTGAGE STATEMENT PARSING
# =============================================================================

@router.post("/parse-mortgage-statement")
async def parse_mortgage_statement(
    file: UploadFile = File(...),
    borrower_name: Optional[str] = None,
):
    """
    Parse a mortgage statement document to extract loan information.

    This endpoint uses AI vision to analyze uploaded mortgage statements and
    extract key data like property address, current balance, monthly payment,
    interest rate, etc.

    Supports PDF, PNG, JPG, and JPEG files.

    Returns structured data that can be used to pre-populate refinance application forms.
    """
    from services.document_analysis_service import document_analysis_service

    # Validate file type
    allowed_types = ["application/pdf", "image/png", "image/jpeg", "image/jpg"]
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type: {file.content_type}. Allowed types: PDF, PNG, JPG"
        )

    # Validate file size (max 10MB)
    max_size = 10 * 1024 * 1024  # 10MB
    contents = await file.read()
    if len(contents) > max_size:
        raise HTTPException(
            status_code=400,
            detail="File too large. Maximum size is 10MB."
        )

    # Determine file extension
    ext_map = {
        "application/pdf": ".pdf",
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
    }
    file_ext = ext_map.get(file.content_type, ".pdf")

    # Save to temp file for processing
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp:
            tmp.write(contents)
            tmp_path = tmp.name

        # Parse the mortgage statement
        result = await document_analysis_service.parse_mortgage_statement(
            file_path=tmp_path,
            borrower_name=borrower_name,
        )

        # Clean up temp file
        import os
        os.unlink(tmp_path)

        if not result.get("success", False):
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": result.get("error", "Failed to parse mortgage statement"),
                    "data": {}
                }
            )

        # Map parsed data to form fields for the refinance application
        data = result.get("data", {})
        form_data = {
            # Property information
            "address": data.get("property_address"),
            "street": data.get("property_street"),
            "city": data.get("property_city"),
            "state": data.get("property_state"),
            "zip": data.get("property_zip"),

            # Loan details
            "mortgageBalance": data.get("principal_balance"),
            "monthlyPayment": data.get("monthly_payment"),
            "currentRate": data.get("interest_rate"),
            "loanDate": data.get("original_loan_date"),
            "currentTerm": data.get("loan_term_years"),

            # Lender info
            "lenderName": data.get("lender_name"),
            "loanNumber": data.get("loan_number"),

            # Payment breakdown
            "principalAndInterest": data.get("principal_and_interest"),
            "escrowPayment": data.get("escrow_payment"),
            "propertyTaxes": data.get("property_taxes_monthly"),
            "insurance": data.get("homeowners_insurance_monthly"),
            "pmi": data.get("pmi_monthly"),
            "hoa": data.get("hoa_monthly"),

            # Additional info
            "escrowBalance": data.get("escrow_balance"),
            "maturityDate": data.get("maturity_date"),
        }

        # Remove None values
        form_data = {k: v for k, v in form_data.items() if v is not None}

        return {
            "success": True,
            "confidence": result.get("confidence", 0),
            "document_verified": result.get("document_type_verified", False),
            "form_data": form_data,
            "warnings": result.get("warnings", []),
            "borrower_name_matches": result.get("borrower_name_matches"),
            "parsed_at": result.get("parsed_at"),
        }

    except Exception as e:
        logger.error(f"Error parsing mortgage statement: {e}")
        # Clean up temp file if it exists
        import os
        if 'tmp_path' in locals() and os.path.exists(tmp_path):
            os.unlink(tmp_path)
        logger.error(f"Error processing document: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Error processing document. Please try again."
        )


# =============================================================================
# APPLICATION SUBMISSION
# =============================================================================

class ApplicationSubmissionRequest(BaseModel):
    """Request model for application submission"""
    profileData: dict
    incomeData: dict
    assetData: dict
    propertyData: dict
    declarations: dict
    paymentEstimate: Optional[dict] = None
    goalsData: Optional[dict] = None  # Refinance goals data
    eConsentAgreed: bool
    creditAuthAgreed: bool
    loId: Optional[str] = None
    applicationType: Optional[str] = "purchase"  # 'purchase' or 'refinance'


@router.post("/submit-application")
async def submit_application(
    request: Request,
    submission: ApplicationSubmissionRequest,
    db: Session = Depends(get_db),
):
    """
    Submit completed application:
    1. Generate E-Consent PDF with signature
    2. Generate Credit Authorization PDF with signature
    3. Save documents to borrower's profile
    4. Generate Fannie Mae 3.4 file
    5. Email Fannie Mae file to loan officer
    """
    from services.application_submission_service import application_submission_service

    try:
        # Get client IP for signature
        client_ip = request.client.host if request.client else "Unknown"

        # Initialize PDF variables (may fail if reportlab not installed)
        econsent_pdf = None
        credit_auth_pdf = None
        fannie_mae_xml = None
        pdf_generation_error = None

        # Try to generate PDFs (non-critical - lead creation still works without them)
        application_summary_pdf = None
        try:
            # Prepare borrower data for PDFs
            borrower_data = {
                "firstName": submission.profileData.get("firstName", ""),
                "lastName": submission.profileData.get("lastName", ""),
                "email": submission.profileData.get("email", ""),
                "phone": submission.profileData.get("phone", ""),
                "ipAddress": client_ip,
            }

            # Generate PDFs
            econsent_pdf = application_submission_service.generate_econsent_pdf(borrower_data)
            credit_auth_pdf = application_submission_service.generate_credit_auth_pdf(borrower_data)

            # Generate Application Summary PDF with all Q&A data
            submission_data_for_pdf = {
                "profileData": submission.profileData,
                "incomeData": submission.incomeData,
                "assetData": submission.assetData,
                "propertyData": submission.propertyData,
                "declarations": submission.declarations,
            }
            application_summary_pdf = application_submission_service.generate_application_summary_pdf(submission_data_for_pdf)
        except Exception as pdf_error:
            logger.warning(f"PDF generation failed (non-critical): {pdf_error}")
            pdf_generation_error = str(pdf_error)

        # Prepare full application data for Fannie Mae 3.4
        application_data = {
            "firstName": submission.profileData.get("firstName", ""),
            "middleName": submission.profileData.get("middleName", ""),
            "lastName": submission.profileData.get("lastName", ""),
            "email": submission.profileData.get("email", ""),
            "phone": submission.profileData.get("phone", ""),
            "currentAddress": {
                "street": submission.profileData.get("address", ""),
                "city": submission.profileData.get("city", ""),
                "state": submission.profileData.get("state", ""),
                "zip": submission.profileData.get("zip", ""),
            },
            "employment": {
                "employerName": submission.incomeData.get("employerName", ""),
                "startDate": submission.incomeData.get("startDate", ""),
                "monthlyIncome": float(submission.incomeData.get("annualSalary", 0)) / 12 if submission.incomeData.get("annualSalary") else 0,
                "jobTitle": submission.incomeData.get("jobTitle", ""),
            },
            "annualIncome": submission.incomeData.get("annualSalary", 0),
            "assets": {
                "checking": submission.assetData.get("checking", 0),
                "savings": submission.assetData.get("savings", 0),
                "investments": submission.assetData.get("investments", 0),
                "giftAmount": submission.assetData.get("giftAmount", 0),
            },
            "declarations": {
                "citizenship": submission.declarations.get("citizenship", "us_citizen"),
                "occupancy": submission.propertyData.get("occupancy", "primary"),
                "firstTimeBuyer": submission.declarations.get("first_time_buyer", "no"),
            },
            "property": {
                "street": submission.propertyData.get("address", ""),
                "city": submission.propertyData.get("city", ""),
                "state": submission.propertyData.get("state", ""),
                "zip": submission.propertyData.get("zip", ""),
                "county": submission.propertyData.get("county", ""),
                "propertyType": submission.propertyData.get("propertyType", "Single Family"),
                "occupancy": submission.propertyData.get("occupancy", "primary"),
            },
            "loan": {
                "purpose": "Purchase",
                "loanAmount": float(submission.propertyData.get("purchasePrice", 0)) - float(submission.propertyData.get("downPayment", 0)),
                "purchasePrice": submission.propertyData.get("purchasePrice", 0),
                "downPayment": submission.propertyData.get("downPayment", 0),
                "amortizationType": "Fixed",
                "termMonths": 360,
            },
        }

        # Generate Fannie Mae 3.4 file (also non-critical)
        try:
            fannie_mae_xml = application_submission_service.generate_fannie_mae_34(application_data)
        except Exception as xml_error:
            logger.warning(f"Fannie Mae XML generation failed (non-critical): {xml_error}")
            fannie_mae_xml = None

        # Create borrower record if doesn't exist
        borrower_email = submission.profileData.get("email", "")
        borrower_name = f"{submission.profileData.get('firstName', '')} {submission.profileData.get('lastName', '')}"
        safe_borrower_name = borrower_name.replace(' ', '_').replace('/', '_').replace('\\', '_')

        # Check for existing borrower
        existing = db.execute(text("""
            SELECT id FROM borrower_profiles WHERE email = :email
        """), {"email": borrower_email}).fetchone()

        if existing:
            borrower_id = existing[0]
        else:
            borrower_id = str(uuid.uuid4())
            db.execute(text("""
                INSERT INTO borrower_profiles (id, email, first_name, last_name, provider, provider_user_id, created_at, updated_at)
                VALUES (:id, :email, :first_name, :last_name, 'application', :provider_user_id, :now, :now)
            """), {
                "id": borrower_id,
                "email": borrower_email,
                "first_name": submission.profileData.get("firstName", ""),
                "last_name": submission.profileData.get("lastName", ""),
                "provider_user_id": borrower_email,
                "now": datetime.now(timezone.utc),
            })

        # Prepare submission timestamp
        submission_date = datetime.now(timezone.utc)
        date_str = submission_date.strftime("%Y%m%d_%H%M%S")
        fannie_mae_bytes = fannie_mae_xml.encode('utf-8') if fannie_mae_xml else None

        # Get loan officer email and all team members to send Fannie Mae file
        lo_email = None
        team_emails = []
        if submission.loId:
            # Get LO email
            lo_result = db.execute(text("""
                SELECT email, organization_id FROM users WHERE id = :lo_id
            """), {"lo_id": submission.loId}).fetchone()
            if lo_result:
                lo_email = lo_result[0]
                org_id_for_team = lo_result[1]

                # Get all team members from the same organization
                if org_id_for_team:
                    team_result = db.execute(text("""
                        SELECT email FROM users
                        WHERE organization_id = :org_id
                        AND email IS NOT NULL
                        AND email != ''
                        AND is_active = true
                    """), {"org_id": org_id_for_team}).fetchall()
                    team_emails = [row[0] for row in team_result if row[0]]
                    logger.info(f"Found {len(team_emails)} team members to notify")

        # Fallback to default application email if no LO assigned
        if not lo_email:
            lo_email = os.getenv("DEFAULT_APPLICATION_EMAIL", "applications@perenniaai.com")
            logger.info(f"No LO assigned, using default email: {lo_email}")

        # Send email to loan officer with all application documents (non-critical)
        email_sent = False
        if lo_email and econsent_pdf and credit_auth_pdf and fannie_mae_bytes:
            try:
                import base64

                # Helper function to format declaration values for display
                def format_declaration(key, value):
                    """Format a declaration value to human-readable text."""
                    if value is None or value == '' or value == 'N/A':
                        return 'N/A'

                    # Value mappings for better readability
                    value_maps = {
                        # Borrower count
                        '1': 'Just me',
                        '2': '2 borrowers',
                        '3': '3 borrowers',
                        '4+': '4+ borrowers',
                        # Relationships
                        'spouse': 'Spouse',
                        'partner': 'Domestic Partner',
                        'relative': 'Relative',
                        'other': 'Other',
                        # Citizenship
                        'us_citizen': 'U.S. Citizen',
                        'permanent_resident': 'Permanent Resident',
                        'non_permanent_resident': 'Non-Permanent Resident',
                        'non_resident': 'Non-Resident Alien',
                        # Yes/No
                        'yes': 'Yes',
                        'no': 'No',
                        # Home status
                        'sold': 'Sold',
                        'second_home': 'Keeping as Second Home',
                        'rental': 'Converting to Rental',
                        'foreclosed': 'Foreclosed/Short Sale',
                        # Marital status
                        'married': 'Married',
                        'single': 'Single',
                        'divorced': 'Divorced',
                        'separated': 'Separated',
                        'widowed': 'Widowed',
                        # Support type
                        'alimony': 'Alimony',
                        'child_support': 'Child Support',
                        'both': 'Both',
                        'none': 'None',
                        # Veteran status
                        'active_duty': 'Active Duty',
                        'veteran': 'Veteran',
                        'reserves': 'Reserves/National Guard',
                        'surviving_spouse': 'Surviving Spouse',
                        # Self-employed
                        'side_business': 'Yes (Side Business)',
                        # Business types
                        'sole_proprietor': 'Sole Proprietor',
                        'llc': 'LLC',
                        's_corp': 'S-Corp',
                        'c_corp': 'C-Corp',
                        'partnership': 'Partnership',
                        # IRS status
                        'payment_plan': 'On Payment Plan',
                        # Credit app types
                        'auto': 'Auto Loan',
                        'credit_card': 'Credit Card',
                        'personal_loan': 'Personal Loan',
                        'mortgage': 'Mortgage',
                        # Gift donors
                        'parent': 'Parent',
                        'grandparent': 'Grandparent',
                        'sibling': 'Sibling',
                        'employer': 'Employer',
                        # Bankruptcy types
                        'chapter_7': 'Chapter 7',
                        'chapter_13': 'Chapter 13',
                        'chapter_12': 'Chapter 12',
                        # Bankruptcy status
                        'discharged': 'Discharged',
                        'open': 'Open/Active',
                        'dismissed': 'Dismissed',
                    }

                    str_value = str(value).lower()
                    if str_value in value_maps:
                        return value_maps[str_value]
                    # Title case for unknown values
                    return str(value).replace('_', ' ').title()

                def format_currency_value(value):
                    """Format a value as currency if it's a number."""
                    if value is None or value == '' or value == 'N/A':
                        return 'N/A'
                    try:
                        amount = float(value)
                        if amount > 0:
                            return f"${amount:,.0f}"
                        return 'N/A'
                    except (ValueError, TypeError):
                        return str(value) if value else 'N/A'

                # Calculate loan amount for email
                email_purchase_price = float(submission.propertyData.get('purchasePrice', 0) or 0)
                email_down_payment = float(submission.propertyData.get('downPayment', 0) or 0)
                email_loan_amount = email_purchase_price - email_down_payment
                email_ltv = (email_loan_amount / email_purchase_price * 100) if email_purchase_price > 0 else 0

                email_html = f"""
                <html>
                <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                    <div style="max-width: 700px; margin: 0 auto; padding: 20px;">
                        <h2 style="color: #218D8D; border-bottom: 2px solid #218D8D; padding-bottom: 10px;">New Mortgage Application Submitted</h2>

                        <h3 style="color: #218D8D; margin-top: 25px;">📋 PERSONAL INFORMATION</h3>
                        <table style="width: 100%; border-collapse: collapse; margin-bottom: 20px;">
                            <tr><td style="padding: 8px; border-bottom: 1px solid #eee; width: 40%;"><strong>Full Name:</strong></td><td style="padding: 8px; border-bottom: 1px solid #eee;">{borrower_name}</td></tr>
                            <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>Email:</strong></td><td style="padding: 8px; border-bottom: 1px solid #eee;">{borrower_email}</td></tr>
                            <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>Phone:</strong></td><td style="padding: 8px; border-bottom: 1px solid #eee;">{submission.profileData.get('phone', 'N/A')}</td></tr>
                            <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>Address:</strong></td><td style="padding: 8px; border-bottom: 1px solid #eee;">{submission.profileData.get('address', 'N/A')}</td></tr>
                            <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>City, State, ZIP:</strong></td><td style="padding: 8px; border-bottom: 1px solid #eee;">{submission.profileData.get('city', '')}, {submission.profileData.get('state', '')} {submission.profileData.get('zip', '')}</td></tr>
                        </table>

                        <h3 style="color: #218D8D; margin-top: 25px;">🏠 PROPERTY DETAILS</h3>
                        <table style="width: 100%; border-collapse: collapse; margin-bottom: 20px;">
                            <tr><td style="padding: 8px; border-bottom: 1px solid #eee; width: 40%;"><strong>Property Address:</strong></td><td style="padding: 8px; border-bottom: 1px solid #eee;">{submission.propertyData.get('address', 'N/A')}</td></tr>
                            <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>City, State, ZIP:</strong></td><td style="padding: 8px; border-bottom: 1px solid #eee;">{submission.propertyData.get('city', '')}, {submission.propertyData.get('state', '')} {submission.propertyData.get('zip', '')}</td></tr>
                            <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>Property Type:</strong></td><td style="padding: 8px; border-bottom: 1px solid #eee;">{submission.propertyData.get('propertyType', 'N/A')}</td></tr>
                            <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>Occupancy:</strong></td><td style="padding: 8px; border-bottom: 1px solid #eee;">{submission.propertyData.get('occupancy', 'Primary Residence')}</td></tr>
                            <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>Purchase Price:</strong></td><td style="padding: 8px; border-bottom: 1px solid #eee;">${email_purchase_price:,.0f}</td></tr>
                            <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>Down Payment:</strong></td><td style="padding: 8px; border-bottom: 1px solid #eee;">${email_down_payment:,.0f}</td></tr>
                            <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>Loan Amount:</strong></td><td style="padding: 8px; border-bottom: 1px solid #eee;">${email_loan_amount:,.0f}</td></tr>
                            <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>LTV:</strong></td><td style="padding: 8px; border-bottom: 1px solid #eee;">{email_ltv:.1f}%</td></tr>
                            <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>Loan Program:</strong></td><td style="padding: 8px; border-bottom: 1px solid #eee;">{submission.propertyData.get('loanProgram', 'Conventional')}</td></tr>
                        </table>

                        <h3 style="color: #218D8D; margin-top: 25px;">💼 EMPLOYMENT & INCOME</h3>
                        <table style="width: 100%; border-collapse: collapse; margin-bottom: 20px;">
                            <tr><td style="padding: 8px; border-bottom: 1px solid #eee; width: 40%;"><strong>Employer Name:</strong></td><td style="padding: 8px; border-bottom: 1px solid #eee;">{submission.incomeData.get('employerName', 'N/A')}</td></tr>
                            <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>Job Title:</strong></td><td style="padding: 8px; border-bottom: 1px solid #eee;">{submission.incomeData.get('jobTitle', 'N/A')}</td></tr>
                            <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>Employment Start Date:</strong></td><td style="padding: 8px; border-bottom: 1px solid #eee;">{submission.incomeData.get('startDate', 'N/A')}</td></tr>
                            <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>Annual Salary:</strong></td><td style="padding: 8px; border-bottom: 1px solid #eee;">${float(submission.incomeData.get('annualSalary', 0) or 0):,.0f}</td></tr>
                        </table>

                        <h3 style="color: #218D8D; margin-top: 25px;">💰 ASSETS</h3>
                        <table style="width: 100%; border-collapse: collapse; margin-bottom: 20px;">
                            <tr><td style="padding: 8px; border-bottom: 1px solid #eee; width: 40%;"><strong>Checking Account:</strong></td><td style="padding: 8px; border-bottom: 1px solid #eee;">${float(submission.assetData.get('checking', 0) or 0):,.0f}</td></tr>
                            <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>Savings Account:</strong></td><td style="padding: 8px; border-bottom: 1px solid #eee;">${float(submission.assetData.get('savings', 0) or 0):,.0f}</td></tr>
                            <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>Investments:</strong></td><td style="padding: 8px; border-bottom: 1px solid #eee;">${float(submission.assetData.get('investments', 0) or 0):,.0f}</td></tr>
                            <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>Gift Amount:</strong></td><td style="padding: 8px; border-bottom: 1px solid #eee;">${float(submission.assetData.get('giftAmount', 0) or 0):,.0f}</td></tr>
                        </table>

                        <h3 style="color: #218D8D; margin-top: 25px;">📝 DECLARATIONS & QUESTIONNAIRE RESPONSES</h3>
                        <table style="width: 100%; border-collapse: collapse; margin-bottom: 20px;">
                            <tr><td style="padding: 8px; border-bottom: 1px solid #eee; width: 40%;"><strong>Borrowers on Loan:</strong></td><td style="padding: 8px; border-bottom: 1px solid #eee;">{format_declaration('borrower_count', submission.declarations.get('borrower_count'))}</td></tr>
                            <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>Borrower Relationship:</strong></td><td style="padding: 8px; border-bottom: 1px solid #eee;">{format_declaration('borrower_relationship', submission.declarations.get('borrower_relationship'))}</td></tr>
                            <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>Citizenship Status:</strong></td><td style="padding: 8px; border-bottom: 1px solid #eee;">{format_declaration('citizenship_status', submission.declarations.get('citizenship_status'))}</td></tr>
                            <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>First-Time Buyer:</strong></td><td style="padding: 8px; border-bottom: 1px solid #eee;">{format_declaration('first_time_buyer', submission.declarations.get('first_time_buyer'))}</td></tr>
                            <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>Previous Home Status:</strong></td><td style="padding: 8px; border-bottom: 1px solid #eee;">{format_declaration('previous_home_status', submission.declarations.get('previous_home_status'))}</td></tr>
                            <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>Previous Home Mortgage:</strong></td><td style="padding: 8px; border-bottom: 1px solid #eee;">{format_declaration('previous_home_mortgage', submission.declarations.get('previous_home_mortgage'))}</td></tr>
                            <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>Marital Status:</strong></td><td style="padding: 8px; border-bottom: 1px solid #eee;">{format_declaration('marital_status', submission.declarations.get('marital_status'))}</td></tr>
                            <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>Spouse on Loan:</strong></td><td style="padding: 8px; border-bottom: 1px solid #eee;">{format_declaration('spouse_on_loan', submission.declarations.get('spouse_on_loan'))}</td></tr>
                            <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>Divorce Status:</strong></td><td style="padding: 8px; border-bottom: 1px solid #eee;">{format_declaration('divorce_finalized', submission.declarations.get('divorce_finalized'))}</td></tr>
                            <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>Child Support/Alimony:</strong></td><td style="padding: 8px; border-bottom: 1px solid #eee;">{format_declaration('child_support_alimony', submission.declarations.get('child_support_alimony'))}</td></tr>
                            <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>Monthly Support Received:</strong></td><td style="padding: 8px; border-bottom: 1px solid #eee;">{format_currency_value(submission.declarations.get('support_received_monthly'))}</td></tr>
                            <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>Monthly Support Paid:</strong></td><td style="padding: 8px; border-bottom: 1px solid #eee;">{format_currency_value(submission.declarations.get('support_paid_monthly'))}</td></tr>
                            <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>Other Real Estate:</strong></td><td style="padding: 8px; border-bottom: 1px solid #eee;">{format_declaration('other_real_estate', submission.declarations.get('other_real_estate'))}</td></tr>
                            <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>Veteran/Military:</strong></td><td style="padding: 8px; border-bottom: 1px solid #eee;">{format_declaration('veteran', submission.declarations.get('veteran'))}</td></tr>
                            <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>VA Loan Used Before:</strong></td><td style="padding: 8px; border-bottom: 1px solid #eee;">{format_declaration('va_loan_used', submission.declarations.get('va_loan_used'))}</td></tr>
                            <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>VA Disability Rating:</strong></td><td style="padding: 8px; border-bottom: 1px solid #eee;">{format_declaration('va_disability', submission.declarations.get('va_disability'))}</td></tr>
                            <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>Self-Employed:</strong></td><td style="padding: 8px; border-bottom: 1px solid #eee;">{format_declaration('self_employed', submission.declarations.get('self_employed'))}</td></tr>
                            <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>Years Self-Employed:</strong></td><td style="padding: 8px; border-bottom: 1px solid #eee;">{format_declaration('self_employed_years', submission.declarations.get('self_employed_years'))}</td></tr>
                            <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>Business Type:</strong></td><td style="padding: 8px; border-bottom: 1px solid #eee;">{format_declaration('business_type', submission.declarations.get('business_type'))}</td></tr>
                            <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>Prior Year Taxes Filed:</strong></td><td style="padding: 8px; border-bottom: 1px solid #eee;">{format_declaration('prior_year_taxes_filed', submission.declarations.get('prior_year_taxes_filed'))}</td></tr>
                            <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>Maximizes Deductions:</strong></td><td style="padding: 8px; border-bottom: 1px solid #eee;">{format_declaration('write_off_expenses', submission.declarations.get('write_off_expenses'))}</td></tr>
                            <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>IRS Balance Owed:</strong></td><td style="padding: 8px; border-bottom: 1px solid #eee;">{format_declaration('irs_balance_owed', submission.declarations.get('irs_balance_owed'))}</td></tr>
                            <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>IRS Payment Plan Current:</strong></td><td style="padding: 8px; border-bottom: 1px solid #eee;">{format_declaration('irs_payment_current', submission.declarations.get('irs_payment_current'))}</td></tr>
                            <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>Recent Credit Applications:</strong></td><td style="padding: 8px; border-bottom: 1px solid #eee;">{format_declaration('recent_credit_apps', submission.declarations.get('recent_credit_apps'))}</td></tr>
                            <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>Credit Application Type:</strong></td><td style="padding: 8px; border-bottom: 1px solid #eee;">{format_declaration('credit_app_type', submission.declarations.get('credit_app_type'))}</td></tr>
                            <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>Credit App Approved:</strong></td><td style="padding: 8px; border-bottom: 1px solid #eee;">{format_declaration('credit_app_approved', submission.declarations.get('credit_app_approved'))}</td></tr>
                            <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>Gift Funds:</strong></td><td style="padding: 8px; border-bottom: 1px solid #eee;">{format_declaration('gift_funds', submission.declarations.get('gift_funds'))}</td></tr>
                            <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>Gift Amount:</strong></td><td style="padding: 8px; border-bottom: 1px solid #eee;">{format_currency_value(submission.declarations.get('gift_amount'))}</td></tr>
                            <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>Gift Donor:</strong></td><td style="padding: 8px; border-bottom: 1px solid #eee;">{format_declaration('gift_donor', submission.declarations.get('gift_donor'))}</td></tr>
                            <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>Property Found:</strong></td><td style="padding: 8px; border-bottom: 1px solid #eee;">{format_declaration('found_property', submission.declarations.get('found_property'))}</td></tr>
                            <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>Target Closing Date:</strong></td><td style="padding: 8px; border-bottom: 1px solid #eee;">{submission.declarations.get('target_closing_date', 'N/A')}</td></tr>
                            <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>Working with Agent:</strong></td><td style="padding: 8px; border-bottom: 1px solid #eee;">{format_declaration('working_with_agent', submission.declarations.get('working_with_agent'))}</td></tr>
                            <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>Bankruptcy History:</strong></td><td style="padding: 8px; border-bottom: 1px solid #eee;">{format_declaration('bankruptcy', submission.declarations.get('bankruptcy'))}</td></tr>
                            <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>Bankruptcy Type:</strong></td><td style="padding: 8px; border-bottom: 1px solid #eee;">{format_declaration('bankruptcy_type', submission.declarations.get('bankruptcy_type'))}</td></tr>
                            <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>Bankruptcy Status:</strong></td><td style="padding: 8px; border-bottom: 1px solid #eee;">{format_declaration('bankruptcy_status', submission.declarations.get('bankruptcy_status'))}</td></tr>
                            <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>E-Consent Agreed:</strong></td><td style="padding: 8px; border-bottom: 1px solid #eee;">{'Yes' if submission.eConsentAgreed else 'No'}</td></tr>
                            <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>Credit Auth Agreed:</strong></td><td style="padding: 8px; border-bottom: 1px solid #eee;">{'Yes' if submission.creditAuthAgreed else 'No'}</td></tr>
                        </table>

                        <h3 style="color: #218D8D; margin-top: 25px;">👥 CO-BORROWER INFORMATION</h3>
                        <table style="width: 100%; border-collapse: collapse; margin-bottom: 20px;">
                            <tr><td style="padding: 8px; border-bottom: 1px solid #eee; width: 40%;"><strong>Co-Borrower First Name:</strong></td><td style="padding: 8px; border-bottom: 1px solid #eee;">{submission.declarations.get('co_borrower_first_name', 'N/A')}</td></tr>
                            <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>Co-Borrower Last Name:</strong></td><td style="padding: 8px; border-bottom: 1px solid #eee;">{submission.declarations.get('co_borrower_last_name', 'N/A')}</td></tr>
                            <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>Co-Borrower Email:</strong></td><td style="padding: 8px; border-bottom: 1px solid #eee;">{submission.declarations.get('co_borrower_email', 'N/A')}</td></tr>
                            <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>Co-Borrower Phone:</strong></td><td style="padding: 8px; border-bottom: 1px solid #eee;">{submission.declarations.get('co_borrower_phone', 'N/A')}</td></tr>
                        </table>

                        <h3 style="color: #218D8D; margin-top: 25px;">📎 ATTACHED DOCUMENTS</h3>
                        <ul style="background: #f8f9fa; padding: 15px 30px; border-radius: 5px;">
                            <li>Application Summary (complete Q&A)</li>
                            <li>E-Consent Agreement (signed)</li>
                            <li>Credit Authorization (signed)</li>
                            <li>Fannie Mae 3.4 File (for LOS import)</li>
                        </ul>

                        <p style="color: #666; font-size: 12px; margin-top: 30px; border-top: 1px solid #eee; padding-top: 20px;">
                            This is an automated message from Perennia AI Mortgage Platform.<br>
                            Submitted: {submission_date.strftime('%B %d, %Y at %I:%M %p')}
                        </p>
                    </div>
                </body>
                </html>
                """

                safe_borrower_name = borrower_name.replace(' ', '_').replace('/', '_')

                # Build attachments list
                email_attachments = [
                    {
                        "filename": f"E-Consent_{safe_borrower_name}_{date_str}.pdf",
                        "content": base64.b64encode(econsent_pdf).decode('utf-8'),
                        "type": "application/pdf",
                    },
                    {
                        "filename": f"Credit_Authorization_{safe_borrower_name}_{date_str}.pdf",
                        "content": base64.b64encode(credit_auth_pdf).decode('utf-8'),
                        "type": "application/pdf",
                    },
                    {
                        "filename": f"FannieMae34_{safe_borrower_name}_{date_str}.xml",
                        "content": base64.b64encode(fannie_mae_bytes).decode('utf-8'),
                        "type": "application/xml",
                    }
                ]

                # Add application summary PDF if generated
                if application_summary_pdf:
                    email_attachments.append({
                        "filename": f"Application_Summary_{safe_borrower_name}_{date_str}.pdf",
                        "content": base64.b64encode(application_summary_pdf).decode('utf-8'),
                        "type": "application/pdf",
                    })

                # Combine LO email with team emails, removing duplicates
                all_recipients = list(set([lo_email] + team_emails))

                # Send email to all recipients
                emails_sent_count = 0
                for recipient_email in all_recipients:
                    try:
                        sent = email_service.send_html_email(
                            to_email=recipient_email,
                            subject=f"New Application: {borrower_name}",
                            html_body=email_html,
                            attachments=email_attachments
                        )
                        if sent:
                            emails_sent_count += 1
                            logger.info(f"Email sent successfully to {recipient_email} for {borrower_name}")
                    except Exception as single_email_error:
                        logger.warning(f"Failed to send email to {recipient_email}: {single_email_error}")

                email_sent = emails_sent_count > 0
                logger.info(f"Sent {emails_sent_count}/{len(all_recipients)} emails for {borrower_name}")
            except Exception as email_error:
                logger.error(f"Email sending failed: {email_error}")

        # =================================================================
        # CREATE LEAD IN CRM
        # =================================================================

        # Resolve organization_id from loan officer for tenant isolation
        organization_id = None
        if submission.loId:
            lo_org_result = db.execute(text(
                "SELECT organization_id FROM users WHERE id = :lo_id"
            ), {"lo_id": submission.loId}).fetchone()
            if lo_org_result and lo_org_result[0]:
                organization_id = lo_org_result[0]

        # Calculate loan details - use paymentEstimate if available (from budget calculator)
        if submission.paymentEstimate:
            purchase_price = float(submission.paymentEstimate.get("homeValue", 0) or 0)
            down_payment = float(submission.paymentEstimate.get("downPaymentAmount", 0) or 0)
            loan_amount = float(submission.paymentEstimate.get("loanAmount", 0) or 0)
        else:
            purchase_price = float(submission.propertyData.get("purchasePrice", 0) or 0)
            down_payment = float(submission.propertyData.get("downPayment", 0) or 0)
            loan_amount = purchase_price - down_payment
        ltv = (loan_amount / purchase_price * 100) if purchase_price > 0 else 0
        annual_income = float(submission.incomeData.get("annualSalary", 0) or 0)

        # Calculate DTI (rough estimate based on loan amount)
        estimated_monthly_payment = loan_amount * 0.006  # ~6% of loan amount as rough monthly
        monthly_income = annual_income / 12 if annual_income > 0 else 1
        dti = (estimated_monthly_payment / monthly_income * 100) if monthly_income > 0 else 0

        # Determine if first-time buyer
        first_time_buyer = submission.declarations.get("first_time_buyer", "no") == "yes"

        # Extract referral partner ID from declarations (agent/realtor selection)
        referral_partner_id = submission.declarations.get("agent_partner_id")
        if referral_partner_id:
            try:
                referral_partner_id = int(referral_partner_id)
                logger.info(f"Application linked to referral partner ID: {referral_partner_id}")
            except (ValueError, TypeError):
                referral_partner_id = None

        # Create lead in CRM (let database auto-generate ID)
        result = db.execute(text("""
            INSERT INTO leads (
                name, first_name, last_name, email, phone,
                address, city, state, zip_code,
                property_type, property_value, down_payment, loan_amount,
                annual_income, credit_score, employer_name,
                stage, source, loan_type, first_time_buyer,
                ltv, dti, owner_id, referral_partner_id,
                organization_id,
                application_completed_date, stage_changed_at,
                created_at, updated_at
            )
            VALUES (
                :name, :first_name, :last_name, :email, :phone,
                :address, :city, :state, :zip_code,
                :property_type, :property_value, :down_payment, :loan_amount,
                :annual_income, :credit_score, :employer_name,
                :stage, :source, :loan_type, :first_time_buyer,
                :ltv, :dti, :owner_id, :referral_partner_id,
                :organization_id,
                :application_completed_date, :stage_changed_at,
                :created_at, :updated_at
            )
            RETURNING id
        """), {
            "name": borrower_name,
            "first_name": submission.profileData.get("firstName", ""),
            "last_name": submission.profileData.get("lastName", ""),
            "email": borrower_email,
            "phone": submission.profileData.get("phone", ""),
            "address": submission.profileData.get("address", ""),
            "city": submission.profileData.get("city", ""),
            "state": submission.profileData.get("state", ""),
            "zip_code": submission.profileData.get("zip", ""),
            "property_type": submission.propertyData.get("propertyType", "Single Family"),
            "property_value": purchase_price,
            "down_payment": down_payment,
            "loan_amount": loan_amount,
            "annual_income": annual_income,
            "credit_score": None,  # Will be populated after credit pull
            "employer_name": submission.incomeData.get("employerName", ""),
            "stage": "NEW",  # Standard stage for new leads (uppercase enum)
            "source": "Online Application",
            "loan_type": submission.propertyData.get("loanProgram", "Conventional"),
            "first_time_buyer": first_time_buyer,
            "ltv": round(ltv, 2),
            "dti": round(dti, 2),
            "owner_id": submission.loId,
            "referral_partner_id": referral_partner_id,
            "organization_id": organization_id,
            "application_completed_date": submission_date,
            "stage_changed_at": submission_date,
            "created_at": submission_date,
            "updated_at": submission_date,
        })

        lead_row = result.fetchone()
        lead_id = lead_row[0] if lead_row else None

        db.commit()
        logger.info(f"Created lead {lead_id} in CRM for {borrower_name}")

        # =================================================================
        # ENROLL LEAD IN WORKFLOW FOR TASK GENERATION
        # =================================================================
        workflow_enrollment_result = None
        if lead_id:
            try:
                from services.workflow_sla_service import WorkflowSLAService
                workflow_service = WorkflowSLAService(db)

                # Enroll in "new_application" workflow (or "prospect" as fallback)
                # This will generate initial tasks based on workflow configuration
                workflow_enrollment_result = workflow_service.enroll_lead(
                    lead_id=lead_id,
                    workflow_key="new_application",  # Primary workflow for new applications
                    trigger_status="NEW",
                    user_id=submission.loId if submission.loId else None
                )

                # If new_application workflow doesn't exist, try prospect workflow
                if not workflow_enrollment_result.get("success"):
                    workflow_enrollment_result = workflow_service.enroll_lead(
                        lead_id=lead_id,
                        workflow_key="prospect",  # Fallback workflow
                        trigger_status="NEW",
                        user_id=submission.loId if submission.loId else None
                    )

                if workflow_enrollment_result.get("success"):
                    logger.info(f"Lead {lead_id} enrolled in workflow, {workflow_enrollment_result.get('tasks_created', 0)} tasks created")
                else:
                    logger.warning(f"Workflow enrollment failed for lead {lead_id}: {workflow_enrollment_result.get('error')}")
            except Exception as workflow_error:
                logger.warning(f"Workflow enrollment failed (non-critical): {workflow_error}")

        # =================================================================
        # CREATE LOAN RECORD FOR SMART DOCS
        # =================================================================
        loan_id = None
        if lead_id:
            try:
                # Generate a unique loan number based on lead_id
                loan_number = f"APP-{str(lead_id).zfill(6)}"

                # Build property address string
                property_address_str = submission.propertyData.get("address", "")
                if submission.propertyData.get("city"):
                    property_address_str += f", {submission.propertyData.get('city')}"
                if submission.propertyData.get("state"):
                    property_address_str += f", {submission.propertyData.get('state')}"
                if submission.propertyData.get("zip"):
                    property_address_str += f" {submission.propertyData.get('zip')}"

                # Determine loan type/program
                loan_program = submission.propertyData.get("loanProgram", "Conventional")

                # Create loan record
                loan_result = db.execute(text("""
                    INSERT INTO loans (
                        loan_number, borrower_name, borrower_email, borrower_phone,
                        stage, program, loan_type, amount,
                        purchase_price, down_payment, rate, term,
                        property_address, loan_officer_id,
                        organization_id,
                        days_in_stage, sla_status,
                        created_at, updated_at
                    )
                    VALUES (
                        :loan_number, :borrower_name, :borrower_email, :borrower_phone,
                        'Processing', :program, :loan_type, :amount,
                        :purchase_price, :down_payment, NULL, 360,
                        :property_address, :loan_officer_id,
                        :organization_id,
                        0, 'on-track',
                        :created_at, :updated_at
                    )
                    RETURNING id
                """), {
                    "loan_number": loan_number,
                    "borrower_name": borrower_name,
                    "borrower_email": borrower_email,
                    "borrower_phone": submission.profileData.get("phone", ""),
                    "program": loan_program,
                    "loan_type": loan_program,
                    "amount": loan_amount,
                    "purchase_price": purchase_price,
                    "down_payment": down_payment,
                    "property_address": property_address_str.strip(", ") if property_address_str else None,
                    "loan_officer_id": submission.loId if submission.loId else None,
                    "organization_id": organization_id,
                    "created_at": submission_date,
                    "updated_at": submission_date,
                })

                loan_row = loan_result.fetchone()
                if loan_row:
                    loan_id = loan_row[0]

                db.commit()
                logger.info(f"Created loan {loan_id} (number: {loan_number}) for lead {lead_id}")

                # Backfill Lead.loan_number so client-file resolution uses the fast path
                try:
                    db.execute(text(
                        "UPDATE leads SET loan_number = :ln WHERE id = :lid AND loan_number IS NULL"
                    ), {"ln": loan_number, "lid": lead_id})
                    db.commit()
                except Exception as e:
                    logger.debug(f"Could not backfill lead loan_number: {e}")

            except Exception as loan_error:
                logger.warning(f"Failed to create loan record: {loan_error}")
                # Non-critical - continue without loan record

        # =================================================================
        # STORE E-SIGN DOCUMENTS IN DATABASE
        # =================================================================
        documents_stored = []
        doc_error_msg = None
        if lead_id:
            try:
                import base64

                # Store E-Consent PDF in database (using notes field for base64 content)
                if econsent_pdf:
                    econsent_filename = f"E-Consent_{safe_borrower_name}_{date_str}.pdf"
                    econsent_b64 = base64.b64encode(econsent_pdf).decode('utf-8')

                    db.execute(text("""
                        INSERT INTO documents (borrower_id, doc_type, doc_category, filename, original_filename,
                            file_size, mime_type, file_location, source, status, notes, uploaded_at)
                        VALUES (:borrower_id, 'E-Consent Agreement', 'Disclosures', :filename, :original_filename,
                            :file_size, 'application/pdf', :file_location, 'APPLICATION', 'active', :notes, :uploaded_at)
                    """), {
                        "borrower_id": lead_id,
                        "filename": econsent_filename,
                        "original_filename": econsent_filename,
                        "file_size": len(econsent_pdf),
                        "file_location": f"db://documents/econsent/{lead_id}/{econsent_filename}",
                        "notes": econsent_b64,
                        "uploaded_at": submission_date,
                    })
                    documents_stored.append("E-Consent")
                    logger.info(f"Stored E-Consent document for lead {lead_id}")

                # Store Credit Authorization PDF
                if credit_auth_pdf:
                    credit_auth_filename = f"Credit_Authorization_{safe_borrower_name}_{date_str}.pdf"
                    credit_auth_b64 = base64.b64encode(credit_auth_pdf).decode('utf-8')

                    db.execute(text("""
                        INSERT INTO documents (borrower_id, doc_type, doc_category, filename, original_filename,
                            file_size, mime_type, file_location, source, status, notes, uploaded_at)
                        VALUES (:borrower_id, 'Credit Authorization', 'Disclosures', :filename, :original_filename,
                            :file_size, 'application/pdf', :file_location, 'APPLICATION', 'active', :notes, :uploaded_at)
                    """), {
                        "borrower_id": lead_id,
                        "filename": credit_auth_filename,
                        "original_filename": credit_auth_filename,
                        "file_size": len(credit_auth_pdf),
                        "file_location": f"db://documents/credit_auth/{lead_id}/{credit_auth_filename}",
                        "notes": credit_auth_b64,
                        "uploaded_at": submission_date,
                    })
                    documents_stored.append("Credit Authorization")
                    logger.info(f"Stored Credit Authorization document for lead {lead_id}")

                # Store Fannie Mae 3.4 file
                if fannie_mae_xml:
                    fannie_filename = f"FannieMae34_{safe_borrower_name}_{date_str}.xml"
                    fannie_b64 = base64.b64encode(fannie_mae_xml.encode('utf-8')).decode('utf-8')

                    db.execute(text("""
                        INSERT INTO documents (borrower_id, doc_type, doc_category, filename, original_filename,
                            file_size, mime_type, file_location, source, status, notes, uploaded_at)
                        VALUES (:borrower_id, 'Fannie Mae 3.4 File', 'Disclosures', :filename, :original_filename,
                            :file_size, 'application/xml', :file_location, 'APPLICATION', 'active', :notes, :uploaded_at)
                    """), {
                        "borrower_id": lead_id,
                        "filename": fannie_filename,
                        "original_filename": fannie_filename,
                        "file_size": len(fannie_mae_xml),
                        "file_location": f"db://documents/fannie_mae/{lead_id}/{fannie_filename}",
                        "notes": fannie_b64,
                        "uploaded_at": submission_date,
                    })
                    documents_stored.append("Fannie Mae 3.4")
                    logger.info(f"Stored Fannie Mae 3.4 document for lead {lead_id}")

                # Store Application Summary PDF
                if application_summary_pdf:
                    app_summary_filename = f"Application_Summary_{safe_borrower_name}_{date_str}.pdf"
                    app_summary_b64 = base64.b64encode(application_summary_pdf).decode('utf-8')

                    db.execute(text("""
                        INSERT INTO documents (borrower_id, doc_type, doc_category, filename, original_filename,
                            file_size, mime_type, file_location, source, status, notes, uploaded_at)
                        VALUES (:borrower_id, 'Application Summary', 'Application', :filename, :original_filename,
                            :file_size, 'application/pdf', :file_location, 'APPLICATION', 'active', :notes, :uploaded_at)
                    """), {
                        "borrower_id": lead_id,
                        "filename": app_summary_filename,
                        "original_filename": app_summary_filename,
                        "file_size": len(application_summary_pdf),
                        "file_location": f"db://documents/application/{lead_id}/{app_summary_filename}",
                        "notes": app_summary_b64,
                        "uploaded_at": submission_date,
                    })
                    documents_stored.append("Application Summary")
                    logger.info(f"Stored Application Summary document for lead {lead_id}")

                db.commit()
                logger.info(f"Stored {len(documents_stored)} documents for lead {lead_id}: {documents_stored}")

            except Exception as doc_error:
                logger.error(f"Document storage failed: {doc_error}")
                import traceback
                doc_error_msg = str(doc_error)
                logger.error(traceback.format_exc())

        # Track if no lead_id was available
        if not lead_id:
            doc_error_msg = "No lead_id available for document storage"

        # =================================================================
        # CREATE PORTAL WORKSPACE FOR BORROWER
        # =================================================================
        workspace_slug = None
        workspace_id = None
        workspace_error = None

        if lead_id:
            try:
                import re
                import random
                import string

                # Reuse organization_id resolved earlier (default to 1)
                org_id = organization_id if organization_id else 1

                # Generate a unique slug in format: firstname.lastname.url
                first_name_clean = re.sub(r'[^a-z]+', '', submission.profileData.get("firstName", "").lower())
                last_name_clean = re.sub(r'[^a-z]+', '', submission.profileData.get("lastName", "").lower())

                # Build base slug: firstname.lastname.url
                if first_name_clean and last_name_clean:
                    base_slug = f"{first_name_clean}.{last_name_clean}.url"
                else:
                    # Fallback if names are missing
                    base_slug = re.sub(r'[^a-z0-9]+', '.', borrower_name.lower()).strip('.') + ".url"

                # Check if slug already exists and add number suffix if needed
                workspace_slug = base_slug
                counter = 1
                while True:
                    existing = db.execute(text("""
                        SELECT id FROM purl_workspaces WHERE slug = :slug
                    """), {"slug": workspace_slug}).fetchone()
                    if not existing:
                        break
                    workspace_slug = f"{first_name_clean}.{last_name_clean}{counter}.url"
                    counter += 1

                # Create workspace with direct SQL (avoids ORM relationship issues)
                workspace_result = db.execute(text("""
                    INSERT INTO purl_workspaces (
                        organization_id, slug, display_name, status, source,
                        owner_user_id, lead_at, meta_data, created_at, updated_at
                    )
                    VALUES (
                        :org_id, :slug, :display_name, 'lead', 'online_application',
                        :owner_user_id, :lead_at, :meta_data, :created_at, :updated_at
                    )
                    RETURNING id
                """), {
                    "org_id": org_id,
                    "slug": workspace_slug,
                    "display_name": borrower_name,
                    "owner_user_id": submission.loId if submission.loId else None,
                    "lead_at": submission_date,
                    "meta_data": json.dumps({
                        "lead_id": lead_id,
                        "email": borrower_email,
                        "phone": submission.profileData.get("phone", ""),
                        "loan_amount": loan_amount,
                        "property_value": purchase_price,
                        # Full application Q&A data for portal display
                        "application_data": {
                            "profileData": submission.profileData,
                            "incomeData": submission.incomeData,
                            "assetData": submission.assetData,
                            "propertyData": submission.propertyData,
                            "declarations": submission.declarations,
                            "applicationType": submission.applicationType if hasattr(submission, 'applicationType') else 'purchase',
                            "submittedAt": submission_date.isoformat(),
                        },
                    }),
                    "created_at": submission_date,
                    "updated_at": submission_date,
                })

                workspace_row = workspace_result.fetchone()
                if workspace_row:
                    workspace_id = workspace_row[0]

                    # Add borrower as a contact in the workspace
                    db.execute(text("""
                        INSERT INTO purl_contacts (
                            organization_id, workspace_id, contact_type,
                            first_name, last_name, email, phone, meta_data, created_at, updated_at
                        )
                        VALUES (
                            :org_id, :workspace_id, 'borrower',
                            :first_name, :last_name, :email, :phone, :meta_data, :created_at, :updated_at
                        )
                    """), {
                        "org_id": org_id,
                        "workspace_id": workspace_id,
                        "first_name": submission.profileData.get("firstName", ""),
                        "last_name": submission.profileData.get("lastName", ""),
                        "email": borrower_email,
                        "phone": submission.profileData.get("phone", ""),
                        "meta_data": json.dumps({"is_primary": True}),
                        "created_at": submission_date,
                        "updated_at": submission_date,
                    })

                    db.commit()
                    logger.info(f"Created workspace {workspace_id} with slug {workspace_slug} for lead {lead_id}")

                    # Generate access token for immediate portal access
                    try:
                        import hashlib
                        from datetime import timezone as tz

                        # Generate a secure token
                        token_raw = secrets.token_hex(32)
                        portal_token = f"purl_live_{token_raw}"
                        token_hash = hashlib.sha256(portal_token.encode()).hexdigest()
                        token_prefix = portal_token[:16]

                        # Get the contact_id we just created
                        contact_result = db.execute(text("""
                            SELECT id FROM purl_contacts
                            WHERE workspace_id = :workspace_id AND email = :email
                            LIMIT 1
                        """), {"workspace_id": workspace_id, "email": borrower_email}).fetchone()

                        contact_id = contact_result[0] if contact_result else None

                        # Create access token (valid for 30 days) - use timezone-aware datetimes
                        now_utc = datetime.now(tz.utc)
                        token_expiry = now_utc + timedelta(days=30)

                        db.execute(text("""
                            INSERT INTO purl_access_tokens (
                                organization_id, workspace_id, token_hash, token_prefix,
                                scope, status, contact_id, expires_at, created_at
                            )
                            VALUES (
                                :org_id, :workspace_id, :token_hash, :token_prefix,
                                'full', 'active', :contact_id, :expires_at, :created_at
                            )
                        """), {
                            "org_id": org_id,
                            "workspace_id": workspace_id,
                            "token_hash": token_hash,
                            "token_prefix": token_prefix,
                            "contact_id": contact_id,
                            "expires_at": token_expiry,
                            "created_at": now_utc,
                        })
                        db.commit()

                        # Verify token was actually inserted
                        verify_result = db.execute(text("""
                            SELECT id, token_hash FROM purl_access_tokens
                            WHERE token_hash = :hash
                        """), {"hash": token_hash}).fetchone()

                        if verify_result:
                            logger.info(f"Generated and verified portal access token for workspace {workspace_id} (token_id={verify_result[0]})")
                        else:
                            logger.error(f"Token INSERT succeeded but verification SELECT failed! Hash: {token_hash[:16]}...")
                            portal_token = None
                    except Exception as token_error:
                        logger.warning(f"Failed to generate portal token: {token_error}")
                        portal_token = None

                    # =================================================================
                    # CREATE PURL LOAN RECORD FOR PORTAL
                    # =================================================================
                    purl_loan_id = None
                    try:
                        # Get property address components
                        property_address = {
                            "street": submission.propertyData.get("address", ""),
                            "city": submission.propertyData.get("city", ""),
                            "state": submission.propertyData.get("state", ""),
                            "zip": submission.propertyData.get("zip", ""),
                        }

                        # Determine loan purpose from application type
                        loan_purpose = submission.applicationType if hasattr(submission, 'applicationType') and submission.applicationType else 'purchase'

                        loan_result = db.execute(text("""
                            INSERT INTO purl_loans (
                                organization_id, workspace_id, loan_number, status,
                                loan_purpose, product_type, loan_amount,
                                property_address, property_type, meta_data,
                                main_loan_id,
                                created_at, updated_at
                            )
                            VALUES (
                                :org_id, :workspace_id, :loan_number, 'processing',
                                :loan_purpose, :product_type, :loan_amount,
                                :property_address, :property_type, :meta_data,
                                :main_loan_id,
                                :created_at, :updated_at
                            )
                            RETURNING id
                        """), {
                            "org_id": org_id,
                            "workspace_id": workspace_id,
                            "loan_number": f"APP-{lead_id}" if lead_id else f"APP-{workspace_id}",
                            "loan_purpose": loan_purpose,
                            "product_type": submission.propertyData.get("loanProgram", "Conventional"),
                            "loan_amount": loan_amount,
                            "property_address": json.dumps(property_address),
                            "property_type": submission.propertyData.get("propertyType", "Single Family"),
                            "meta_data": json.dumps({
                                "purchase_price": purchase_price,
                                "down_payment": down_payment,
                                "ltv": round(ltv, 2),
                                "lead_id": lead_id,
                            }),
                            "main_loan_id": loan_id,  # Link to main loans table for Smart Docs
                            "created_at": submission_date,
                            "updated_at": submission_date,
                        })
                        loan_row = loan_result.fetchone()
                        if loan_row:
                            purl_loan_id = loan_row[0]
                        db.commit()
                        logger.info(f"Created PURL loan record {purl_loan_id} for workspace {workspace_id}")
                    except Exception as loan_error:
                        logger.warning(f"Failed to create PURL loan: {loan_error}")

                    # =================================================================
                    # STORE DOCUMENTS IN PURL_DOCUMENTS FOR PORTAL SMART DOCS
                    # =================================================================
                    if purl_loan_id and workspace_id:
                        try:
                            import hashlib
                            import base64 as b64

                            # Helper function to generate storage key and insert document
                            def store_purl_document(doc_type, doc_category, filename, content_bytes, mime_type):
                                storage_key = f"purl/{org_id}/{workspace_id}/{purl_loan_id}/{filename}"
                                sha256_hash = hashlib.sha256(content_bytes).hexdigest()

                                db.execute(text("""
                                    INSERT INTO purl_documents (
                                        organization_id, workspace_id, loan_id,
                                        doc_type, doc_category, status,
                                        file_name, storage_key, size_bytes, mime_type, sha256,
                                        created_at, updated_at
                                    )
                                    VALUES (
                                        :org_id, :workspace_id, :loan_id,
                                        :doc_type, :doc_category, 'approved',
                                        :file_name, :storage_key, :size_bytes, :mime_type, :sha256,
                                        :created_at, :updated_at
                                    )
                                """), {
                                    "org_id": org_id,
                                    "workspace_id": workspace_id,
                                    "loan_id": purl_loan_id,
                                    "doc_type": doc_type,
                                    "doc_category": doc_category,
                                    "file_name": filename,
                                    "storage_key": storage_key,
                                    "size_bytes": len(content_bytes),
                                    "mime_type": mime_type,
                                    "sha256": sha256_hash,
                                    "created_at": submission_date,
                                    "updated_at": submission_date,
                                })

                            # Store E-Consent in purl_documents
                            if econsent_pdf:
                                econsent_filename = f"E-Consent_{safe_borrower_name}_{date_str}.pdf"
                                store_purl_document("E-Consent Agreement", "Disclosures", econsent_filename, econsent_pdf, "application/pdf")

                            # Store Credit Authorization in purl_documents
                            if credit_auth_pdf:
                                credit_auth_filename = f"Credit_Authorization_{safe_borrower_name}_{date_str}.pdf"
                                store_purl_document("Credit Authorization", "Disclosures", credit_auth_filename, credit_auth_pdf, "application/pdf")

                            # Store Application Summary in purl_documents
                            if application_summary_pdf:
                                app_summary_filename = f"Application_Summary_{safe_borrower_name}_{date_str}.pdf"
                                store_purl_document("Application Summary", "Application", app_summary_filename, application_summary_pdf, "application/pdf")

                            # Store Fannie Mae 3.4 file in purl_documents
                            if fannie_mae_xml:
                                fannie_filename = f"FannieMae34_{safe_borrower_name}_{date_str}.xml"
                                store_purl_document("Fannie Mae 3.4 File", "Application", fannie_filename, fannie_mae_xml.encode('utf-8'), "application/xml")

                            db.commit()
                            logger.info(f"Stored documents in purl_documents for portal Smart Docs (workspace={workspace_id}, loan={purl_loan_id})")

                        except Exception as purl_doc_error:
                            logger.warning(f"Failed to store documents in purl_documents: {purl_doc_error}")
                            import traceback
                            logger.warning(traceback.format_exc())

                    # =================================================================
                    # GENERATE SMART DOCS NEEDS LIST
                    # =================================================================
                    if purl_loan_id:
                        try:
                            from services.smart_docs.needs_list_generator import NeedsListGenerator

                            # Map loan program
                            loan_program_raw = submission.propertyData.get("loanProgram", "Conventional").upper()
                            if loan_program_raw in ["FHA", "VA", "USDA", "CONVENTIONAL"]:
                                loan_program = loan_program_raw
                            else:
                                loan_program = "CONVENTIONAL"

                            # Map occupancy type
                            occupancy_raw = submission.propertyData.get("occupancy", "primary").upper()
                            occupancy_map = {
                                "PRIMARY": "PRIMARY",
                                "PRIMARY_RESIDENCE": "PRIMARY",
                                "SECOND_HOME": "SECOND_HOME",
                                "INVESTMENT": "INVESTMENT",
                                "RENTAL": "INVESTMENT",
                            }
                            occupancy_type = occupancy_map.get(occupancy_raw, "PRIMARY")

                            # Map income type based on declarations
                            is_self_employed = submission.declarations.get("self_employed") in ["yes", "side_business"]
                            income_type = "SELF_EMPLOYED" if is_self_employed else "W2"

                            # Additional flags
                            has_gift_funds = submission.declarations.get("gift_funds") == "yes"
                            has_bankruptcy = submission.declarations.get("bankruptcy") == "yes"
                            has_co_borrower = submission.declarations.get("has_co_borrower", False)

                            # Generate needs list using Smart Docs
                            generator = NeedsListGenerator(db)
                            result = generator.generate_needs_list(
                                loan_id=purl_loan_id,
                                loan_program=loan_program,
                                occupancy_type=occupancy_type,
                                income_type=income_type,
                                borrower_id=1,
                                co_borrower_id=2 if has_co_borrower else None,
                                has_gift_funds=has_gift_funds,
                                is_self_employed=is_self_employed,
                                has_bankruptcy=has_bankruptcy,
                                property_type=submission.propertyData.get("propertyType"),
                            )
                            logger.info(f"Generated Smart Docs needs list for loan {purl_loan_id}: {result.get('request_count', 0)} requests")
                        except ImportError:
                            logger.warning("Smart Docs NeedsListGenerator not available, skipping needs list generation")
                        except Exception as needs_error:
                            logger.warning(f"Failed to generate Smart Docs needs list: {needs_error}")
                            # Rollback to clear failed transaction state
                            db.rollback()

                    # =================================================================
                    # CREATE NEEDS LIST TASKS BASED ON DECLARATIONS
                    # =================================================================
                    try:
                        needs_tasks = []

                        # Self-employed documentation
                        if submission.declarations.get("self_employed") in ["yes", "side_business"]:
                            needs_tasks.append({
                                "title": "Business tax returns (2 years)",
                                "category": "income",
                                "description": "Personal and business tax returns from the past 2 years"
                            })
                            needs_tasks.append({
                                "title": "Profit & loss statement (YTD)",
                                "category": "income",
                                "description": "Current year-to-date profit and loss statement"
                            })
                            needs_tasks.append({
                                "title": "Business bank statements (3 months)",
                                "category": "income",
                                "description": "Most recent 3 months of business bank statements"
                            })
                        else:
                            needs_tasks.append({
                                "title": "Recent pay stubs (30 days)",
                                "category": "income",
                                "description": "Pay stubs covering the most recent 30-day period"
                            })
                            needs_tasks.append({
                                "title": "W-2s (last 2 years)",
                                "category": "income",
                                "description": "W-2 forms from your employer for the past 2 years"
                            })

                        # Gift funds documentation
                        if submission.declarations.get("gift_funds") == "yes":
                            needs_tasks.append({
                                "title": "Gift letter from donor",
                                "category": "assets",
                                "description": "Signed letter from the gift donor confirming the gift"
                            })
                            needs_tasks.append({
                                "title": "Donor bank statements",
                                "category": "assets",
                                "description": "Bank statements showing the source of gift funds"
                            })

                        # Veteran documentation
                        if submission.declarations.get("veteran") and submission.declarations.get("veteran") != "no":
                            needs_tasks.append({
                                "title": "DD-214 or Certificate of Eligibility",
                                "category": "military",
                                "description": "Military discharge papers or VA Certificate of Eligibility"
                            })

                        # IRS payment plan documentation
                        if submission.declarations.get("irs_balance_owed") in ["yes", "payment_plan"]:
                            needs_tasks.append({
                                "title": "IRS payment arrangement documentation",
                                "category": "legal",
                                "description": "Documentation of your IRS payment plan or balance owed"
                            })

                        # New credit account statement (if approved)
                        if submission.declarations.get("credit_application_approved") == "yes":
                            needs_tasks.append({
                                "title": "New account statement (loan/credit card)",
                                "category": "assets",
                                "description": "Most recent statement for any newly opened loan or credit card account"
                            })

                        # Standard documents for all applications
                        needs_tasks.append({
                            "title": "Bank statements (2 months)",
                            "category": "assets",
                            "description": "Most recent 2 months of all bank account statements"
                        })
                        needs_tasks.append({
                            "title": "Government-issued ID",
                            "category": "identity",
                            "description": "Driver's license or passport"
                        })

                        # Property-specific documents
                        if submission.declarations.get("found_property") == "yes":
                            needs_tasks.append({
                                "title": "Purchase contract",
                                "category": "property",
                                "description": "Signed purchase agreement for the property"
                            })

                        # Insert tasks
                        for idx, task in enumerate(needs_tasks):
                            db.execute(text("""
                                INSERT INTO purl_tasks (
                                    organization_id, workspace_id, task_type, title,
                                    description, status, priority, category, order_index,
                                    created_at, updated_at
                                )
                                VALUES (
                                    :org_id, :workspace_id, 'document_upload', :title,
                                    :description, 'open', 'high', :category, :order_index,
                                    :created_at, :updated_at
                                )
                            """), {
                                "org_id": org_id,
                                "workspace_id": workspace_id,
                                "title": task["title"],
                                "description": task["description"],
                                "category": task["category"],
                                "order_index": idx,
                                "created_at": submission_date,
                                "updated_at": submission_date,
                            })

                        db.commit()
                        logger.info(f"Created {len(needs_tasks)} needs list tasks for workspace {workspace_id}")

                        # =================================================================
                        # CREATE LEAD_CONDITIONS FOR PORTAL NEEDS LIST
                        # =================================================================
                        # Also create lead_conditions which the portal uses for the needs list
                        try:
                            for task in needs_tasks:
                                db.execute(text("""
                                    INSERT INTO lead_conditions (
                                        lead_id, name, description, category, priority,
                                        status, is_new, created_at, updated_at
                                    )
                                    VALUES (
                                        :lead_id, :name, :description, :category, 'required',
                                        'pending', 1, :created_at, :updated_at
                                    )
                                """), {
                                    "lead_id": lead_id,
                                    "name": task["title"],
                                    "description": task["description"],
                                    "category": task["category"],
                                    "created_at": submission_date,
                                    "updated_at": submission_date,
                                })
                            db.commit()
                            logger.info(f"Created {len(needs_tasks)} lead_conditions for lead {lead_id}")
                        except Exception as cond_error:
                            logger.warning(f"Failed to create lead_conditions (table may not exist): {cond_error}")

                    except Exception as task_error:
                        logger.warning(f"Failed to create needs list tasks: {task_error}")
                        import traceback
                        logger.warning(traceback.format_exc())
                        # Rollback to clear failed transaction state
                        db.rollback()

            except Exception as ws_error:
                logger.warning(f"Workspace creation failed (non-critical): {ws_error}")
                import traceback
                logger.warning(traceback.format_exc())
                workspace_error = str(ws_error)
                workspace_slug = None
                workspace_id = None
                portal_token = None

        # Build portal URL with token if available
        portal_url = None
        if workspace_slug:
            base_domain = os.getenv("PURL_BASE_DOMAIN", "perenniaai.com")
            portal_url = f"https://{base_domain}/portal/{workspace_slug}"
            try:
                if portal_token:
                    portal_url += f"?token={portal_token}"
            except NameError:
                pass  # portal_token wasn't defined

        return {
            "success": True,
            "message": "Application submitted successfully",
            "data": {
                "borrower_id": borrower_id,
                "lead_id": lead_id,
                "loan_id": loan_id,  # Main loans table ID for Smart Docs
                "workspace_id": workspace_id,
                "workspace_slug": workspace_slug,
                "portal_url": portal_url,
                "submission_date": submission_date.isoformat(),
                "pdfs_generated": econsent_pdf is not None and credit_auth_pdf is not None,
                "fannie_mae_generated": fannie_mae_xml is not None,
                "email_sent_to_lo": email_sent,
                "documents_stored": documents_stored,
                "document_storage_error": doc_error_msg,
                "workspace_error": workspace_error,
            }
        }

    except Exception as e:
        logger.exception("Application submission failed")
        db.rollback()
        raise HTTPException(status_code=500, detail="Submission failed. Please try again.")
