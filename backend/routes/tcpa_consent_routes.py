"""
TCPA Consent Certificate Routes

API endpoints for managing TCPA consent certificates under the FCC's
one-to-one consent rule effective April 11, 2026.

Every outbound automated call or text must be preceded by a consent lookup.
These endpoints cover the full consent lifecycle:
  - Recording a new consent grant (with evidence capture)
  - Checking active consent status before a call/text
  - Revoking consent (required to be processed within 10 business days per FCC)
  - Full audit trail retrieval per contact
  - Expiring-consent report for proactive renewal
  - Pre-call verification gate

Endpoints:
    POST /api/v1/compliance/tcpa/consent
        Record a new consent grant.

    GET  /api/v1/compliance/tcpa/consent/{phone_number}
        Return current active consent status for a phone number.

    POST /api/v1/compliance/tcpa/consent/revoke
        Revoke an existing consent record.

    GET  /api/v1/compliance/tcpa/consent/audit/{contact_id}
        Full consent audit trail for a contact (all grants and revocations).

    GET  /api/v1/compliance/tcpa/consent/expiring
        List consents expiring within N days (default 30).

    POST /api/v1/compliance/tcpa/consent/verify-before-call
        Pre-call/pre-text consent gate — returns go/no-go with reason.

Registration pattern: APIRouter (not function-based) — mount in main.py with:
    from routes.tcpa_consent_routes import router as tcpa_consent_router
    app.include_router(tcpa_consent_router)
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, validator
from sqlalchemy.orm import Session

from auth.dependencies import get_current_user
from database.models.tcpa_consent import TCPAConsent
from db import get_db

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/compliance/tcpa",
    tags=["tcpa-compliance"],
    dependencies=[Depends(get_current_user)],
)


# =============================================================================
# Request / Response Schemas
# =============================================================================

class ConsentGrantRequest(BaseModel):
    """Request payload for recording a new TCPA consent grant."""

    contact_id: str = Field(
        ...,
        description="UUID of the lead, borrower, or referral partner.",
    )
    contact_type: str = Field(
        ...,
        description='One of: "lead", "borrower", "referral_partner".',
    )
    phone_number: str = Field(
        ...,
        description="E.164 or local format phone number.",
        min_length=7,
        max_length=20,
    )
    consent_type: str = Field(
        ...,
        description='One of: "express_written", "express_oral", "implied".',
    )
    consent_channel: str = Field(
        ...,
        description='One of: "call", "sms", "both".',
    )
    consent_source: Optional[str] = Field(
        None,
        description='How consent was captured, e.g. "web_form", "paper_form", "verbal_recording", "app_signup".',
    )
    consent_text: Optional[str] = Field(
        None,
        description="Verbatim disclosure language shown/read to the contact.",
    )
    consent_ip_address: Optional[str] = Field(
        None,
        description="IP address of the contact at the time of consent (web forms).",
    )
    consent_user_agent: Optional[str] = Field(
        None,
        description="Browser user-agent string at time of consent.",
    )
    expires_at: Optional[datetime] = Field(
        None,
        description="Optional expiration date/time for this consent. NULL means no expiry.",
    )
    recording_url: Optional[str] = Field(
        None,
        description="URL to a call recording capturing verbal consent.",
    )
    document_url: Optional[str] = Field(
        None,
        description="URL to a signed consent form (PDF, e-sign document).",
    )

    @validator("contact_type")
    def validate_contact_type(cls, v):
        allowed = {"lead", "borrower", "referral_partner"}
        if v not in allowed:
            raise ValueError(f"contact_type must be one of {allowed}")
        return v

    @validator("consent_type")
    def validate_consent_type(cls, v):
        allowed = {"express_written", "express_oral", "implied"}
        if v not in allowed:
            raise ValueError(f"consent_type must be one of {allowed}")
        return v

    @validator("consent_channel")
    def validate_consent_channel(cls, v):
        allowed = {"call", "sms", "both"}
        if v not in allowed:
            raise ValueError(f"consent_channel must be one of {allowed}")
        return v


class ConsentGrantResponse(BaseModel):
    """Response after recording a consent grant."""

    id: str
    phone_number: str
    contact_id: str
    contact_type: str
    consent_type: str
    consent_channel: str
    is_active: bool
    granted_at: datetime
    expires_at: Optional[datetime]
    message: str


class ConsentStatusResponse(BaseModel):
    """Current consent status for a phone number."""

    phone_number: str
    has_active_consent: bool
    consent_id: Optional[str]
    consent_type: Optional[str]
    consent_channel: Optional[str]
    granted_at: Optional[datetime]
    expires_at: Optional[datetime]
    call_permitted: bool
    sms_permitted: bool
    message: str


class ConsentRevokeRequest(BaseModel):
    """Request payload to revoke a consent record."""

    phone_number: str = Field(
        ...,
        description="Phone number whose consent is being revoked.",
        min_length=7,
        max_length=20,
    )
    revocation_method: str = Field(
        ...,
        description='How the revocation was received: "text_reply", "phone_request", "email", "portal", "manual".',
    )
    contact_id: Optional[str] = Field(
        None,
        description="Limit revocation to a specific contact UUID (optional — revokes all active consents for the phone if omitted).",
    )

    @validator("revocation_method")
    def validate_revocation_method(cls, v):
        allowed = {"text_reply", "phone_request", "email", "portal", "manual"}
        if v not in allowed:
            raise ValueError(f"revocation_method must be one of {allowed}")
        return v


class ConsentRevokeResponse(BaseModel):
    """Response after revoking consent."""

    revoked_count: int
    phone_number: str
    revocation_method: str
    revoked_at: datetime
    message: str


class ConsentAuditEntry(BaseModel):
    """Single entry in a contact's consent audit trail."""

    id: str
    phone_number: str
    consent_type: str
    consent_channel: str
    consent_source: Optional[str]
    is_active: bool
    granted_at: datetime
    expires_at: Optional[datetime]
    revoked_at: Optional[datetime]
    revocation_method: Optional[str]
    revocation_processed_at: Optional[datetime]
    recording_url: Optional[str]
    document_url: Optional[str]
    created_at: datetime


class ConsentAuditResponse(BaseModel):
    """Full consent audit trail for a contact."""

    contact_id: str
    total_records: int
    active_count: int
    revoked_count: int
    records: List[ConsentAuditEntry]


class ExpiringConsentEntry(BaseModel):
    """A consent that is expiring soon."""

    id: str
    phone_number: str
    contact_id: str
    contact_type: str
    consent_channel: str
    granted_at: datetime
    expires_at: datetime
    days_until_expiry: int


class ExpiringConsentsResponse(BaseModel):
    """List of soon-to-expire consents."""

    days_ahead: int
    total: int
    consents: List[ExpiringConsentEntry]


class VerifyBeforeCallRequest(BaseModel):
    """Pre-call consent verification request."""

    phone_number: str = Field(
        ...,
        description="Phone number to be dialled or texted.",
        min_length=7,
        max_length=20,
    )
    channel: str = Field(
        default="call",
        description='Channel being used: "call" or "sms".',
    )
    contact_id: Optional[str] = Field(
        None,
        description="Contact UUID for a more specific lookup.",
    )

    @validator("channel")
    def validate_channel(cls, v):
        allowed = {"call", "sms"}
        if v not in allowed:
            raise ValueError(f"channel must be one of {allowed}")
        return v


class VerifyBeforeCallResponse(BaseModel):
    """Result of a pre-call consent verification."""

    permitted: bool
    phone_number: str
    channel: str
    consent_id: Optional[str]
    consent_type: Optional[str]
    granted_at: Optional[datetime]
    expires_at: Optional[datetime]
    reason: str  # Human-readable explanation for the go/no-go decision


# =============================================================================
# Helper utilities
# =============================================================================

def _get_org_id(current_user) -> str:
    """Extract the organisation UUID from the authenticated user object."""
    org_id = getattr(current_user, "organization_id", None)
    if org_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User has no associated organisation.",
        )
    return str(org_id)


def _consent_channel_permits(consent_channel: str, requested_channel: str) -> bool:
    """Return True if the stored consent channel covers the requested channel."""
    if consent_channel == "both":
        return True
    return consent_channel == requested_channel


# =============================================================================
# Endpoints
# =============================================================================

@router.post(
    "/consent",
    response_model=ConsentGrantResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record a new TCPA consent grant",
    description=(
        "Store a new consent certificate for a phone number. Under the FCC's "
        "one-to-one consent rule (effective April 11, 2026) each record must "
        "identify this company specifically and capture the verbatim disclosure "
        "text presented to the consumer."
    ),
)
async def record_consent(
    payload: ConsentGrantRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Record a new TCPA consent grant."""
    org_id = _get_org_id(current_user)
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    try:
        contact_uuid = uuid.UUID(payload.contact_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"contact_id is not a valid UUID: {payload.contact_id}",
        )

    created_by_id = None
    raw_created_by = getattr(current_user, "id", None)
    if raw_created_by is not None:
        try:
            created_by_id = uuid.UUID(str(raw_created_by))
        except (ValueError, AttributeError):
            created_by_id = None

    record = TCPAConsent(
        organization_id=uuid.UUID(str(org_id)),
        contact_id=contact_uuid,
        contact_type=payload.contact_type,
        phone_number=payload.phone_number,
        consent_type=payload.consent_type,
        consent_channel=payload.consent_channel,
        consent_source=payload.consent_source,
        consent_text=payload.consent_text,
        consent_ip_address=payload.consent_ip_address,
        consent_user_agent=payload.consent_user_agent,
        is_active=True,
        granted_at=now,
        expires_at=payload.expires_at,
        recording_url=payload.recording_url,
        document_url=payload.document_url,
        created_by=created_by_id,
        created_at=now,
        updated_at=now,
    )

    try:
        db.add(record)
        db.commit()
        db.refresh(record)
    except Exception as e:
        db.rollback()
        logger.exception("Failed to record TCPA consent for phone %s", payload.phone_number)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save consent record.",
        ) from e

    logger.info(
        "TCPA consent recorded: id=%s phone=%s type=%s channel=%s by_user=%s",
        record.id,
        record.phone_number,
        record.consent_type,
        record.consent_channel,
        getattr(current_user, "id", "unknown"),
    )

    return ConsentGrantResponse(
        id=str(record.id),
        phone_number=record.phone_number,
        contact_id=str(record.contact_id),
        contact_type=record.contact_type,
        consent_type=record.consent_type,
        consent_channel=record.consent_channel,
        is_active=record.is_active,
        granted_at=record.granted_at,
        expires_at=record.expires_at,
        message="Consent recorded successfully.",
    )


@router.get(
    "/consent/{phone_number}",
    response_model=ConsentStatusResponse,
    summary="Check consent status for a phone number",
    description=(
        "Returns the most recent active consent record for the given phone "
        "number within the caller's organisation. Used for pre-dial compliance "
        "checks."
    ),
)
async def get_consent_status(
    phone_number: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Return active consent status for a phone number."""
    org_id = _get_org_id(current_user)
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    record = (
        db.query(TCPAConsent)
        .filter(
            TCPAConsent.organization_id == uuid.UUID(str(org_id)),
            TCPAConsent.phone_number == phone_number,
            TCPAConsent.is_active == True,  # noqa: E712
        )
        .order_by(TCPAConsent.granted_at.desc())
        .first()
    )

    if record is None:
        return ConsentStatusResponse(
            phone_number=phone_number,
            has_active_consent=False,
            consent_id=None,
            consent_type=None,
            consent_channel=None,
            granted_at=None,
            expires_at=None,
            call_permitted=False,
            sms_permitted=False,
            message="No active consent on file for this number.",
        )

    # Check expiration
    if record.expires_at and record.expires_at < now:
        return ConsentStatusResponse(
            phone_number=phone_number,
            has_active_consent=False,
            consent_id=str(record.id),
            consent_type=record.consent_type,
            consent_channel=record.consent_channel,
            granted_at=record.granted_at,
            expires_at=record.expires_at,
            call_permitted=False,
            sms_permitted=False,
            message="Consent on file has expired. A new consent grant is required.",
        )

    call_ok = _consent_channel_permits(record.consent_channel, "call")
    sms_ok = _consent_channel_permits(record.consent_channel, "sms")

    return ConsentStatusResponse(
        phone_number=phone_number,
        has_active_consent=True,
        consent_id=str(record.id),
        consent_type=record.consent_type,
        consent_channel=record.consent_channel,
        granted_at=record.granted_at,
        expires_at=record.expires_at,
        call_permitted=call_ok,
        sms_permitted=sms_ok,
        message="Active consent on file.",
    )


@router.post(
    "/consent/revoke",
    response_model=ConsentRevokeResponse,
    summary="Revoke TCPA consent",
    description=(
        "Marks active consent records for a phone number as revoked. "
        "Under FCC rules, revocation must be honoured within 10 business days. "
        "The revocation timestamp is captured immediately on this call; "
        "callers should also set revocation_processed_at to confirm the "
        "10-day deadline is being tracked."
    ),
)
async def revoke_consent(
    payload: ConsentRevokeRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Revoke active TCPA consent for a phone number."""
    org_id = _get_org_id(current_user)
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    query = db.query(TCPAConsent).filter(
        TCPAConsent.organization_id == uuid.UUID(str(org_id)),
        TCPAConsent.phone_number == payload.phone_number,
        TCPAConsent.is_active == True,  # noqa: E712
    )

    if payload.contact_id:
        try:
            contact_uuid = uuid.UUID(payload.contact_id)
            query = query.filter(TCPAConsent.contact_id == contact_uuid)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"contact_id is not a valid UUID: {payload.contact_id}",
            )

    records = query.all()

    if not records:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active consent records found for this phone number.",
        )

    try:
        for record in records:
            record.is_active = False
            record.revoked_at = now
            record.revocation_method = payload.revocation_method
            record.updated_at = now
        db.commit()
    except Exception as e:
        db.rollback()
        logger.exception(
            "Failed to revoke TCPA consent for phone %s", payload.phone_number
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save revocation.",
        ) from e

    logger.info(
        "TCPA consent revoked: phone=%s count=%d method=%s by_user=%s",
        payload.phone_number,
        len(records),
        payload.revocation_method,
        getattr(current_user, "id", "unknown"),
    )

    return ConsentRevokeResponse(
        revoked_count=len(records),
        phone_number=payload.phone_number,
        revocation_method=payload.revocation_method,
        revoked_at=now,
        message=(
            f"{len(records)} consent record(s) revoked. "
            "Ensure outbound contact stops within 10 business days per FCC rules."
        ),
    )


@router.get(
    "/consent/audit/{contact_id}",
    response_model=ConsentAuditResponse,
    summary="Full consent audit trail for a contact",
    description=(
        "Returns every consent record — active, revoked, and expired — for "
        "the given contact UUID.  Useful for regulatory audits and dispute "
        "resolution."
    ),
)
async def get_consent_audit(
    contact_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Return the full consent audit trail for a contact."""
    org_id = _get_org_id(current_user)

    try:
        contact_uuid = uuid.UUID(contact_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"contact_id is not a valid UUID: {contact_id}",
        )

    records = (
        db.query(TCPAConsent)
        .filter(
            TCPAConsent.organization_id == uuid.UUID(str(org_id)),
            TCPAConsent.contact_id == contact_uuid,
        )
        .order_by(TCPAConsent.granted_at.desc())
        .all()
    )

    active_count = sum(1 for r in records if r.is_active)
    revoked_count = sum(1 for r in records if r.revoked_at is not None)

    return ConsentAuditResponse(
        contact_id=contact_id,
        total_records=len(records),
        active_count=active_count,
        revoked_count=revoked_count,
        records=[
            ConsentAuditEntry(
                id=str(r.id),
                phone_number=r.phone_number,
                consent_type=r.consent_type,
                consent_channel=r.consent_channel,
                consent_source=r.consent_source,
                is_active=r.is_active,
                granted_at=r.granted_at,
                expires_at=r.expires_at,
                revoked_at=r.revoked_at,
                revocation_method=r.revocation_method,
                revocation_processed_at=r.revocation_processed_at,
                recording_url=r.recording_url,
                document_url=r.document_url,
                created_at=r.created_at,
            )
            for r in records
        ],
    )


@router.get(
    "/consent/expiring",
    response_model=ExpiringConsentsResponse,
    summary="List consents expiring within N days",
    description=(
        "Returns active consent records whose expires_at falls within the "
        "specified window.  Use this to proactively solicit consent renewals "
        "before your ability to contact the consumer lapses."
    ),
)
async def get_expiring_consents(
    days: int = Query(
        default=30,
        ge=1,
        le=365,
        description="Look-ahead window in days (1–365, default 30).",
    ),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Return consents expiring within the specified number of days."""
    org_id = _get_org_id(current_user)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    cutoff = now + timedelta(days=days)

    records = (
        db.query(TCPAConsent)
        .filter(
            TCPAConsent.organization_id == uuid.UUID(str(org_id)),
            TCPAConsent.is_active == True,  # noqa: E712
            TCPAConsent.expires_at.isnot(None),
            TCPAConsent.expires_at <= cutoff,
            TCPAConsent.expires_at > now,
        )
        .order_by(TCPAConsent.expires_at.asc())
        .all()
    )

    entries = []
    for r in records:
        days_until = (r.expires_at - now).days
        entries.append(
            ExpiringConsentEntry(
                id=str(r.id),
                phone_number=r.phone_number,
                contact_id=str(r.contact_id),
                contact_type=r.contact_type,
                consent_channel=r.consent_channel,
                granted_at=r.granted_at,
                expires_at=r.expires_at,
                days_until_expiry=max(days_until, 0),
            )
        )

    return ExpiringConsentsResponse(
        days_ahead=days,
        total=len(entries),
        consents=entries,
    )


@router.post(
    "/consent/verify-before-call",
    response_model=VerifyBeforeCallResponse,
    summary="Pre-call/pre-text consent verification gate",
    description=(
        "Call this endpoint immediately before placing an automated call or "
        "sending a marketing text.  Returns a boolean 'permitted' field along "
        "with a plain-English reason.  A response of permitted=False MUST "
        "block the outbound contact to comply with TCPA / FCC rules."
    ),
)
async def verify_before_call(
    payload: VerifyBeforeCallRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Pre-call/pre-text consent verification gate."""
    org_id = _get_org_id(current_user)
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    base_query = db.query(TCPAConsent).filter(
        TCPAConsent.organization_id == uuid.UUID(str(org_id)),
        TCPAConsent.phone_number == payload.phone_number,
        TCPAConsent.is_active == True,  # noqa: E712
    )

    if payload.contact_id:
        try:
            contact_uuid = uuid.UUID(payload.contact_id)
            base_query = base_query.filter(TCPAConsent.contact_id == contact_uuid)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"contact_id is not a valid UUID: {payload.contact_id}",
            )

    record = base_query.order_by(TCPAConsent.granted_at.desc()).first()

    # --- No consent on file ---
    if record is None:
        return VerifyBeforeCallResponse(
            permitted=False,
            phone_number=payload.phone_number,
            channel=payload.channel,
            consent_id=None,
            consent_type=None,
            granted_at=None,
            expires_at=None,
            reason=(
                "No active TCPA consent on file for this number. "
                "Obtain express written consent before contacting this consumer."
            ),
        )

    # --- Consent has expired ---
    if record.expires_at and record.expires_at < now:
        return VerifyBeforeCallResponse(
            permitted=False,
            phone_number=payload.phone_number,
            channel=payload.channel,
            consent_id=str(record.id),
            consent_type=record.consent_type,
            granted_at=record.granted_at,
            expires_at=record.expires_at,
            reason=(
                f"Consent expired on {record.expires_at.strftime('%Y-%m-%d')}. "
                "A renewed consent grant is required before proceeding."
            ),
        )

    # --- Consent channel does not cover the requested channel ---
    if not _consent_channel_permits(record.consent_channel, payload.channel):
        return VerifyBeforeCallResponse(
            permitted=False,
            phone_number=payload.phone_number,
            channel=payload.channel,
            consent_id=str(record.id),
            consent_type=record.consent_type,
            granted_at=record.granted_at,
            expires_at=record.expires_at,
            reason=(
                f"Consent on file covers '{record.consent_channel}' only. "
                f"A separate consent grant for '{payload.channel}' is required."
            ),
        )

    # --- All checks passed ---
    return VerifyBeforeCallResponse(
        permitted=True,
        phone_number=payload.phone_number,
        channel=payload.channel,
        consent_id=str(record.id),
        consent_type=record.consent_type,
        granted_at=record.granted_at,
        expires_at=record.expires_at,
        reason=(
            f"Active {record.consent_type} consent on file for '{record.consent_channel}' channel. "
            f"Granted on {record.granted_at.strftime('%Y-%m-%d')}. "
            "Contact is permitted."
        ),
    )
