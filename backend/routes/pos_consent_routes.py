"""
POS Consent Routes
==================
Endpoints for the voice-complete consent flow:

  CRM-authenticated (LO/system):
    POST /api/v1/pos/voice-complete                    — trigger consent SMS

  PURL-authenticated (borrower via magic link):
    GET  /api/v1/pos/consent/{token}/status            — consent completion status
    GET  /api/v1/pos/consent/{token}/disclosures       — consent language text
    POST /api/v1/pos/consent/{token}/credit-auth       — capture credit authorization
    POST /api/v1/pos/consent/{token}/e-disclosure      — capture e-disclosure consent
    POST /api/v1/pos/consent/{token}/submit            — submit (requires both consents)
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

router = APIRouter(tags=["POS Consent"])

logger = logging.getLogger("pos_consent.routes")


# Lazy imports to avoid circular dependency issues at module load time
def _get_db():
    from database import get_db
    return get_db


def _get_auth():
    from auth.dependencies import get_current_user
    return get_current_user


def _get_auth_or_api_key():
    from auth.dependencies import get_current_user_or_api_key
    return get_current_user_or_api_key


# =============================================================================
# REQUEST / RESPONSE SCHEMAS
# =============================================================================

class VoiceCompleteRequest(BaseModel):
    voice_loan_id: str = Field(..., description="URLA loan_id from the voice agent's Redis state")
    borrower_first_name: str
    borrower_phone: str
    lo_name: str
    organization_id: Optional[int] = None


class VoiceCompleteResponse(BaseModel):
    status: str
    application_id: int
    magic_link: Optional[str] = None
    sms_result: Optional[dict] = None
    message: Optional[str] = None


class ConsentCaptureRequest(BaseModel):
    typed_full_name: str = Field(..., min_length=2, max_length=255)
    consent_agreed: bool = Field(..., description="Must be true")


class ConsentResponse(BaseModel):
    status: str
    authorized_at: Optional[str] = None
    consented_at: Optional[str] = None
    uuid: Optional[str] = None


class ConsentStatusResponse(BaseModel):
    credit_auth: dict
    e_consent: dict
    all_complete: bool
    application_status: str
    form_data: Optional[dict] = None
    lo_name: Optional[str] = None


# =============================================================================
# CRM-AUTHENTICATED ENDPOINTS
# =============================================================================

@router.post(
    "/api/v1/pos/voice-complete",
    response_model=VoiceCompleteResponse,
)
async def trigger_voice_complete(
    body: VoiceCompleteRequest,
    request: Request,
    db: Session = Depends(_get_db()),
    current_user=Depends(_get_auth_or_api_key()),
):
    """
    Trigger the POS consent flow after voice agent completes a URLA.

    Finds or creates a BorrowerApplication from the voice_loan_id,
    transitions to PENDING_CONSENT, generates a PURL magic link,
    and sends the borrower an SMS.

    Auth: CRM JWT (LO or system service account) **or** CRM_API_KEY /
    INTERNAL_API_KEY for service-to-service calls from the URLA voice agent.
    """
    from services.pos_consent_service import voice_complete

    try:
        result = voice_complete(
            db=db,
            voice_loan_id=body.voice_loan_id,
            borrower_first_name=body.borrower_first_name,
            borrower_phone=body.borrower_phone,
            lo_name=body.lo_name,
            organization_id=body.organization_id or getattr(current_user, "organization_id", None),
            owner_id=getattr(current_user, "id", None),
        )
        return VoiceCompleteResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# =============================================================================
# PURL-AUTHENTICATED ENDPOINTS (borrower via magic link)
# =============================================================================

def _resolve_application_from_token(token: str, db: Session):
    """
    Resolve a PURL token to its associated BorrowerApplication.
    Validates token is active, not expired, and has VOICE_REVIEW_SUBMIT scope.

    The workspace slug encodes the application_id (voice-consent-app-{id}).
    """
    from models.purl import TokenScope
    from services.purl_token_service import PURLTokenService

    token_service = PURLTokenService(db)
    token_record = token_service.verify_token(token)
    if not token_record:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    scope = token_record.get("scope")
    if scope != TokenScope.VOICE_REVIEW_SUBMIT:
        raise HTTPException(status_code=403, detail="Token does not have consent access")

    from database.models.borrower import BorrowerApplication

    # Extract application_id from workspace slug (voice-consent-app-{id})
    workspace_slug = token_record.get("workspace_slug", "")
    application_id = None
    if workspace_slug.startswith("voice-consent-app-"):
        try:
            application_id = int(workspace_slug.split("-")[-1])
        except (ValueError, IndexError):
            pass

    if application_id:
        app = db.query(BorrowerApplication).filter(
            BorrowerApplication.id == application_id,
        ).first()
    else:
        raise HTTPException(status_code=404, detail="Token is not linked to an application")

    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    return app, token_record


@router.get("/api/v1/pos/consent/{token}/status", response_model=ConsentStatusResponse)
async def get_consent_status(
    token: str,
    db: Session = Depends(_get_db()),
):
    """Get the current consent completion status for the borrower."""
    from services.pos_consent_service import check_consents_complete

    app, _ = _resolve_application_from_token(token, db)
    consents = check_consents_complete(db, app.id)

    form_data = None
    if hasattr(app, 'step_data') and app.step_data:
        form_data = app.step_data
    elif hasattr(app, 'form_data') and app.form_data:
        form_data = app.form_data

    lo_name = None
    if hasattr(app, 'lo_name'):
        lo_name = app.lo_name
    elif hasattr(app, 'assigned_lo_name'):
        lo_name = app.assigned_lo_name

    return ConsentStatusResponse(
        credit_auth=consents["credit_auth"],
        e_consent=consents["e_consent"],
        all_complete=consents["all_complete"],
        application_status=app.status.value if hasattr(app.status, 'value') else str(app.status),
        form_data=form_data,
        lo_name=lo_name,
    )


@router.get("/api/v1/pos/consent/{token}/disclosures")
async def get_disclosures(
    token: str,
    db: Session = Depends(_get_db()),
):
    """Return the current consent language for the frontend to display."""
    from services.pos_consent_service import get_disclosure_texts

    _resolve_application_from_token(token, db)
    return get_disclosure_texts()


@router.post("/api/v1/pos/consent/{token}/credit-auth", response_model=ConsentResponse)
async def capture_credit_authorization(
    token: str,
    body: ConsentCaptureRequest,
    request: Request,
    db: Session = Depends(_get_db()),
):
    """
    Capture the borrower's FCRA credit authorization.

    The borrower types their full legal name and clicks "I Authorize."
    Records IP, user agent, consent text version, and content hash.
    """
    from services.pos_consent_service import record_credit_authorization

    if not body.consent_agreed:
        raise HTTPException(status_code=400, detail="Consent must be agreed to proceed")

    app, _ = _resolve_application_from_token(token, db)

    ip_address = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")

    try:
        result = record_credit_authorization(
            db=db,
            application_id=app.id,
            typed_full_name=body.typed_full_name,
            ip_address=ip_address,
            user_agent=user_agent,
            organization_id=app.organization_id,
        )
        return ConsentResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/api/v1/pos/consent/{token}/e-disclosure", response_model=ConsentResponse)
async def capture_econsent(
    token: str,
    body: ConsentCaptureRequest,
    request: Request,
    db: Session = Depends(_get_db()),
):
    """
    Capture the borrower's E-SIGN Act electronic disclosure consent.
    """
    from services.pos_consent_service import record_econsent_agreement

    if not body.consent_agreed:
        raise HTTPException(status_code=400, detail="Consent must be agreed to proceed")

    app, _ = _resolve_application_from_token(token, db)

    ip_address = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")

    try:
        result = record_econsent_agreement(
            db=db,
            application_id=app.id,
            typed_full_name=body.typed_full_name,
            ip_address=ip_address,
            user_agent=user_agent,
            organization_id=app.organization_id,
        )
        return ConsentResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/api/v1/pos/consent/{token}/submit")
async def submit_with_consent(
    token: str,
    request: Request,
    db: Session = Depends(_get_db()),
):
    """
    Submit the application after both consents are captured.

    Validates that credit auth and e-consent are recorded before
    transitioning to SUBMITTED. Idempotent — second call returns success.
    """
    from services.pos_consent_service import check_consents_complete
    from database.enums import ApplicationStatus

    app, _ = _resolve_application_from_token(token, db)

    # Idempotent: already submitted
    if app.status in (
        ApplicationStatus.SUBMITTED,
        ApplicationStatus.UNDER_REVIEW,
        ApplicationStatus.APPROVED,
    ):
        return {
            "status": "already_submitted",
            "submitted_at": app.submitted_at.isoformat() if app.submitted_at else None,
        }

    if app.status != ApplicationStatus.PENDING_CONSENT:
        raise HTTPException(
            status_code=400,
            detail=f"Application is in status {app.status.value}, expected PENDING_CONSENT",
        )

    # Require both consents
    consents = check_consents_complete(db, app.id)
    if not consents["all_complete"]:
        missing = []
        if not consents["credit_auth"]["completed"]:
            missing.append("credit authorization")
        if not consents["e_consent"]["completed"]:
            missing.append("e-disclosure consent")
        raise HTTPException(
            status_code=400,
            detail=f"Missing required consents: {', '.join(missing)}",
        )

    # Transition to SUBMITTED
    app.status = ApplicationStatus.SUBMITTED
    app.submitted_at = datetime.now(timezone.utc)
    app.progress_percentage = 100

    # Write audit event
    from services.pos_consent_service import _write_application_event
    ip_address = request.client.host if request.client else "unknown"
    _write_application_event(db, app.id, "submitted_via_voice_consent", {
        "ip_address": ip_address,
        "credit_auth_complete": True,
        "econsent_complete": True,
    })

    db.commit()

    logger.info("Application %d submitted via voice consent flow", app.id)

    return {
        "status": "submitted",
        "submitted_at": app.submitted_at.isoformat(),
        "application_id": app.id,
    }
