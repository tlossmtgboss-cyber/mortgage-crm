"""Public POS start + SMS verification endpoints.

Flow:
1. POST /pos/start  — collect info, send 6-digit SMS code, return session_id
2. POST /pos/verify — validate code, create workspace/contact/token
3. POST /pos/resend — resend code with rate limiting

Enterprise hardening:
- Phone normalization to E.164 before send
- IP-based rate limiting (5 starts / 10 min per IP)
- Per-session rate limiting on resend (60s cooldown)
- Duplicate email+phone dedup within 5 min (reuse existing session)
- HMAC-SHA256 code hashing with SECRET_KEY
- Code expiry (10 min), max attempts (5)
- TCPA consent timestamp stored
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
import uuid
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from threading import Lock
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import Column, DateTime, Integer, String, text
from sqlalchemy.orm import Session

from database import Base, get_db
from database.models.core import User
from models.purl import (
    ContactType,
    PURLContact,
    PURLWorkspace,
    TokenScope,
    WorkspaceStatus,
)
from services.purl_token_service import PURLTokenService
from telephony.phone_utils import normalize_phone

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/pos", tags=["POS - Public Start"])
CODE_TTL_MINUTES = 10
MAX_VERIFY_ATTEMPTS = 5
RESEND_COOLDOWN_SECONDS = 60
IP_RATE_LIMIT = 5
IP_RATE_WINDOW_MINUTES = 10


# ── IP rate limiter (in-memory, resets on deploy) ──────────────────

_ip_tracker: dict[str, list[float]] = defaultdict(list)
_ip_lock = Lock()


def _check_ip_rate_limit(ip: str):
    now = datetime.now(timezone.utc).timestamp()
    cutoff = now - (IP_RATE_WINDOW_MINUTES * 60)
    with _ip_lock:
        # Evict oldest entries if tracker grows too large (prevent unbounded growth)
        if len(_ip_tracker) > 10000:
            oldest_keys = sorted(
                _ip_tracker.keys(),
                key=lambda k: min(_ip_tracker[k]) if _ip_tracker[k] else 0,
            )[:5000]
            for k in oldest_keys:
                del _ip_tracker[k]

        timestamps = [t for t in _ip_tracker.get(ip, []) if t > cutoff]
        if not timestamps:
            # Clean up empty entries
            _ip_tracker.pop(ip, None)
        else:
            _ip_tracker[ip] = timestamps

        if len(_ip_tracker.get(ip, [])) >= IP_RATE_LIMIT:
            raise HTTPException(
                status_code=429,
                detail="Too many requests. Please try again in a few minutes.",
            )
        _ip_tracker.setdefault(ip, []).append(now)


# ── OTP storage model ──────────────────────────────────────────────

class POSVerification(Base):
    __tablename__ = "pos_verifications"
    id = Column(Integer, primary_key=True)
    session_id = Column(String, unique=True, nullable=False, index=True)
    phone = Column(String, nullable=False)
    phone_raw = Column(String, nullable=False, default="")
    code_hash = Column(String, nullable=False)
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    email = Column(String, nullable=False)
    organization_id = Column(Integer, nullable=True)
    attempts = Column(Integer, default=0)
    ip_address = Column(String, nullable=True)
    consent_at = Column(DateTime(timezone=True), nullable=True)
    last_resend_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    verified_at = Column(DateTime(timezone=True), nullable=True)


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
        db.commit()
        _table_ensured = True
    except Exception as e:
        logger.error("Failed to ensure POS table: %s", e)
        db.rollback()


def _resolve_organization_id(db: Session, lo_slug: Optional[str]) -> int:
    """Resolve organization_id from an LO slug. Raises 400 if slug invalid."""
    if not lo_slug:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing loan officer identifier (lo_slug). Please use the link provided by your loan officer.",
        )
    lo_user = db.query(User).filter(User.slug == lo_slug).first()
    if not lo_user or not lo_user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid loan officer link. Please contact your loan officer for a new link.",
        )
    return lo_user.organization_id


def _hash_code(code: str) -> str:
    salt = os.getenv("SECRET_KEY", "pos-otp-salt")
    return hmac.new(salt.encode(), code.encode(), hashlib.sha256).hexdigest()


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# ── Request / Response models ──────────────────────────────────────

class StartRequest(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr
    phone: str = Field(..., min_length=10, max_length=20)
    sms_consent: bool = Field(..., description="User consented to receive SMS")
    lo_slug: Optional[str] = Field(None, max_length=200, description="Loan officer slug from PURL")

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        normalized = normalize_phone(v.strip())
        if not normalized:
            raise ValueError("Please enter a valid 10-digit US phone number.")
        return v.strip()

    @field_validator("sms_consent")
    @classmethod
    def require_consent(cls, v: bool) -> bool:
        if not v:
            raise ValueError("SMS consent is required to proceed.")
        return v


class StartResponse(BaseModel):
    session_id: str
    phone_masked: str
    expires_at: str
    message: str


class VerifyRequest(BaseModel):
    session_id: str
    code: str = Field(..., min_length=6, max_length=6)

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


# ── SMS helper ─────────────────────────────────────────────────────

def _send_verification_sms(phone_e164: str, code: str):
    try:
        from telephony.sms import send_sms
        send_sms(
            to=phone_e164,
            text=(
                f"Your Perennia verification code is: {code}\n\n"
                f"This code expires in {CODE_TTL_MINUTES} minutes. "
                f"Do not share this code with anyone."
            ),
            bypass_compliance=True,
        )
    except Exception as e:
        logger.error("Failed to send verification SMS to %s: %s", phone_e164, e)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not send verification code. Please try again.",
        )


def _mask_phone(phone: str) -> str:
    digits = "".join(c for c in phone if c.isdigit())
    if len(digits) >= 10:
        last4 = digits[-4:]
        return f"(***) ***-{last4}"
    return "***"


# ── Endpoints ──────────────────────────────────────────────────────

@router.post(
    "/start",
    response_model=StartResponse,
    status_code=status.HTTP_200_OK,
    summary="Start application — sends SMS verification code",
)
def start_application(body: StartRequest, request: Request, db: Session = Depends(get_db)):
    _ensure_table(db)

    ip = _client_ip(request)
    _check_ip_rate_limit(ip)

    # Resolve organization from LO slug (tenant isolation)
    org_id = _resolve_organization_id(db, body.lo_slug)

    phone_e164 = normalize_phone(body.phone)
    if not phone_e164:
        raise HTTPException(status_code=422, detail="Invalid phone number format.")

    email_lower = body.email.strip().lower()
    dedup_cutoff = datetime.now(timezone.utc) - timedelta(minutes=5)
    existing = (
        db.query(POSVerification)
        .filter(
            POSVerification.email == email_lower,
            POSVerification.phone == phone_e164,
            POSVerification.verified_at == None,
            POSVerification.created_at > dedup_cutoff,
        )
        .first()
    )
    if existing:
        expires = existing.created_at.replace(tzinfo=timezone.utc) + timedelta(minutes=CODE_TTL_MINUTES)
        return StartResponse(
            session_id=existing.session_id,
            phone_masked=_mask_phone(phone_e164),
            expires_at=expires.isoformat(),
            message="Verification code already sent. Check your phone.",
        )

    session_id = f"pos_sess_{secrets.token_hex(16)}"
    code = f"{secrets.randbelow(900000) + 100000}"
    now = datetime.now(timezone.utc)

    verification = POSVerification(
        session_id=session_id,
        phone=phone_e164,
        phone_raw=body.phone.strip(),
        code_hash=_hash_code(code),
        first_name=body.first_name.strip(),
        last_name=body.last_name.strip(),
        email=email_lower,
        organization_id=org_id,
        ip_address=ip,
        consent_at=now,
        created_at=now,
    )
    db.add(verification)
    db.commit()

    _send_verification_sms(phone_e164, code)

    expires = now + timedelta(minutes=CODE_TTL_MINUTES)
    return StartResponse(
        session_id=session_id,
        phone_masked=_mask_phone(phone_e164),
        expires_at=expires.isoformat(),
        message="Verification code sent",
    )


@router.post(
    "/verify",
    response_model=VerifyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Verify SMS code and create application",
)
def verify_code(body: VerifyRequest, db: Session = Depends(get_db)):
    _ensure_table(db)

    verification = (
        db.query(POSVerification)
        .filter(POSVerification.session_id == body.session_id)
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

    slug = f"{verification.first_name.lower()}-{verification.last_name.lower()}-{uuid.uuid4().hex[:8]}"
    display_name = f"{verification.first_name} {verification.last_name}"
    org_id = verification.organization_id
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Session missing organization context. Please start over.",
        )

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

    token_service = PURLTokenService(db)
    _token_id, full_token = token_service.create_token(
        organization_id=org_id,
        workspace_id=workspace.id,
        scope=TokenScope.WRITE,
        contact_id=contact.id,
        expires_in_days=90,
    )

    db.commit()
    redirect_url = f"https://app.perenniaai.com/pos?token={full_token}"

    return VerifyResponse(
        token=full_token,
        workspace_slug=slug,
        redirect_url=redirect_url,
        borrower_name=verification.first_name,
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

    _send_verification_sms(verification.phone, code)

    expires = now + timedelta(minutes=CODE_TTL_MINUTES)
    return ResendResponse(
        message="New verification code sent",
        expires_at=expires.isoformat(),
        cooldown_seconds=RESEND_COOLDOWN_SECONDS,
    )
