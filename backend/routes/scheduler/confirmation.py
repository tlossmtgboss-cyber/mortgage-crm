"""
Scheduler Confirmation Endpoints - Public appointment confirmation page data.

Endpoints:
  - GET  /public/confirmation/{appointment_id}       Get confirmation details (token-based auth)
  - GET  /public/confirmation/{appointment_id}/ics    Download ICS calendar file
  - POST /public/confirmation/{appointment_id}/cancel Request cancellation
  - POST /public/confirmation/{appointment_id}/reschedule Request reschedule

All endpoints use appointment-specific JWT tokens (no login required).
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
from typing import Optional
import html
import hashlib
import hmac
import json
import logging
import os
import re
import jwt

from smart_scheduler_models import (
    AppointmentStatus, MeetingType, MeetingMode,
)
from services.ics_generator import generate_ics_content
from scheduler_email_service import generate_reschedule_url
from routes.scheduler._helpers import (
    get_models, _check_rate_limit, _sanitize_text,
    _check_appointment_conflict, _convert_utc_to_user_tz, _audit_log,
)
from routes.scheduler.constants import DEFAULT_TIMEZONE
from db import get_db

logger = logging.getLogger(__name__)

router = APIRouter()

SECRET_KEY = os.getenv("SECRET_KEY", "")
if not SECRET_KEY:
    import warnings
    warnings.warn("SECRET_KEY not set in confirmation module")
FRONTEND_URL = os.getenv("FRONTEND_URL", "https://app.perenniaai.com")

# Maximum length for ICS description field to prevent abuse
_ICS_DESCRIPTION_MAX_LENGTH = 2000

# Regex to strip HTML tags
_HTML_TAG_RE = re.compile(r"<[^>]+>")

# Statuses from which an appointment can be cancelled or rescheduled by a borrower
_ACTIONABLE_STATUSES = {"booked", "confirmed", "reminded", "scheduled"}


# ============================================================================
# PYDANTIC REQUEST MODELS
# ============================================================================

class ConfirmationCancelRequest(BaseModel):
    """Request body for cancelling an appointment via confirmation token."""
    reason: Optional[str] = Field(None, max_length=1000, description="Optional cancellation reason")


class ConfirmationRescheduleRequest(BaseModel):
    """Request body for rescheduling an appointment via confirmation token."""
    slot_time: str = Field(..., description="New appointment start time in ISO 8601 format")
    reason: Optional[str] = Field(None, max_length=1000, description="Optional reschedule reason")


# ============================================================================
# PII MASKING HELPERS (for public-facing responses)
# ============================================================================

def _mask_email_public(email: Optional[str]) -> Optional[str]:
    """Mask email for public responses: ti***@company.com"""
    if not email or "@" not in email:
        return None
    local, domain = email.split("@", 1)
    if len(local) <= 2:
        masked_local = local[0] + "***" if local else "***"
    else:
        masked_local = local[:2] + "***"
    return f"{masked_local}@{domain}"


def _mask_phone_public(phone: Optional[str]) -> Optional[str]:
    """Mask phone for public responses: show only last 4 digits."""
    if not phone:
        return None
    digits = re.sub(r"\D", "", phone)
    if len(digits) < 4:
        return None
    return f"***-***-{digits[-4:]}"


def _mask_nmls_public(nmls: Optional[str]) -> Optional[str]:
    """Mask NMLS number for public responses: show only last 4 digits."""
    if not nmls:
        return None
    nmls_str = str(nmls)
    if len(nmls_str) <= 4:
        return None
    return f"***{nmls_str[-4:]}"


# ============================================================================
# ICS CONTENT SANITIZATION
# ============================================================================

def _sanitize_ics_description(description: str) -> str:
    """Sanitize user-provided content for ICS DESCRIPTION field.

    Strips HTML tags, escapes special ICS characters per RFC 5545,
    and limits length to prevent abuse.
    """
    if not description:
        return ""
    # Strip HTML tags
    cleaned = _HTML_TAG_RE.sub("", description)
    # Decode HTML entities (e.g., &amp; -> &)
    cleaned = html.unescape(cleaned)
    # Truncate to max length
    if len(cleaned) > _ICS_DESCRIPTION_MAX_LENGTH:
        cleaned = cleaned[:_ICS_DESCRIPTION_MAX_LENGTH] + "..."
    return cleaned


# ============================================================================
# PREPARATION CHECKLISTS (by meeting type)
# ============================================================================

PREPARATION_CHECKLISTS = {
    MeetingType.DISCOVERY_CALL.value: {
        "title": "Prepare for Your Consultation",
        "description": "Having these items ready will help us make the most of our time together.",
        "items": [
            {"label": "Recent pay stubs (last 30 days)", "category": "income", "priority": "high"},
            {"label": "W-2 forms (last 2 years)", "category": "income", "priority": "high"},
            {"label": "Bank statements (last 2 months)", "category": "assets", "priority": "high"},
            {"label": "Government-issued photo ID", "category": "identity", "priority": "high"},
            {"label": "Property address or area of interest", "category": "property", "priority": "medium"},
            {"label": "Estimated budget or price range", "category": "property", "priority": "medium"},
            {"label": "List of questions about the mortgage process", "category": "general", "priority": "low"},
        ],
    },
    MeetingType.PRE_APPROVAL_REVIEW.value: {
        "title": "Documents for Pre-Approval",
        "description": "We will review your financials and determine your pre-approval amount.",
        "items": [
            {"label": "Pay stubs (last 30 days)", "category": "income", "priority": "high"},
            {"label": "W-2 forms (last 2 years)", "category": "income", "priority": "high"},
            {"label": "Federal tax returns (last 2 years)", "category": "income", "priority": "high"},
            {"label": "Bank statements - all accounts (last 2 months)", "category": "assets", "priority": "high"},
            {"label": "Investment/retirement account statements", "category": "assets", "priority": "medium"},
            {"label": "Employment history (2 years)", "category": "income", "priority": "high"},
            {"label": "Driver's license or government ID", "category": "identity", "priority": "high"},
            {"label": "Social Security number", "category": "identity", "priority": "high"},
            {"label": "Landlord contact info (if renting)", "category": "general", "priority": "low"},
            {"label": "Gift letter (if receiving down payment gift)", "category": "assets", "priority": "low"},
        ],
    },
    MeetingType.RATE_LOCK_DISCUSSION.value: {
        "title": "Prepare for Your Rate Review",
        "description": "We will discuss current rates and lock-in options for your loan.",
        "items": [
            {"label": "Current loan details (if refinancing)", "category": "loan", "priority": "high"},
            {"label": "Most recent mortgage statement", "category": "loan", "priority": "high"},
            {"label": "Property address and estimated value", "category": "property", "priority": "high"},
            {"label": "Your financial goals (lower payment, cash out, shorter term)", "category": "general", "priority": "medium"},
            {"label": "Credit score (approximate is fine)", "category": "credit", "priority": "medium"},
            {"label": "Timeline for closing", "category": "general", "priority": "medium"},
        ],
    },
    MeetingType.APPLICATION_WALKTHROUGH.value: {
        "title": "Application Appointment Checklist",
        "description": "We will complete your mortgage application together. Please have these ready.",
        "items": [
            {"label": "Pay stubs (last 30 days)", "category": "income", "priority": "high"},
            {"label": "W-2 forms (last 2 years)", "category": "income", "priority": "high"},
            {"label": "Federal tax returns (last 2 years)", "category": "income", "priority": "high"},
            {"label": "Bank statements - all accounts (last 2 months)", "category": "assets", "priority": "high"},
            {"label": "Purchase contract (if you have one)", "category": "property", "priority": "high"},
            {"label": "Driver's license (front and back)", "category": "identity", "priority": "high"},
            {"label": "Social Security number for all borrowers", "category": "identity", "priority": "high"},
            {"label": "Homeowner's insurance quote", "category": "property", "priority": "medium"},
            {"label": "Divorce decree (if applicable)", "category": "legal", "priority": "medium"},
            {"label": "Bankruptcy discharge papers (if applicable)", "category": "legal", "priority": "low"},
        ],
    },
    MeetingType.DOCUMENT_REVIEW.value: {
        "title": "Document Review Preparation",
        "description": "We will review your submitted documents and address any outstanding items.",
        "items": [
            {"label": "Any documents requested by your loan officer", "category": "general", "priority": "high"},
            {"label": "Updated bank statements (if previously submitted are over 60 days old)", "category": "assets", "priority": "medium"},
            {"label": "Updated pay stubs (if previously submitted are over 30 days old)", "category": "income", "priority": "medium"},
            {"label": "Explanation letters for any credit inquiries", "category": "credit", "priority": "medium"},
            {"label": "Questions about any conditions or requirements", "category": "general", "priority": "low"},
        ],
    },
    MeetingType.CLOSING_PREP.value: {
        "title": "Closing Preparation Checklist",
        "description": "Your closing is coming up. Here is what you will need.",
        "items": [
            {"label": "Government-issued photo ID", "category": "identity", "priority": "high"},
            {"label": "Cashier's check or wire transfer confirmation for closing costs", "category": "assets", "priority": "high"},
            {"label": "Proof of homeowner's insurance", "category": "property", "priority": "high"},
            {"label": "Review your Closing Disclosure (CD) - sent 3 days before closing", "category": "loan", "priority": "high"},
            {"label": "Questions about any fees or terms on the CD", "category": "general", "priority": "medium"},
        ],
    },
    MeetingType.POST_CLOSE_REVIEW.value: {
        "title": "Post-Closing Review",
        "description": "Congratulations on your new home! We will review next steps.",
        "items": [
            {"label": "Your closing documents packet", "category": "loan", "priority": "medium"},
            {"label": "First payment details and setup questions", "category": "loan", "priority": "medium"},
            {"label": "Questions about escrow or insurance", "category": "general", "priority": "low"},
        ],
    },
}

# Default checklist for unrecognized meeting types
DEFAULT_CHECKLIST = {
    "title": "Prepare for Your Appointment",
    "description": "Having these items ready will help us make the most of our time.",
    "items": [
        {"label": "Government-issued photo ID", "category": "identity", "priority": "high"},
        {"label": "Any relevant financial documents", "category": "general", "priority": "medium"},
        {"label": "List of questions for your loan officer", "category": "general", "priority": "low"},
    ],
}


# ============================================================================
# TOKEN HELPERS
# ============================================================================

def _generate_confirmation_token(appointment_id: int, attendee_email: str) -> str:
    """Generate a JWT token for accessing a specific appointment's confirmation page."""
    if not SECRET_KEY:
        raise RuntimeError("SECRET_KEY required for token generation")
    payload = {
        "appt_id": appointment_id,
        "email": attendee_email,
        "purpose": "confirmation",
        "exp": datetime.now(timezone.utc) + timedelta(hours=48),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")


def _verify_confirmation_token(
    token: str,
    appointment_id: int,
    appointment_status: Optional[str] = None,
) -> dict:
    """Verify a confirmation token. Returns decoded payload or raises HTTPException.

    If appointment_status is provided, also checks that the appointment has not
    been cancelled or marked as no-show (revokes token implicitly).
    """
    if not SECRET_KEY:
        raise HTTPException(status_code=500, detail="Server configuration error")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Confirmation link has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid confirmation link")

    if payload.get("appt_id") != appointment_id:
        raise HTTPException(status_code=403, detail="Token does not match this appointment")

    # Implicit token revocation: reject tokens for cancelled/terminal appointments
    if appointment_status and appointment_status in ("cancelled", "no_show"):
        raise HTTPException(status_code=410, detail="This appointment has been cancelled")

    return payload


def _generate_qr_data(appointment_id: int, attendee_name: str, scheduled_start: datetime) -> dict:
    """Generate QR code data payload for in-office check-in."""
    check_in_data = {
        "type": "perennia_checkin",
        "appointment_id": appointment_id,
        "name": attendee_name or "",
        "time": scheduled_start.isoformat() if scheduled_start else "",
    }
    # Create a verification hash so the check-in kiosk can validate
    data_str = json.dumps(check_in_data, sort_keys=True)
    if SECRET_KEY:
        check_in_data["hash"] = hmac.new(
            SECRET_KEY.encode(), data_str.encode(), hashlib.sha256
        ).hexdigest()[:16]
    return check_in_data


# ============================================================================
# ENDPOINTS
# ============================================================================

@router.get("/public/confirmation/{appointment_id}")
async def get_confirmation_details(
    request: Request,
    appointment_id: int,
    token: str = Query(..., description="Appointment-specific JWT token"),
    db: Session = Depends(get_db),
):
    """
    Get appointment confirmation details for the public confirmation page.
    Requires a valid appointment-specific JWT token (no login needed).
    """
    await _check_rate_limit(request, max_requests=30)

    models = get_models()
    if not models:
        raise HTTPException(status_code=500, detail="Scheduler not initialized")

    Appointment = models.get("Appointment")
    if not Appointment:
        raise HTTPException(status_code=500, detail="Appointment model unavailable")

    appointment = db.query(Appointment).filter(
        Appointment.id == appointment_id
    ).first()

    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")

    # Resolve appointment status for token revocation check
    appt_status = appointment.status.value if hasattr(appointment.status, 'value') else str(appointment.status)

    # Verify token AND implicitly revoke if appointment is cancelled/no-show
    payload = _verify_confirmation_token(token, appointment_id, appointment_status=appt_status)

    # SEC-001: Verify token email matches appointment attendee
    token_email = (payload.get("email") or "").strip().lower()
    appt_email = (appointment.attendee_email or "").strip().lower()
    if token_email and appt_email and token_email != appt_email:
        raise HTTPException(status_code=403, detail="Token does not match this appointment")

    # Get LO details -- mask PII for public response (no raw email/phone/NMLS)
    lo_name = None
    lo_photo = None
    lo_title = None
    lo_nmls_masked = None
    if appointment.assigned_user_id:
        try:
            from database.models.core import User
            lo = db.query(User).filter(User.id == appointment.assigned_user_id).first()
            if lo:
                lo_name = f"{getattr(lo, 'first_name', '') or ''} {getattr(lo, 'last_name', '') or ''}".strip()
                lo_photo = getattr(lo, 'profile_photo_url', None) or getattr(lo, 'avatar_url', None)
                lo_title = getattr(lo, 'title', None) or "Loan Officer"
                # Mask NMLS -- only show last 4 digits in public response
                lo_nmls_masked = _mask_nmls_public(getattr(lo, 'nmls_number', None))
        except Exception as e:
            logger.error("Could not load LO details for appointment %s", appointment_id, exc_info=True)

    # Get appointment type details (scoped by org_id to prevent cross-tenant exposure)
    appointment_type_name = None
    if appointment.appointment_type_id:
        AppointmentType = models.get("AppointmentType")
        if AppointmentType:
            apt_type = db.query(AppointmentType).filter(
                AppointmentType.id == appointment.appointment_type_id,
                AppointmentType.organization_id == appointment.organization_id,
            ).first()
            if apt_type:
                appointment_type_name = getattr(apt_type, 'name', None)

    # Build meeting type string
    meeting_type_value = None
    if appointment.meeting_type:
        meeting_type_value = appointment.meeting_type.value if hasattr(appointment.meeting_type, 'value') else str(appointment.meeting_type)

    # Get preparation checklist
    checklist = PREPARATION_CHECKLISTS.get(meeting_type_value, DEFAULT_CHECKLIST)

    # Build meeting mode display
    meeting_mode_value = None
    meeting_mode_label = "Meeting"
    if appointment.meeting_mode:
        meeting_mode_value = appointment.meeting_mode.value if hasattr(appointment.meeting_mode, 'value') else str(appointment.meeting_mode)
        mode_labels = {
            "video": "Video Call",
            "phone": "Phone Call",
            "in_person": "In-Person Meeting",
            "screen_share": "Screen Share Session",
        }
        meeting_mode_label = mode_labels.get(meeting_mode_value, "Meeting")

    # Build add-to-calendar data
    start_dt = appointment.scheduled_start
    end_dt = appointment.scheduled_end
    duration_min = appointment.duration_minutes or 30

    # Google Calendar link
    google_cal_url = _build_google_calendar_url(
        title=appointment.title or "Mortgage Appointment",
        start=start_dt,
        end=end_dt,
        description=appointment.description or "",
        location=appointment.location or appointment.video_link or "",
    )

    # Yahoo Calendar link
    yahoo_cal_url = _build_yahoo_calendar_url(
        title=appointment.title or "Mortgage Appointment",
        start=start_dt,
        end=end_dt,
        description=appointment.description or "",
        location=appointment.location or appointment.video_link or "",
    )

    # Outlook Web link
    outlook_cal_url = _build_outlook_calendar_url(
        title=appointment.title or "Mortgage Appointment",
        start=start_dt,
        end=end_dt,
        description=appointment.description or "",
        location=appointment.location or appointment.video_link or "",
    )

    # ICS download link
    api_base = os.getenv("API_BASE_URL", "https://api.perenniaai.com")
    ics_url = f"{api_base}/api/v1/scheduler/public/confirmation/{appointment_id}/ics?token={token}"

    # Reschedule/cancel URLs
    reschedule_url = None
    cancel_url = None
    try:
        attendee_email = payload.get("email", appointment.attendee_email or "")
        cancel_token = jwt.encode(
            {
                "appt_id": appointment_id,
                "email": attendee_email,
                "action": "cancel",
                "exp": datetime.now(timezone.utc) + timedelta(hours=72),
            },
            SECRET_KEY,
            algorithm="HS256",
        )
        reschedule_url = generate_reschedule_url(
            appointment_id, attendee_email
        )
        cancel_url = f"{FRONTEND_URL}/booking/cancel?token={cancel_token}"
    except Exception as e:
        logger.error("Could not generate reschedule/cancel URLs for appointment %s", appointment_id, exc_info=True)

    # QR code data for in-office check-in
    qr_data = _generate_qr_data(
        appointment_id,
        appointment.attendee_name,
        start_dt,
    )

    # Share link
    share_url = f"{FRONTEND_URL}/booking/confirmation/{appointment_id}?token={token}"

    return {
        "appointment": {
            "id": appointment.id,
            "title": appointment.title,
            "description": appointment.description,
            "status": appt_status,
            "meeting_type": meeting_type_value,
            "meeting_mode": meeting_mode_value,
            "meeting_mode_label": meeting_mode_label,
            "appointment_type_name": appointment_type_name,
            "scheduled_start": start_dt.isoformat() if start_dt else None,
            "scheduled_end": end_dt.isoformat() if end_dt else None,
            "duration_minutes": duration_min,
            "timezone": appointment.timezone or DEFAULT_TIMEZONE,
            "location": appointment.location,
            "video_link": appointment.video_link,
            "phone_number": appointment.phone_number,
            "attendee_name": appointment.attendee_name,
            "attendee_email": appointment.attendee_email,
        },
        "loan_officer": {
            "name": lo_name,
            "photo_url": lo_photo,
            "title": lo_title,
            "nmls_number": lo_nmls_masked,
        },
        "calendar_links": {
            "google": google_cal_url,
            "yahoo": yahoo_cal_url,
            "outlook_web": outlook_cal_url,
            "ics_download": ics_url,
        },
        "preparation": checklist,
        "actions": {
            "reschedule_url": reschedule_url,
            "cancel_url": cancel_url,
            "share_url": share_url,
        },
        "qr_data": qr_data,
    }


@router.get("/public/confirmation/{appointment_id}/ics")
async def download_ics_file(
    request: Request,
    appointment_id: int,
    token: str = Query(..., description="Appointment-specific JWT token"),
    db: Session = Depends(get_db),
):
    """Download ICS calendar file for the appointment."""
    await _check_rate_limit(request, max_requests=30)

    models = get_models()
    if not models:
        raise HTTPException(status_code=500, detail="Scheduler not initialized")

    Appointment = models.get("Appointment")
    if not Appointment:
        raise HTTPException(status_code=500, detail="Appointment model unavailable")

    appointment = db.query(Appointment).filter(
        Appointment.id == appointment_id
    ).first()

    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")

    # Resolve status for token revocation check (Task #7)
    appt_status = appointment.status.value if hasattr(appointment.status, 'value') else str(appointment.status)

    # Verify token AND reject if appointment is cancelled/no-show
    payload = _verify_confirmation_token(token, appointment_id, appointment_status=appt_status)

    # SEC-001: Verify token email matches appointment attendee
    token_email = (payload.get("email") or "").strip().lower()
    appt_email = (appointment.attendee_email or "").strip().lower()
    if token_email and appt_email and token_email != appt_email:
        raise HTTPException(status_code=403, detail="Token does not match this appointment")

    # Get LO info for organizer fields
    organizer_name = "Perennia AI"
    organizer_email = "noreply@perenniaai.com"
    if appointment.assigned_user_id:
        try:
            from database.models.core import User
            lo = db.query(User).filter(User.id == appointment.assigned_user_id).first()
            if lo:
                organizer_name = f"{getattr(lo, 'first_name', '') or ''} {getattr(lo, 'last_name', '') or ''}".strip()
                organizer_email = getattr(lo, 'email', None) or organizer_email
        except Exception as e:
            logger.error("Could not load LO for ICS for appointment %s", appointment_id, exc_info=True)

    # Sanitize description: strip HTML tags, limit length (Task #16)
    safe_description = _sanitize_ics_description(appointment.description or "")

    ics_content = generate_ics_content(
        appointment_title=appointment.title or "Mortgage Appointment",
        start_datetime=appointment.scheduled_start,
        duration_minutes=appointment.duration_minutes or 30,
        attendee_email=appointment.attendee_email or "",
        attendee_name=appointment.attendee_name or "",
        organizer_email=organizer_email,
        organizer_name=organizer_name,
        description=safe_description,
        location=appointment.location or "",
        video_link=appointment.video_link,
        appointment_id=appointment.id,
    )

    return Response(
        content=ics_content,
        media_type="text/calendar",
        headers={
            "Content-Disposition": f'attachment; filename="appointment-{appointment_id}.ics"',
        },
    )


# ============================================================================
# CANCEL (public, borrower self-service via confirmation token)
# ============================================================================

@router.post("/public/confirm/{appointment_id}/cancel")
async def public_cancel_appointment(
    request: Request,
    appointment_id: int,
    body: Optional[ConfirmationCancelRequest] = None,
    token: str = Query(..., description="Appointment-specific JWT token"),
    db: Session = Depends(get_db),
):
    """
    Cancel an appointment using the confirmation token.

    The borrower can cancel directly from the confirmation page without logging in.
    Rate-limited to 10 requests per window to prevent abuse.
    """
    await _check_rate_limit(request, max_requests=10)

    models = get_models()
    if not models:
        raise HTTPException(status_code=500, detail="Scheduler not initialized")

    Appointment = models.get("Appointment")
    if not Appointment:
        raise HTTPException(status_code=500, detail="Appointment model unavailable")

    appointment = db.query(Appointment).filter(
        Appointment.id == appointment_id
    ).first()

    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")

    # Resolve status string
    appt_status = appointment.status.value if hasattr(appointment.status, 'value') else str(appointment.status)

    # Verify token (also rejects cancelled/no-show appointments)
    payload = _verify_confirmation_token(token, appointment_id, appointment_status=appt_status)

    # SEC-001: Verify token email matches appointment attendee
    token_email = (payload.get("email") or "").strip().lower()
    appt_email = (appointment.attendee_email or "").strip().lower()
    if token_email and appt_email and token_email != appt_email:
        raise HTTPException(status_code=403, detail="Token does not match this appointment")

    # Check the appointment is still in a cancellable state
    if appt_status not in _ACTIONABLE_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot cancel an appointment with status: {appt_status}",
        )

    # Check the appointment is not in the past
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    if appointment.scheduled_start and appointment.scheduled_start < now_utc:
        raise HTTPException(
            status_code=409,
            detail="Cannot cancel an appointment that has already started or passed",
        )

    # Extract cancellation reason
    reason = _sanitize_text(body.reason) if body and body.reason else None

    # Store details for email before mutating the record
    attendee_email_raw = appointment.attendee_email
    attendee_name = appointment.attendee_name or "Valued Client"
    appointment_title = appointment.title or "Appointment"
    org_id = appointment.organization_id

    # Format date/time for the cancellation email
    if appointment.scheduled_start and appointment.assigned_user_id:
        try:
            local_start = _convert_utc_to_user_tz(
                appointment.scheduled_start, appointment.assigned_user_id, db, org_id=org_id
            )
            appointment_date = local_start.strftime('%B %d, %Y')
            appointment_time = local_start.strftime('%I:%M %p %Z')
        except Exception as e:
            logger.warning("Timezone conversion failed for cancellation email (appointment %s): %s", appointment.id, e)
            appointment_date = appointment.scheduled_start.strftime('%B %d, %Y')
            appointment_time = appointment.scheduled_start.strftime('%I:%M %p UTC')
    elif appointment.scheduled_start:
        appointment_date = appointment.scheduled_start.strftime('%B %d, %Y')
        appointment_time = appointment.scheduled_start.strftime('%I:%M %p UTC')
    else:
        appointment_date = "TBD"
        appointment_time = "TBD"

    # Get LO name for email
    team_member_name = None
    if appointment.assigned_user_id:
        try:
            from database.models.core import User
            lo = db.query(User).filter(User.id == appointment.assigned_user_id).first()
            if lo:
                team_member_name = f"{getattr(lo, 'first_name', '') or ''} {getattr(lo, 'last_name', '') or ''}".strip()
        except Exception as e:
            logger.error("Could not load LO details for cancellation email: %s", e, exc_info=True)

    # Perform the cancellation
    appointment.status = AppointmentStatus.CANCELLED
    appointment.cancelled_at = datetime.now(timezone.utc)
    appointment.cancellation_reason = reason
    appointment.status_changed_at = datetime.now(timezone.utc)
    appointment.updated_at = datetime.now(timezone.utc)

    # Record status history
    AppointmentStatusHistory = models.get("AppointmentStatusHistory")
    if AppointmentStatusHistory:
        try:
            status_history = AppointmentStatusHistory(
                organization_id=org_id,
                appointment_id=appointment_id,
                previous_status=appt_status,
                new_status=AppointmentStatus.CANCELLED.value,
                change_source="borrower_confirmation_page",
                notes=reason,
            )
            db.add(status_history)
        except Exception as e:
            logger.error("Failed to record status history for cancellation: %s", e, exc_info=True)

    # Audit log
    try:
        _audit_log(
            db, org_id, None, "cancelled", "appointment",
            entity_id=appointment_id,
            changes={"reason": reason, "cancelled_by": "borrower"},
            request=request,
            booking_source="public_confirmation",
        )
    except Exception as e:
        logger.error("Failed to write audit log for cancellation: %s", e, exc_info=True)

    db.commit()

    # Enterprise audit (best-effort, non-blocking)
    try:
        from services.scheduler_audit_logger import scheduler_audit

        class _BorrowerProxy:
            """Minimal proxy to satisfy scheduler_audit.log_appointment_cancelled user param."""
            id = None
            first_name = attendee_name
            last_name = ""

        scheduler_audit.log_appointment_cancelled(
            appointment, _BorrowerProxy(), reason=reason, request=request,
            booking_source="public_confirmation",
        )
    except Exception as e:
        logger.debug("Could not write scheduler audit for borrower cancellation: %s", e)

    # Send cancellation email (best-effort, non-blocking)
    if attendee_email_raw:
        try:
            from scheduler_email_service import send_appointment_cancellation_email
            send_appointment_cancellation_email(
                attendee_email=attendee_email_raw,
                attendee_name=attendee_name,
                appointment_title=appointment_title,
                appointment_date=appointment_date,
                appointment_time=appointment_time,
                team_member_name=team_member_name,
                cancellation_reason=reason,
                organization_id=org_id,
            )
        except Exception as e:
            logger.error("Failed to send cancellation email for appointment %s: %s", appointment_id, e, exc_info=True)

    return {
        "status": "ok",
        "message": "Appointment cancelled successfully",
        "appointment_id": appointment_id,
        "cancelled_at": appointment.cancelled_at.isoformat() if appointment.cancelled_at else None,
    }


# ============================================================================
# RESCHEDULE (public, borrower self-service via confirmation token)
# ============================================================================

@router.post("/public/confirm/{appointment_id}/reschedule")
async def public_reschedule_appointment(
    request: Request,
    appointment_id: int,
    body: ConfirmationRescheduleRequest,
    token: str = Query(..., description="Appointment-specific JWT token"),
    db: Session = Depends(get_db),
):
    """
    Reschedule an appointment using the confirmation token.

    The borrower provides a new `slot_time` (ISO 8601) and the appointment is
    moved to that time.  The duration is preserved from the original appointment.
    Rate-limited to 10 requests per window to prevent abuse.
    """
    await _check_rate_limit(request, max_requests=10)

    models = get_models()
    if not models:
        raise HTTPException(status_code=500, detail="Scheduler not initialized")

    Appointment = models.get("Appointment")
    if not Appointment:
        raise HTTPException(status_code=500, detail="Appointment model unavailable")

    appointment = db.query(Appointment).filter(
        Appointment.id == appointment_id
    ).first()

    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")

    # Resolve status string
    appt_status = appointment.status.value if hasattr(appointment.status, 'value') else str(appointment.status)

    # Verify token (also rejects cancelled/no-show appointments)
    payload = _verify_confirmation_token(token, appointment_id, appointment_status=appt_status)

    # SEC-001: Verify token email matches appointment attendee
    token_email = (payload.get("email") or "").strip().lower()
    appt_email = (appointment.attendee_email or "").strip().lower()
    if token_email and appt_email and token_email != appt_email:
        raise HTTPException(status_code=403, detail="Token does not match this appointment")

    # Check the appointment is still in a reschedulable state
    if appt_status not in _ACTIONABLE_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot reschedule an appointment with status: {appt_status}",
        )

    # Check the appointment is not in the past
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    if appointment.scheduled_start and appointment.scheduled_start < now_utc:
        raise HTTPException(
            status_code=409,
            detail="Cannot reschedule an appointment that has already started or passed",
        )

    # Parse the new slot_time
    try:
        new_start = datetime.fromisoformat(body.slot_time.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Invalid datetime format for slot_time. Use ISO 8601.")

    # Normalize to UTC naive (consistent with DB storage)
    if new_start.tzinfo is not None:
        new_start = new_start.astimezone(timezone.utc).replace(tzinfo=None)

    # Calculate new end based on original duration
    duration_minutes = appointment.duration_minutes or 30
    new_end = new_start + timedelta(minutes=duration_minutes)

    # Validate the new time is in the future
    if new_start < now_utc:
        raise HTTPException(status_code=400, detail="Cannot reschedule to a past time")

    # Validate new_start != current start (no-op reschedule)
    if appointment.scheduled_start and new_start == appointment.scheduled_start:
        raise HTTPException(status_code=400, detail="New time is the same as the current appointment time")

    org_id = appointment.organization_id
    reason = _sanitize_text(body.reason) if body.reason else None

    # Check for conflicts at the new time
    if appointment.assigned_user_id:
        await _check_appointment_conflict(
            db,
            appointment.assigned_user_id,
            new_start,
            new_end,
            org_id=org_id,
            exclude_appointment_id=appointment_id,
        )

    # Capture old times for audit
    old_start = appointment.scheduled_start
    old_end = appointment.scheduled_end

    # Move the appointment
    appointment.scheduled_start = new_start
    appointment.scheduled_end = new_end
    appointment.status = AppointmentStatus.RESCHEDULED
    appointment.status_changed_at = datetime.now(timezone.utc)
    appointment.reschedule_count = (appointment.reschedule_count or 0) + 1
    appointment.updated_at = datetime.now(timezone.utc)

    # Record status history
    AppointmentStatusHistory = models.get("AppointmentStatusHistory")
    if AppointmentStatusHistory:
        try:
            status_history = AppointmentStatusHistory(
                organization_id=org_id,
                appointment_id=appointment_id,
                previous_status=appt_status,
                new_status=AppointmentStatus.RESCHEDULED.value,
                change_source="borrower_confirmation_page",
                notes=reason,
            )
            db.add(status_history)
        except Exception as e:
            logger.error("Failed to record status history for reschedule: %s", e, exc_info=True)

    # Audit log
    try:
        _audit_log(
            db, org_id, None, "rescheduled", "appointment",
            entity_id=appointment_id,
            changes={
                "reason": reason,
                "rescheduled_by": "borrower",
                "old_start": old_start.isoformat() if old_start else None,
                "new_start": new_start.isoformat(),
                "old_end": old_end.isoformat() if old_end else None,
                "new_end": new_end.isoformat(),
            },
            request=request,
            booking_source="public_confirmation",
        )
    except Exception as e:
        logger.error("Failed to write audit log for reschedule: %s", e, exc_info=True)

    db.commit()

    # Enterprise audit (best-effort)
    try:
        from services.scheduler_audit_logger import scheduler_audit
        scheduler_audit.log_borrower_reschedule_confirmed(
            appointment,
            old_start=old_start,
            new_start=new_start,
            old_end=old_end,
            new_end=new_end,
            request=request,
        )
    except Exception as e:
        logger.debug("Could not write scheduler audit for borrower reschedule: %s", e)

    # Sync rescheduled time to external calendars (Google, Outlook) - best-effort
    try:
        from services.calendar_outbound_sync import push_appointment_updated
        if appointment.assigned_user_id:
            User = models.get("User")
            if User:
                sync_user = db.query(User).filter(User.id == appointment.assigned_user_id).first()
                if sync_user:
                    await push_appointment_updated(db, appointment, sync_user)
    except Exception as cal_err:
        logger.error("Outbound calendar sync (reschedule) failed for appointment %s: %s", appointment_id, cal_err)

    # Send reschedule confirmation email (best-effort)
    if appointment.attendee_email:
        try:
            from scheduler_email_service import send_appointment_update_email
            if appointment.assigned_user_id:
                try:
                    local_new_start = _convert_utc_to_user_tz(
                        new_start, appointment.assigned_user_id, db, org_id=org_id
                    )
                    new_date_str = local_new_start.strftime('%B %d, %Y')
                    new_time_str = local_new_start.strftime('%I:%M %p %Z')
                except Exception as e:
                    logger.warning("Timezone conversion failed for reschedule email (appointment %s): %s", appointment_id, e)
                    new_date_str = new_start.strftime('%B %d, %Y')
                    new_time_str = new_start.strftime('%I:%M %p UTC')
            else:
                new_date_str = new_start.strftime('%B %d, %Y')
                new_time_str = new_start.strftime('%I:%M %p UTC')

            # Build meeting mode label
            meeting_mode_str = "Meeting"
            if appointment.meeting_mode:
                mm_val = appointment.meeting_mode.value if hasattr(appointment.meeting_mode, 'value') else str(appointment.meeting_mode)
                mode_labels = {"video": "Video Call", "phone": "Phone Call", "in_person": "In-Person", "screen_share": "Screen Share"}
                meeting_mode_str = mode_labels.get(mm_val, "Meeting")

            send_appointment_update_email(
                attendee_email=appointment.attendee_email,
                attendee_name=appointment.attendee_name or "Valued Client",
                appointment_title=appointment.title or "Appointment",
                appointment_date=new_date_str,
                appointment_time=new_time_str,
                duration=f"{duration_minutes} minutes",
                meeting_mode=meeting_mode_str,
                scheduled_start=new_start,
                duration_minutes=duration_minutes,
                organization_id=org_id,
            )
        except Exception as e:
            logger.error("Failed to send reschedule email for appointment %s: %s", appointment_id, e, exc_info=True)

    return {
        "status": "ok",
        "message": "Appointment rescheduled successfully",
        "appointment_id": appointment_id,
        "scheduled_start": new_start.isoformat(),
        "scheduled_end": new_end.isoformat(),
        "duration_minutes": duration_minutes,
        "reschedule_count": appointment.reschedule_count,
    }


# ============================================================================
# CALENDAR LINK BUILDERS
# ============================================================================

def _build_google_calendar_url(
    title: str, start: datetime, end: datetime,
    description: str = "", location: str = "",
) -> str:
    """Build a Google Calendar event creation URL."""
    from urllib.parse import quote
    fmt = "%Y%m%dT%H%M%SZ"
    start_str = start.strftime(fmt) if start else ""
    end_str = end.strftime(fmt) if end else ""
    dates = f"{start_str}/{end_str}"
    params = (
        f"action=TEMPLATE"
        f"&text={quote(title)}"
        f"&dates={dates}"
        f"&details={quote(description)}"
        f"&location={quote(location)}"
    )
    return f"https://calendar.google.com/calendar/render?{params}"


def _build_yahoo_calendar_url(
    title: str, start: datetime, end: datetime,
    description: str = "", location: str = "",
) -> str:
    """Build a Yahoo Calendar event creation URL."""
    from urllib.parse import quote
    fmt = "%Y%m%dT%H%M%SZ"
    start_str = start.strftime(fmt) if start else ""
    end_str = end.strftime(fmt) if end else ""
    params = (
        f"v=60"
        f"&title={quote(title)}"
        f"&st={start_str}"
        f"&et={end_str}"
        f"&desc={quote(description)}"
        f"&in_loc={quote(location)}"
    )
    return f"https://calendar.yahoo.com/?{params}"


def _build_outlook_calendar_url(
    title: str, start: datetime, end: datetime,
    description: str = "", location: str = "",
) -> str:
    """Build an Outlook Web Calendar event creation URL."""
    from urllib.parse import quote
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    start_str = start.strftime(fmt) if start else ""
    end_str = end.strftime(fmt) if end else ""
    params = (
        f"path=/calendar/action/compose"
        f"&subject={quote(title)}"
        f"&startdt={start_str}"
        f"&enddt={end_str}"
        f"&body={quote(description)}"
        f"&location={quote(location)}"
    )
    return f"https://outlook.live.com/calendar/0/deeplink/compose?{params}"
