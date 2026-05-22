"""Public POS start + email verification endpoints.

Flow:
1. POST /pos/start  — collect info, send 6-digit email code, return session_id
2. POST /pos/verify — validate code, create workspace/contact/token
3. POST /pos/resend — resend code with rate limiting

Enterprise hardening:
- IP-based rate limiting (5 starts / 10 min per IP)
- Per-session rate limiting on resend (60s cooldown)
- Duplicate email dedup within 5 min (reuse existing session)
- HMAC-SHA256 code hashing with SECRET_KEY
- Code expiry (10 min), max attempts (5)
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import os
import random
import re
import secrets
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from threading import Lock
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import text
from sqlalchemy.orm import Session

from database import get_db
from database.models.core import User
from database.models.pos import POSTrustedDevice, POSVerification
from models.purl import (
    ContactType,
    PURLContact,
    PURLWorkspace,
    TokenScope,
    WorkspaceStatus,
)
from services.purl_token_service import PURLTokenService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/pos", tags=["POS - Public Start"])
CODE_TTL_MINUTES = 10
MAX_VERIFY_ATTEMPTS = 5
RESEND_COOLDOWN_SECONDS = 60
IP_RATE_LIMIT = 5
IP_RATE_WINDOW_MINUTES = 10


# ── IP rate limiter (Redis-backed with in-memory fallback) ────────
# SEC-003: Primary rate limiting via Redis INCR with TTL so limits survive
# deploys. Falls back to in-memory tracking if Redis is unavailable.

_ip_tracker: dict[str, list[float]] = defaultdict(list)
_ip_lock = Lock()


def _get_redis():
    """Get Redis client, returning None if unavailable."""
    try:
        from services.redis_service import get_redis_client
        return get_redis_client()
    except Exception:
        return None


def _check_ip_rate_limit(ip: str):
    redis = _get_redis()
    if redis:
        try:
            key = f"pos_rate:{ip}"
            count = redis.incr(key)
            if count == 1:
                redis.expire(key, IP_RATE_WINDOW_MINUTES * 60)
            if count > IP_RATE_LIMIT:
                raise HTTPException(
                    status_code=429,
                    detail="Too many requests. Please try again in a few minutes.",
                )
            return
        except HTTPException:
            raise
        except Exception as e:
            logger.warning(f"Redis rate limit check failed, falling back to in-memory: {e}")

    # In-memory fallback
    now = datetime.now(timezone.utc).timestamp()
    cutoff = now - (IP_RATE_WINDOW_MINUTES * 60)
    with _ip_lock:
        if len(_ip_tracker) > 10000:
            oldest_keys = sorted(
                _ip_tracker.keys(),
                key=lambda k: min(_ip_tracker[k]) if _ip_tracker[k] else 0,
            )[:5000]
            for k in oldest_keys:
                del _ip_tracker[k]

        timestamps = [t for t in _ip_tracker.get(ip, []) if t > cutoff]
        if not timestamps:
            _ip_tracker.pop(ip, None)
        else:
            _ip_tracker[ip] = timestamps

        if len(_ip_tracker.get(ip, [])) >= IP_RATE_LIMIT:
            raise HTTPException(
                status_code=429,
                detail="Too many requests. Please try again in a few minutes.",
            )
        _ip_tracker.setdefault(ip, []).append(now)


# POSVerification and POSTrustedDevice models live in database/models/pos.py
# (imported at module level above).

TRUSTED_DEVICE_DAYS = 30


_table_ensured = False


def _ensure_table(db: Session):
    global _table_ensured
    if _table_ensured:
        return
    try:
        db.execute(text(
            "CREATE TABLE IF NOT EXISTS pos_verifications ("
            "id SERIAL PRIMARY KEY,"
            "session_id VARCHAR UNIQUE NOT NULL,"
            "phone VARCHAR NOT NULL,"
            "phone_raw VARCHAR NOT NULL DEFAULT '',"
            "code_hash VARCHAR NOT NULL,"
            "first_name VARCHAR NOT NULL,"
            "last_name VARCHAR NOT NULL,"
            "email VARCHAR NOT NULL,"
            "attempts INTEGER DEFAULT 0,"
            "ip_address VARCHAR,"
            "consent_at TIMESTAMPTZ,"
            "last_resend_at TIMESTAMPTZ,"
            "created_at TIMESTAMPTZ DEFAULT NOW(),"
            "verified_at TIMESTAMPTZ"
            ")"
        ))
        db.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_pos_verifications_session_id "
            "ON pos_verifications (session_id)"
        ))
        for col in ("phone_raw", "ip_address"):
            db.execute(text(
                f"ALTER TABLE pos_verifications ADD COLUMN IF NOT EXISTS "
                f"{col} VARCHAR"
            ))
        db.execute(text(
            "ALTER TABLE pos_verifications ADD COLUMN IF NOT EXISTS "
            "organization_id INTEGER"
        ))
        for col in ("consent_at", "last_resend_at"):
            db.execute(text(
                f"ALTER TABLE pos_verifications ADD COLUMN IF NOT EXISTS "
                f"{col} TIMESTAMPTZ"
            ))
        db.execute(text(
            "ALTER TABLE pos_verifications ADD COLUMN IF NOT EXISTS "
            "flow_type VARCHAR NOT NULL DEFAULT 'signup'"
        ))
        db.execute(text(
            "ALTER TABLE pos_verifications ADD COLUMN IF NOT EXISTS "
            "contact_id INTEGER"
        ))
        db.execute(text(
            "CREATE TABLE IF NOT EXISTS pos_trusted_devices ("
            "id SERIAL PRIMARY KEY,"
            "contact_id INTEGER NOT NULL,"
            "ip_address VARCHAR NOT NULL,"
            "device_token VARCHAR NOT NULL DEFAULT '',"
            "organization_id INTEGER,"
            "created_at TIMESTAMPTZ DEFAULT NOW(),"
            "expires_at TIMESTAMPTZ NOT NULL"
            ")"
        ))
        db.execute(text(
            "ALTER TABLE pos_trusted_devices "
            "ADD COLUMN IF NOT EXISTS device_token VARCHAR NOT NULL DEFAULT ''"
        ))
        db.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_pos_trusted_devices_contact_ip "
            "ON pos_trusted_devices (contact_id, ip_address)"
        ))
        db.commit()
        _table_ensured = True
    except Exception as e:
        logger.error("Failed to ensure POS table: %s", e)
        db.rollback()


def _resolve_organization_id(db: Session, lo_slug: Optional[str]) -> int:
    """Resolve organization_id from an LO slug, falling back to default org."""
    if lo_slug:
        lo_user = db.query(User).filter(User.slug == lo_slug).first()
        if lo_user and lo_user.organization_id:
            return lo_user.organization_id

    from database.models.core import Organization
    default_org = (
        db.query(Organization)
        .filter(Organization.is_active == True)
        .order_by(Organization.id)
        .first()
    )
    if default_org:
        return default_org.id

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="No active organization found. Please contact support.",
    )


def _hash_code(code: str) -> str:
    salt = os.getenv("SECRET_KEY")
    if not salt:
        raise RuntimeError("SECRET_KEY environment variable is required for OTP hashing")
    return hmac.new(salt.encode(), code.encode(), hashlib.sha256).hexdigest()


def _client_ip(request: Request) -> str:
    # C2 fix: Use request.client.host (set by Railway's reverse proxy) as the
    # authoritative source. Do NOT trust X-Forwarded-For — it is trivially
    # spoofable and lets attackers bypass IP rate limiting.
    return request.client.host if request.client else "unknown"


# ── Request / Response models ──────────────────────────────────────

class StartRequest(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr
    phone: str = Field("", max_length=20, description="Optional phone for contact records")
    lo_slug: Optional[str] = Field(None, max_length=200, description="Loan officer slug from PURL")

    @field_validator("first_name", "last_name", mode="before")
    @classmethod
    def clean_name(cls, v: str) -> str:
        v = re.sub(r"<[^>]*>", "", v).strip()
        if not v:
            raise ValueError("Name cannot be blank")
        return v


class StartResponse(BaseModel):
    session_id: str
    email_masked: str
    expires_at: str
    message: str


class VerifyRequest(BaseModel):
    session_id: str
    code: str = Field(..., min_length=6, max_length=6)
    remember_device: bool = Field(False, description="Trust this IP for future logins")

    @field_validator("code")
    @classmethod
    def digits_only(cls, v: str) -> str:
        if not v.isdigit():
            raise ValueError("Code must be 6 digits.")
        return v


class VerifyResponse(BaseModel):
    token: str
    workspace_slug: str
    redirect_url: str
    borrower_name: str


class ResendRequest(BaseModel):
    session_id: str


class ResendResponse(BaseModel):
    message: str
    expires_at: str
    cooldown_seconds: int


class LoginRequest(BaseModel):
    email: EmailStr


class LoginResponse(BaseModel):
    session_id: str = ""
    email_masked: str = ""
    expires_at: str = ""
    message: str = ""
    trusted_device: bool = False
    token: str = ""
    workspace_slug: str = ""
    borrower_name: str = ""


class TokenCheckResponse(BaseModel):
    valid: bool
    borrower_name: str = ""


# ── Email helper ──────────────────────────────────────────────────

def _send_verification_email(email_addr: str, code: str):
    try:
        from services.notification_service import NotificationService
        svc = NotificationService()
        svc.send_email(
            to_email=email_addr,
            subject="Your Perennia Verification Code",
            html_content=(
                f"<div style='font-family:system-ui,sans-serif;max-width:480px;margin:0 auto;padding:32px'>"
                f"<h2 style='color:#1F3D2E;margin:0 0 8px'>Verification Code</h2>"
                f"<p style='color:#6B7B75;margin:0 0 24px'>Use the code below to verify your identity.</p>"
                f"<div style='background:#f0fdf4;border:1px solid #86efac;border-radius:12px;"
                f"padding:24px;text-align:center;margin:0 0 24px'>"
                f"<span style='font-size:36px;font-weight:700;letter-spacing:8px;color:#1F3D2E'>{code}</span>"
                f"</div>"
                f"<p style='color:#6B7B75;font-size:13px;margin:0'>"
                f"This code expires in {CODE_TTL_MINUTES} minutes. Do not share this code with anyone.</p>"
                f"</div>"
            ),
            plain_content=(
                f"Your Perennia verification code is: {code}\n\n"
                f"This code expires in {CODE_TTL_MINUTES} minutes. "
                f"Do not share this code with anyone."
            ),
        )
    except Exception as e:
        logger.error("Failed to send verification email to %s: %s", email_addr, e)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not send verification code. Please try again.",
        )


def _mask_email(email_addr: str) -> str:
    if "@" not in email_addr:
        return "***"
    local, domain = email_addr.rsplit("@", 1)
    if len(local) <= 1:
        masked_local = local[0] + "***"
    else:
        masked_local = local[0] + "***" + local[-1]
    return f"{masked_local}@{domain}"


# ── Endpoints ──────────────────────────────────────────────────────

@router.post(
    "/start",
    response_model=StartResponse,
    status_code=status.HTTP_200_OK,
    summary="Start application — sends email verification code",
)
def start_application(body: StartRequest, request: Request, db: Session = Depends(get_db)):
    _ensure_table(db)

    ip = _client_ip(request)
    _check_ip_rate_limit(ip)

    try:
        org_id = _resolve_organization_id(db, body.lo_slug)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("POS start: failed to resolve organization: %s", e)
        raise HTTPException(status_code=500, detail=f"Organization lookup failed: {type(e).__name__}")

    email_lower = body.email.strip().lower()
    dedup_cutoff = datetime.now(timezone.utc) - timedelta(minutes=5)

    try:
        existing = (
            db.query(POSVerification)
            .filter(
                POSVerification.email == email_lower,
                POSVerification.verified_at == None,
                POSVerification.created_at > dedup_cutoff,
            )
            .first()
        )
    except Exception as e:
        logger.exception("POS start: dedup query failed: %s", e)
        db.rollback()
        existing = None

    if existing:
        expires = existing.created_at.replace(tzinfo=timezone.utc) + timedelta(minutes=CODE_TTL_MINUTES)
        return StartResponse(
            session_id=existing.session_id,
            email_masked=_mask_email(email_lower),
            expires_at=expires.isoformat(),
            message="Verification code already sent. Check your email.",
        )

    session_id = f"pos_sess_{secrets.token_hex(16)}"
    code = f"{secrets.randbelow(900000) + 100000}"
    now = datetime.now(timezone.utc)

    phone_raw = body.phone.strip() if body.phone else ""

    verification = POSVerification(
        session_id=session_id,
        phone=phone_raw,
        phone_raw=phone_raw,
        code_hash=_hash_code(code),
        first_name=body.first_name.strip(),
        last_name=body.last_name.strip(),
        email=email_lower,
        organization_id=org_id,
        ip_address=ip,
        consent_at=now,
        created_at=now,
    )

    try:
        db.add(verification)
        db.commit()
    except Exception as e:
        logger.exception("POS start: failed to save verification record: %s", e)
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Could not create verification session: {type(e).__name__}",
        )

    _send_verification_email(email_lower, code)

    expires = now + timedelta(minutes=CODE_TTL_MINUTES)
    return StartResponse(
        session_id=session_id,
        email_masked=_mask_email(email_lower),
        expires_at=expires.isoformat(),
        message="Verification code sent",
    )


@router.post(
    "/verify",
    response_model=VerifyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Verify email code and create application",
)
def verify_code(body: VerifyRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    _ensure_table(db)

    verification = (
        db.query(POSVerification)
        .filter(POSVerification.session_id == body.session_id)
        .with_for_update()
        .first()
    )
    if not verification:
        raise HTTPException(status_code=404, detail="Session expired. Please start over.")

    if verification.verified_at:
        raise HTTPException(status_code=400, detail="This code has already been used.")

    created = verification.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=CODE_TTL_MINUTES)
    if created < cutoff:
        raise HTTPException(status_code=410, detail="Code expired. Please start over.")

    if verification.attempts >= MAX_VERIFY_ATTEMPTS:
        raise HTTPException(status_code=429, detail="Too many failed attempts. Please start over.")

    verification.attempts += 1

    if not hmac.compare_digest(_hash_code(body.code), verification.code_hash):
        db.commit()
        remaining = MAX_VERIFY_ATTEMPTS - verification.attempts
        raise HTTPException(
            status_code=401,
            detail=f"Incorrect code. {remaining} attempt{'s' if remaining != 1 else ''} remaining.",
        )

    verification.verified_at = datetime.now(timezone.utc)
    db.flush()

    org_id = verification.organization_id
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Session missing organization context. Please start over.",
        )

    if verification.flow_type == "login" and verification.contact_id:
        contact = db.query(PURLContact).filter(PURLContact.id == verification.contact_id).first()
        if not contact:
            raise HTTPException(status_code=404, detail="Account not found. Please create a new account.")
        workspace = db.query(PURLWorkspace).filter(PURLWorkspace.id == contact.workspace_id).first()
        if not workspace:
            raise HTTPException(status_code=404, detail="Account not found. Please create a new account.")
        slug = workspace.slug
        borrower_name = contact.first_name or verification.first_name
    else:
        from database.models.pos import POSApplication, POSStatus
        old_contacts = (
            db.query(PURLContact)
            .filter(PURLContact.email == verification.email, PURLContact.organization_id == org_id)
            .all()
        )
        for old_contact in old_contacts:
            db.query(POSApplication).filter(
                POSApplication.contact_id == old_contact.id,
                POSApplication.status == POSStatus.DRAFT,
            ).update({"status": POSStatus.ABANDONED})

        slug = f"{verification.first_name.lower()}-{verification.last_name.lower()}-{uuid.uuid4().hex[:8]}"
        display_name = f"{verification.first_name} {verification.last_name}"

        workspace = PURLWorkspace(
            organization_id=org_id,
            slug=slug,
            status=WorkspaceStatus.APPLICATION.value,
            display_name=display_name,
            source="pos_public_start",
            application_at=datetime.now(timezone.utc),
        )
        db.add(workspace)
        db.flush()

        contact = PURLContact(
            organization_id=org_id,
            workspace_id=workspace.id,
            contact_type=ContactType.BORROWER.value,
            first_name=verification.first_name,
            last_name=verification.last_name,
            email=verification.email,
            phone=verification.phone,
        )
        db.add(contact)
        db.flush()
        borrower_name = verification.first_name

    token_service = PURLTokenService(db)
    _token_id, full_token = token_service.create_token(
        organization_id=org_id,
        workspace_id=workspace.id,
        scope=TokenScope.WRITE,
        contact_id=contact.id,
        expires_in_days=90,
    )

    if body.remember_device:
        ip = _client_ip(request)
        # H2 fix: generate a unique device token stored in a cookie.
        # Trusted device = matching IP AND matching device cookie.
        device_token = uuid.uuid4().hex
        db.query(POSTrustedDevice).filter(
            POSTrustedDevice.contact_id == contact.id,
            POSTrustedDevice.ip_address == ip,
        ).delete()
        db.add(POSTrustedDevice(
            contact_id=contact.id,
            ip_address=ip,
            device_token=device_token,
            organization_id=org_id,
            expires_at=datetime.now(timezone.utc) + timedelta(days=TRUSTED_DEVICE_DAYS),
        ))
        response.set_cookie(
            key="pos_device_token",
            value=device_token,
            max_age=TRUSTED_DEVICE_DAYS * 86400,
            httponly=True,
            secure=True,
            samesite="strict",
        )

    db.commit()
    base_url = os.getenv("POS_REDIRECT_BASE_URL", "https://app.perenniaai.com")
    redirect_url = f"{base_url}/pos?token={full_token}"

    return VerifyResponse(
        token=full_token,
        workspace_slug=slug,
        redirect_url=redirect_url,
        borrower_name=borrower_name,
    )


@router.post(
    "/resend",
    response_model=ResendResponse,
    status_code=status.HTTP_200_OK,
    summary="Resend verification code (60s cooldown)",
)
def resend_code(body: ResendRequest, request: Request, db: Session = Depends(get_db)):
    _ensure_table(db)

    verification = (
        db.query(POSVerification)
        .filter(POSVerification.session_id == body.session_id)
        .first()
    )
    if not verification:
        raise HTTPException(status_code=404, detail="Session expired. Please start over.")

    if verification.verified_at:
        raise HTTPException(status_code=400, detail="Already verified.")

    now = datetime.now(timezone.utc)

    if verification.last_resend_at:
        resend_at = verification.last_resend_at
        if resend_at.tzinfo is None:
            resend_at = resend_at.replace(tzinfo=timezone.utc)
        elapsed = (now - resend_at).total_seconds()
        if elapsed < RESEND_COOLDOWN_SECONDS:
            wait = int(RESEND_COOLDOWN_SECONDS - elapsed)
            raise HTTPException(
                status_code=429,
                detail=f"Please wait {wait} seconds before requesting a new code.",
            )

    code = f"{secrets.randbelow(900000) + 100000}"
    verification.code_hash = _hash_code(code)
    verification.attempts = 0
    verification.created_at = now
    verification.last_resend_at = now
    db.commit()

    _send_verification_email(verification.email, code)

    expires = now + timedelta(minutes=CODE_TTL_MINUTES)
    return ResendResponse(
        message="New verification code sent",
        expires_at=expires.isoformat(),
        cooldown_seconds=RESEND_COOLDOWN_SECONDS,
    )


@router.post(
    "/login",
    response_model=LoginResponse,
    status_code=status.HTTP_200_OK,
    summary="Sign in with email — sends email verification code",
)
async def login_start(body: LoginRequest, request: Request, db: Session = Depends(get_db)):
    _ensure_table(db)

    ip = _client_ip(request)
    _check_ip_rate_limit(ip)

    email_lower = body.email.strip().lower()

    # C1 fix: always return the same response shape to prevent account enumeration.
    # Never reveal whether the email exists via different status codes or messages.
    generic_message = "If an account exists, a verification code has been sent."

    contact = (
        db.query(PURLContact)
        .filter(PURLContact.email == email_lower)
        .order_by(PURLContact.id.desc())
        .first()
    )
    if not contact:
        # No account — return generic response. Do NOT send email or reveal absence.
        # M1 fix: Sleep a random duration to match the typical latency of the
        # "account exists" path (DB queries + email send = 200-2000ms). Without
        # this, an attacker can distinguish account existence via response time.
        await asyncio.sleep(random.uniform(0.5, 1.5))
        return LoginResponse(
            session_id="",
            email_masked=_mask_email(email_lower),
            expires_at="",
            message=generic_message,
        )

    now = datetime.now(timezone.utc)
    device_cookie = request.cookies.get("pos_device_token", "")
    trusted = (
        db.query(POSTrustedDevice)
        .filter(
            POSTrustedDevice.contact_id == contact.id,
            POSTrustedDevice.ip_address == ip,
            POSTrustedDevice.device_token == device_cookie,
            POSTrustedDevice.expires_at > now,
        )
        .first()
    ) if device_cookie else None
    if trusted:
        workspace = db.query(PURLWorkspace).filter(PURLWorkspace.id == contact.workspace_id).first()
        if workspace:
            token_service = PURLTokenService(db)
            _token_id, full_token = token_service.create_token(
                organization_id=contact.organization_id,
                workspace_id=workspace.id,
                scope=TokenScope.WRITE,
                contact_id=contact.id,
                expires_in_days=90,
            )
            trusted.created_at = now
            trusted.expires_at = now + timedelta(days=TRUSTED_DEVICE_DAYS)
            db.commit()
            return LoginResponse(
                trusted_device=True,
                token=full_token,
                workspace_slug=workspace.slug,
                borrower_name=contact.first_name or "",
                message="Welcome back! Device recognized.",
            )

    dedup_cutoff = now - timedelta(minutes=5)
    existing = (
        db.query(POSVerification)
        .filter(
            POSVerification.email == email_lower,
            POSVerification.flow_type == "login",
            POSVerification.verified_at == None,
            POSVerification.created_at > dedup_cutoff,
        )
        .first()
    )
    if existing:
        expires = existing.created_at.replace(tzinfo=timezone.utc) + timedelta(minutes=CODE_TTL_MINUTES)
        return LoginResponse(
            session_id=existing.session_id,
            email_masked=_mask_email(email_lower),
            expires_at=expires.isoformat(),
            message=generic_message,
        )

    session_id = f"pos_sess_{secrets.token_hex(16)}"
    code = f"{secrets.randbelow(900000) + 100000}"

    verification = POSVerification(
        session_id=session_id,
        phone=contact.phone or "",
        phone_raw=contact.phone or "",
        code_hash=_hash_code(code),
        first_name=contact.first_name or "",
        last_name=contact.last_name or "",
        email=email_lower,
        organization_id=contact.organization_id,
        flow_type="login",
        contact_id=contact.id,
        ip_address=ip,
        consent_at=now,
        created_at=now,
    )
    db.add(verification)
    db.commit()

    _send_verification_email(email_lower, code)

    expires = now + timedelta(minutes=CODE_TTL_MINUTES)
    return LoginResponse(
        session_id=session_id,
        email_masked=_mask_email(email_lower),
        expires_at=expires.isoformat(),
        message=generic_message,
    )


class LoginDemoRequest(BaseModel):
    email: EmailStr


class LoginDemoResponse(BaseModel):
    token: str
    workspace_slug: str
    borrower_name: str


@router.post(
    "/login-demo",
    response_model=LoginDemoResponse,
    status_code=status.HTTP_200_OK,
    summary="Demo login — returns token directly without email verification",
)
def login_demo(body: LoginDemoRequest, request: Request, db: Session = Depends(get_db)):
    if os.getenv("ENVIRONMENT", "production").lower() not in ("development", "test"):
        raise HTTPException(status_code=404, detail="Not found")
    _ensure_table(db)

    ip = _client_ip(request)
    _check_ip_rate_limit(ip)

    email_lower = body.email.strip().lower()

    contact = (
        db.query(PURLContact)
        .filter(PURLContact.email == email_lower)
        .order_by(PURLContact.id.desc())
        .first()
    )
    if not contact:
        raise HTTPException(status_code=404, detail="No account found with this email. Please create a new account.")

    workspace = db.query(PURLWorkspace).filter(PURLWorkspace.id == contact.workspace_id).first()
    if not workspace:
        raise HTTPException(status_code=404, detail="No account found. Please create a new account.")

    token_service = PURLTokenService(db)
    _token_id, full_token = token_service.create_token(
        organization_id=contact.organization_id,
        workspace_id=workspace.id,
        scope=TokenScope.WRITE,
        contact_id=contact.id,
        expires_in_days=90,
    )
    db.commit()

    return LoginDemoResponse(
        token=full_token,
        workspace_slug=workspace.slug,
        borrower_name=contact.first_name or "",
    )


class DemoStartRequest(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr
    phone: str = Field("", max_length=20)
    lo_slug: Optional[str] = Field(None, max_length=200)

    @field_validator("first_name", "last_name", mode="before")
    @classmethod
    def clean_name(cls, v: str) -> str:
        v = re.sub(r"<[^>]*>", "", v).strip()
        if not v:
            raise ValueError("Name cannot be blank")
        return v


class DemoStartResponse(BaseModel):
    token: str
    workspace_slug: str
    borrower_name: str


@router.post(
    "/start-demo",
    response_model=DemoStartResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Demo start — creates application immediately without email verification",
)
def start_demo(body: DemoStartRequest, request: Request, db: Session = Depends(get_db)):
    if os.getenv("ENVIRONMENT", "production").lower() not in ("development", "test"):
        raise HTTPException(status_code=404, detail="Not found")
    phase = "ensure_table"
    try:
        _ensure_table(db)

        ip = _client_ip(request)
        _check_ip_rate_limit(ip)

        phase = "resolve_org"
        try:
            org_id = _resolve_organization_id(db, body.lo_slug)
        except HTTPException:
            raise
        except Exception as e:
            logger.exception("POS demo start[resolve_org]: failed for lo_slug=%r: %s", body.lo_slug, e)
            raise HTTPException(status_code=500, detail=f"Organization lookup failed: {type(e).__name__}")

        email_lower = body.email.strip().lower()

        phase = "abandon_old_drafts"
        from database.models.pos import POSApplication, POSStatus
        existing_contacts = (
            db.query(PURLContact)
            .filter(PURLContact.email == email_lower, PURLContact.organization_id == org_id)
            .all()
        )
        for old_contact in existing_contacts:
            db.query(POSApplication).filter(
                POSApplication.contact_id == old_contact.id,
                POSApplication.status == POSStatus.DRAFT,
            ).update({"status": POSStatus.ABANDONED})

        slug = f"{body.first_name.strip().lower()}-{body.last_name.strip().lower()}-{uuid.uuid4().hex[:8]}"
        display_name = f"{body.first_name.strip()} {body.last_name.strip()}"
        phone_raw = body.phone.strip() if body.phone else ""

        phase = "create_workspace"
        workspace = PURLWorkspace(
            organization_id=org_id,
            slug=slug,
            status=WorkspaceStatus.APPLICATION.value,
            display_name=display_name,
            source="pos_demo",
            application_at=datetime.now(timezone.utc),
        )
        db.add(workspace)
        db.flush()

        phase = "create_contact"
        contact = PURLContact(
            organization_id=org_id,
            workspace_id=workspace.id,
            contact_type=ContactType.BORROWER.value,
            first_name=body.first_name.strip(),
            last_name=body.last_name.strip(),
            email=email_lower,
            phone=phone_raw,
        )
        db.add(contact)
        db.flush()

        phase = "issue_token_new"
        token_service = PURLTokenService(db)
        _token_id, full_token = token_service.create_token(
            organization_id=org_id,
            workspace_id=workspace.id,
            scope=TokenScope.WRITE,
            contact_id=contact.id,
            expires_in_days=90,
        )

        phase = "commit_new"
        db.commit()
        logger.info(
            "POS demo start: created workspace=%d contact=%d slug=%s for email=%s",
            workspace.id, contact.id, slug, email_lower,
        )
        return DemoStartResponse(
            token=full_token,
            workspace_slug=slug,
            borrower_name=body.first_name.strip(),
        )

    except HTTPException:
        raise
    except Exception as e:
        # Roll back so the next request on this connection isn't in a poisoned
        # transaction. Log the phase tag + exception type so production logs
        # tell us exactly which step blew up — the user-facing response is
        # sanitized to "Internal server error" by the global handler.
        try:
            db.rollback()
        except Exception:
            pass
        logger.exception(
            "POS demo start[%s] failed for email=%s lo_slug=%r: %s: %s",
            phase, body.email, body.lo_slug, type(e).__name__, e,
        )
        raise HTTPException(
            status_code=500,
            detail=f"start-demo failed at phase={phase} error={type(e).__name__}",
        )


@router.post(
    "/check-token",
    response_model=TokenCheckResponse,
    status_code=status.HTTP_200_OK,
    summary="Validate an existing PURL token before entering the app",
)
def check_token(request: Request, db: Session = Depends(get_db)):
    auth_header = request.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        return TokenCheckResponse(valid=False)

    token = auth_header[7:]
    try:
        token_service = PURLTokenService(db)
        ctx = token_service.verify_token(token)
        if not ctx:
            return TokenCheckResponse(valid=False)
        contact = db.query(PURLContact).filter(PURLContact.id == ctx.get("contact_id")).first()
        name = contact.first_name if contact else ""
        return TokenCheckResponse(valid=True, borrower_name=name or "")
    except Exception:
        return TokenCheckResponse(valid=False)
