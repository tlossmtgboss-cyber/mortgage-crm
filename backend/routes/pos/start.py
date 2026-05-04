"""Public POS start + SMS verification endpoints.

Flow:
1. POST /pos/start  — collect info, send 6-digit SMS code, return session_id
2. POST /pos/verify — validate code, create workspace/contact/token, return token
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
import uuid
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import Column, DateTime, Integer, String, text
from sqlalchemy.orm import Session

from database import Base, get_db
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

DEFAULT_ORG_ID = 1
CODE_TTL_MINUTES = 10
MAX_VERIFY_ATTEMPTS = 5


# ── OTP storage model ──────────────────────────────────────────────

class POSVerification(Base):
    __tablename__ = "pos_verifications"
    id = Column(Integer, primary_key=True)
    session_id = Column(String, unique=True, nullable=False, index=True)
    phone = Column(String, nullable=False)
    code_hash = Column(String, nullable=False)
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    email = Column(String, nullable=False)
    attempts = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    verified_at = Column(DateTime(timezone=True), nullable=True)


def _ensure_table(db: Session):
    try:
        db.execute(text(
            "CREATE TABLE IF NOT EXISTS pos_verifications ("
            "id SERIAL PRIMARY KEY,"
            "session_id VARCHAR UNIQUE NOT NULL,"
            "phone VARCHAR NOT NULL,"
            "code_hash VARCHAR NOT NULL,"
            "first_name VARCHAR NOT NULL,"
            "last_name VARCHAR NOT NULL,"
            "email VARCHAR NOT NULL,"
            "attempts INTEGER DEFAULT 0,"
            "created_at TIMESTAMPTZ DEFAULT NOW(),"
            "verified_at TIMESTAMPTZ"
            ")"
        ))
        db.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_pos_verifications_session_id "
            "ON pos_verifications (session_id)"
        ))
        db.commit()
    except Exception:
        db.rollback()


def _hash_code(code: str) -> str:
    salt = os.getenv("SECRET_KEY", "pos-otp-salt")
    return hmac.new(salt.encode(), code.encode(), hashlib.sha256).hexdigest()


# ── Request / Response models ──────────────────────────────────────

class StartRequest(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr
    phone: str = Field(..., min_length=10, max_length=20)


class StartResponse(BaseModel):
    session_id: str
    message: str


class VerifyRequest(BaseModel):
    session_id: str
    code: str = Field(..., min_length=6, max_length=6)


class VerifyResponse(BaseModel):
    token: str
    workspace_slug: str
    redirect_url: str


class ResendRequest(BaseModel):
    session_id: str


class ResendResponse(BaseModel):
    message: str


# ── SMS helper ─────────────────────────────────────────────────────

def _send_verification_sms(phone: str, code: str):
    try:
        from telephony.sms import send_sms
        send_sms(
            to=phone,
            text=f"Your Perennia verification code is: {code}",
            bypass_compliance=True,
        )
    except Exception as e:
        logger.error("Failed to send verification SMS to %s: %s", phone, e)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not send verification code. Please try again.",
        )


# ── Endpoints ──────────────────────────────────────────────────────

@router.post(
    "/start",
    response_model=StartResponse,
    status_code=status.HTTP_200_OK,
    summary="Start application — sends SMS verification code",
)
def start_application(body: StartRequest, db: Session = Depends(get_db)):
    _ensure_table(db)

    session_id = f"pos_sess_{secrets.token_hex(16)}"
    code = f"{secrets.randbelow(900000) + 100000}"

    verification = POSVerification(
        session_id=session_id,
        phone=body.phone.strip(),
        code_hash=_hash_code(code),
        first_name=body.first_name.strip(),
        last_name=body.last_name.strip(),
        email=body.email.strip(),
    )
    db.add(verification)
    db.commit()

    _send_verification_sms(body.phone.strip(), code)

    return StartResponse(
        session_id=session_id,
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
        raise HTTPException(status_code=404, detail="Session not found. Please start over.")

    if verification.verified_at:
        raise HTTPException(status_code=400, detail="Code already used. Please start over.")

    cutoff = datetime.now(timezone.utc) - timedelta(minutes=CODE_TTL_MINUTES)
    if verification.created_at.replace(tzinfo=timezone.utc) < cutoff:
        raise HTTPException(status_code=410, detail="Code expired. Please start over.")

    if verification.attempts >= MAX_VERIFY_ATTEMPTS:
        raise HTTPException(status_code=429, detail="Too many attempts. Please start over.")

    verification.attempts += 1

    if not hmac.compare_digest(_hash_code(body.code), verification.code_hash):
        db.commit()
        remaining = MAX_VERIFY_ATTEMPTS - verification.attempts
        raise HTTPException(
            status_code=401,
            detail=f"Invalid code. {remaining} attempt(s) remaining.",
        )

    verification.verified_at = datetime.now(timezone.utc)
    db.flush()

    slug = f"{verification.first_name.lower()}-{verification.last_name.lower()}-{uuid.uuid4().hex[:8]}"
    display_name = f"{verification.first_name} {verification.last_name}"

    workspace = PURLWorkspace(
        organization_id=DEFAULT_ORG_ID,
        slug=slug,
        status=WorkspaceStatus.APPLICATION.value,
        display_name=display_name,
        source="pos_public_start",
        application_at=datetime.now(timezone.utc),
    )
    db.add(workspace)
    db.flush()

    contact = PURLContact(
        organization_id=DEFAULT_ORG_ID,
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
        organization_id=DEFAULT_ORG_ID,
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
    )


@router.post(
    "/resend",
    response_model=ResendResponse,
    status_code=status.HTTP_200_OK,
    summary="Resend verification code",
)
def resend_code(body: ResendRequest, db: Session = Depends(get_db)):
    _ensure_table(db)

    verification = (
        db.query(POSVerification)
        .filter(POSVerification.session_id == body.session_id)
        .first()
    )
    if not verification:
        raise HTTPException(status_code=404, detail="Session not found. Please start over.")

    if verification.verified_at:
        raise HTTPException(status_code=400, detail="Already verified.")

    code = f"{secrets.randbelow(900000) + 100000}"
    verification.code_hash = _hash_code(code)
    verification.attempts = 0
    verification.created_at = datetime.now(timezone.utc)
    db.commit()

    _send_verification_sms(verification.phone, code)

    return ResendResponse(message="New verification code sent")
