"""
Borrower Social Authentication Routes

Handles OAuth flows for borrowers to:
1. Sign in with Google, Apple, Facebook, LinkedIn
2. Create or resume mortgage applications
3. Capture consent for communication and marketing

This is separate from internal user authentication (LO/staff login).
"""

from fastapi import APIRouter, Request, HTTPException, Depends, Query, Body
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
import httpx
from datetime import datetime, timedelta
import uuid
import secrets
import logging
import jwt
import json
from urllib.parse import urlencode, quote
import os
from typing import Optional
from pydantic import BaseModel, EmailStr

from database import get_db
from email_service import email_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/borrower-auth", tags=["borrower-auth"])

# =============================================================================
# CONFIGURATION
# =============================================================================

FRONTEND_URL = os.getenv("FRONTEND_URL", "https://mortgage-crm-nine.vercel.app")
JWT_SECRET = os.getenv("JWT_SECRET", "your-secret-key-change-in-production")
JWT_ALGORITHM = "HS256"
BORROWER_TOKEN_EXPIRY_DAYS = 90

# Google OAuth
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
# Callback goes to backend, which then redirects to frontend with token
BACKEND_URL = os.getenv("BACKEND_URL", "https://mortgage-crm-production-7a9a.up.railway.app")
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
        "exp": datetime.utcnow() + timedelta(days=BORROWER_TOKEN_EXPIRY_DAYS),
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_borrower_token(token: str) -> Optional[dict]:
    """Verify and decode a borrower JWT token."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "borrower":
            return None
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
                "updated_at": datetime.utcnow(),
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
            "updated_at": datetime.utcnow(),
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
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
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
    subject = "🔐 Your Secure Login Link - Perennia Mortgage"

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
            <h1>Perennia Mortgage</h1>
        </div>

        <h2>Hi {first_name},</h2>

        <p>Click the button below to securely sign in to your mortgage application:</p>

        <div style="text-align: center;">
            <a href="{magic_link}" class="btn-login">Sign In to Your Application</a>
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
            <p>This email was sent by Perennia Mortgage</p>
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

- Perennia Mortgage
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
    redirect_to: Optional[str] = Query(None, description="Where to redirect after auth"),
    lo_id: Optional[str] = Query(None, description="Loan officer ID for attribution"),
):
    """Initiate Google OAuth flow for borrower."""
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=500, detail="Google OAuth not configured")

    state = json.dumps({
        "csrf": generate_state_token(),
        "redirect_to": redirect_to,
        "lo_id": lo_id,
    })

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
        state_data = json.loads(state)
    except:
        state_data = {}

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
                logger.error(f"Google token exchange failed: {token_response.text}")
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
            "created_at": datetime.utcnow(),
        })
        db.commit()

        # Redirect with token
        redirect_to = state_data.get("redirect_to") or "/apply/start"
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
    redirect_to: Optional[str] = Query(None),
    lo_id: Optional[str] = Query(None),
):
    """Initiate Facebook OAuth flow for borrower."""
    if not FACEBOOK_APP_ID:
        raise HTTPException(status_code=500, detail="Facebook OAuth not configured")

    state = json.dumps({
        "csrf": generate_state_token(),
        "redirect_to": redirect_to,
        "lo_id": lo_id,
    })

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
        state_data = json.loads(state)
    except:
        state_data = {}

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
                logger.error(f"Facebook token exchange failed: {token_response.text}")
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
            "created_at": datetime.utcnow(),
        })
        db.commit()

        redirect_to = state_data.get("redirect_to") or "/apply/start"
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
    redirect_to: Optional[str] = Query(None),
    lo_id: Optional[str] = Query(None),
):
    """Initiate LinkedIn OAuth flow for borrower."""
    if not LINKEDIN_CLIENT_ID:
        raise HTTPException(status_code=500, detail="LinkedIn OAuth not configured")

    state = json.dumps({
        "csrf": generate_state_token(),
        "redirect_to": redirect_to,
        "lo_id": lo_id,
    })

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
        state_data = json.loads(state)
    except:
        state_data = {}

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
                logger.error(f"LinkedIn token exchange failed: {token_response.text}")
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
            "created_at": datetime.utcnow(),
        })
        db.commit()

        redirect_to = state_data.get("redirect_to") or "/apply/start"
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
        "iat": datetime.utcnow(),
        "exp": datetime.utcnow() + timedelta(days=180),
        "aud": "https://appleid.apple.com",
        "sub": APPLE_CLIENT_ID,
    }

    return jwt.encode(payload, APPLE_PRIVATE_KEY, algorithm="ES256", headers=headers)


@router.get("/apple/connect")
async def apple_connect(
    redirect_to: Optional[str] = Query(None),
    lo_id: Optional[str] = Query(None),
):
    """Initiate Apple Sign In flow for borrower."""
    if not APPLE_CLIENT_ID:
        raise HTTPException(status_code=500, detail="Apple Sign In not configured")

    state = json.dumps({
        "csrf": generate_state_token(),
        "redirect_to": redirect_to,
        "lo_id": lo_id,
    })

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
        state_data = json.loads(state)
    except:
        state_data = {}

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
                logger.error(f"Apple token exchange failed: {token_response.text}")
                return RedirectResponse(url=f"{FRONTEND_URL}/apply/login?error=token_exchange_failed")

            tokens = token_response.json()

        # Decode ID token to get user info
        # Note: In production, verify the token signature
        id_token_payload = jwt.decode(
            tokens["id_token"],
            options={"verify_signature": False}  # Should verify in production
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
            except:
                pass

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
            "created_at": datetime.utcnow(),
        })
        db.commit()

        redirect_to = state_data.get("redirect_to") or "/apply/start"
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
    request: EmailLoginRequest,
    db: Session = Depends(get_db),
):
    """Request email-based login (sends magic link)."""

    # Generate magic link token
    magic_token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(hours=24)

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
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
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
        "created_at": datetime.utcnow(),
    })
    db.commit()

    # TODO: Send email with magic link
    magic_link = f"{FRONTEND_URL}/apply/verify?token={magic_token}"

    # Send the magic link email
    first_name = request.first_name or "there"
    email_sent = send_magic_link_email(request.email, first_name, magic_link)

    if not email_sent:
        logger.error(f"Failed to send magic link email to {request.email}")
        # Still return success since link was created - user can request again

    logger.info(f"Magic link created for {request.email}")

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

    result = db.execute(text("""
        SELECT ml.borrower_id, ml.expires_at, ml.used_at, bp.email
        FROM borrower_magic_links ml
        JOIN borrower_profiles bp ON bp.id = ml.borrower_id
        WHERE ml.token = :token
    """), {"token": token}).fetchone()

    if not result:
        return RedirectResponse(url=f"{FRONTEND_URL}/apply/login?error=invalid_link")

    borrower_id, expires_at, used_at, email = result

    if used_at:
        return RedirectResponse(url=f"{FRONTEND_URL}/apply/login?error=link_already_used")

    if expires_at < datetime.utcnow():
        return RedirectResponse(url=f"{FRONTEND_URL}/apply/login?error=link_expired")

    # Mark as used
    db.execute(text("""
        UPDATE borrower_magic_links SET used_at = :used_at WHERE token = :token
    """), {"used_at": datetime.utcnow(), "token": token})

    # Log event
    db.execute(text("""
        INSERT INTO borrower_auth_events (id, borrower_id, event_type, provider, created_at)
        VALUES (:id, :borrower_id, 'login', 'email', :created_at)
    """), {
        "id": str(uuid.uuid4()),
        "borrower_id": borrower_id,
        "created_at": datetime.utcnow(),
    })
    db.commit()

    auth_token = generate_borrower_token(borrower_id, email)

    return RedirectResponse(url=f"{FRONTEND_URL}/apply/start?token={auth_token}")


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
        "updated_at": datetime.utcnow(),
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
    eConsentAgreed: bool
    creditAuthAgreed: bool
    loId: Optional[str] = None


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
                "now": datetime.utcnow(),
            })

        # Prepare submission timestamp
        submission_date = datetime.utcnow()
        date_str = submission_date.strftime("%Y%m%d_%H%M%S")
        fannie_mae_bytes = fannie_mae_xml.encode('utf-8') if fannie_mae_xml else None

        # Get loan officer email to send Fannie Mae file
        lo_email = None
        if submission.loId:
            lo_result = db.execute(text("""
                SELECT email FROM users WHERE id = :lo_id
            """), {"lo_id": submission.loId}).fetchone()
            if lo_result:
                lo_email = lo_result[0]

        # Send email to loan officer with all application documents (non-critical)
        email_sent = False
        if lo_email and econsent_pdf and credit_auth_pdf and fannie_mae_bytes:
            try:
                import base64

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

                        <h3 style="color: #218D8D; margin-top: 25px;">📝 DECLARATIONS</h3>
                        <table style="width: 100%; border-collapse: collapse; margin-bottom: 20px;">
                            <tr><td style="padding: 8px; border-bottom: 1px solid #eee; width: 40%;"><strong>Citizenship:</strong></td><td style="padding: 8px; border-bottom: 1px solid #eee;">{submission.declarations.get('citizenship', 'N/A')}</td></tr>
                            <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>First-Time Buyer:</strong></td><td style="padding: 8px; border-bottom: 1px solid #eee;">{submission.declarations.get('first_time_buyer', 'N/A')}</td></tr>
                            <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>E-Consent Agreed:</strong></td><td style="padding: 8px; border-bottom: 1px solid #eee;">{'Yes' if submission.eConsentAgreed else 'No'}</td></tr>
                            <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>Credit Auth Agreed:</strong></td><td style="padding: 8px; border-bottom: 1px solid #eee;">{'Yes' if submission.creditAuthAgreed else 'No'}</td></tr>
                        </table>

                        <h3 style="color: #218D8D; margin-top: 25px;">📎 ATTACHED DOCUMENTS</h3>
                        <ul style="background: #f8f9fa; padding: 15px 30px; border-radius: 5px;">
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
                email_sent = email_service.send_html_email(
                    to_email=lo_email,
                    subject=f"New Application: {borrower_name}",
                    html_body=email_html,
                    attachments=[
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
                )
                if email_sent:
                    logger.info(f"Email sent successfully to {lo_email} for {borrower_name}")
                else:
                    logger.warning(f"Email send returned False for {lo_email}")
            except Exception as email_error:
                logger.error(f"Email sending failed: {email_error}")

        # =================================================================
        # CREATE LEAD IN CRM
        # =================================================================

        # Calculate loan details
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

        # Create lead in CRM (let database auto-generate ID)
        result = db.execute(text("""
            INSERT INTO leads (
                name, first_name, last_name, email, phone,
                address, city, state, zip_code,
                property_type, property_value, down_payment, loan_amount,
                annual_income, credit_score, employer_name,
                stage, source, loan_type, first_time_buyer,
                ltv, dti, owner_id,
                application_completed_date, stage_changed_at,
                created_at, updated_at
            )
            VALUES (
                :name, :first_name, :last_name, :email, :phone,
                :address, :city, :state, :zip_code,
                :property_type, :property_value, :down_payment, :loan_amount,
                :annual_income, :credit_score, :employer_name,
                :stage, :source, :loan_type, :first_time_buyer,
                :ltv, :dti, :owner_id,
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
        # STORE E-SIGN DOCUMENTS IN DATABASE
        # =================================================================
        documents_stored = []
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

                db.commit()
                logger.info(f"Stored {len(documents_stored)} documents for lead {lead_id}: {documents_stored}")

            except Exception as doc_error:
                logger.error(f"Document storage failed: {doc_error}")
                import traceback
                logger.error(traceback.format_exc())

        return {
            "success": True,
            "message": "Application submitted successfully",
            "data": {
                "borrower_id": borrower_id,
                "lead_id": lead_id,
                "submission_date": submission_date.isoformat(),
                "pdfs_generated": econsent_pdf is not None and credit_auth_pdf is not None,
                "fannie_mae_generated": fannie_mae_xml is not None,
                "email_sent_to_lo": email_sent,
                "documents_stored": documents_stored,
            }
        }

    except Exception as e:
        logger.exception("Application submission failed")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Submission failed: {str(e)}")
