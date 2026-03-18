"""
Scheduler Appointments - CRUD, status transitions, and export.

Endpoints:
  - GET    /appointments                          List appointments with filters
  - GET    /appointments/export/ics               Export appointments as ICS calendar file
  - GET    /appointments/{appointment_id}         Get appointment details
  - GET    /appointments/{appointment_id}/timeline  Get status history timeline
  - POST   /appointments                          Create a new appointment
  - PUT    /appointments/{appointment_id}         Update an appointment
  - POST   /appointments/{appointment_id}/cancel  Cancel an appointment
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from datetime import datetime, timedelta, date, time, timezone
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field
import html
import logging

from smart_scheduler_models import (
    AppointmentStatus, MeetingType, MeetingMode,
)
from scheduler_models import (
    AppointmentCreate, AppointmentUpdate, CancelAppointmentRequest,
)
from scheduler_email_service import (
    send_appointment_confirmation_email,
    send_appointment_confirmation_sms,
    send_appointment_update_email,
    send_appointment_update_sms,
    send_team_member_notification_email,
    send_appointment_cancellation_email,
    send_team_member_cancellation_email,
    generate_reschedule_url,
)
from services.notification_service import notification_service

from routes.scheduler._helpers import (
    get_current_user, get_models, _get_org_id, _is_scheduler_admin,
    _convert_utc_to_user_tz,
    _check_appointment_conflict,
    _log_appointment_activity, _create_followup_task,
    _audit_log, _validate_url, _mask_email,
)
from routes.scheduler.error_responses import (
    scheduler_error,
    VALIDATION_ERROR, NOT_FOUND, FORBIDDEN,
)
from routes.scheduler.constants import DEFAULT_APPOINTMENT_DURATION_MINUTES
from services.scheduler_audit_logger import scheduler_audit, get_appointment_audit_trail
from db import get_db

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================================
# PYDANTIC RESPONSE MODELS
# ============================================================================

class AppointmentItem(BaseModel):
    """A single appointment in a list or detail response."""
    id: Union[int, str] = Field(..., description="Appointment ID (int for v2, 'ai-NNN' for legacy)")
    title: Optional[str] = None
    description: Optional[str] = None
    meeting_type: Optional[str] = None
    meeting_mode: Optional[str] = None
    scheduled_start: Optional[str] = None
    scheduled_end: Optional[str] = None
    duration_minutes: Optional[int] = None
    status: Optional[str] = None
    attendee_name: Optional[str] = None
    attendee_email: Optional[str] = None
    video_link: Optional[str] = None
    lead_id: Optional[int] = None
    loan_id: Optional[int] = None
    booked_by_ai: Optional[bool] = None
    created_at: Optional[str] = None

    class Config:
        extra = "allow"


class AppointmentDetail(BaseModel):
    """Full appointment detail with all fields."""
    id: int
    appointment_type_id: Optional[int] = None
    title: Optional[str] = None
    description: Optional[str] = None
    meeting_type: Optional[str] = None
    meeting_mode: Optional[str] = None
    scheduled_start: Optional[str] = None
    scheduled_end: Optional[str] = None
    duration_minutes: Optional[int] = None
    timezone: Optional[str] = None
    location: Optional[str] = None
    video_link: Optional[str] = None
    phone_number: Optional[str] = None
    attendee_name: Optional[str] = None
    attendee_email: Optional[str] = None
    attendee_phone: Optional[str] = None
    attendee_notes: Optional[str] = None
    intake_responses: Optional[Dict[str, Any]] = None
    status: Optional[str] = None
    lead_id: Optional[int] = None
    loan_id: Optional[int] = None
    contact_id: Optional[int] = None
    assigned_user_id: Optional[int] = None
    booked_by_ai: Optional[bool] = None
    ai_booking_context: Optional[str] = None
    internal_notes: Optional[str] = None
    meeting_notes: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class AppointmentListResponse(BaseModel):
    """Response for listing appointments."""
    appointments: List[AppointmentItem] = Field(default_factory=list, description="List of appointments")
    total: int = Field(0, description="Total count across both tables")
    limit: int = Field(50, description="Page size")
    offset: int = Field(0, description="Page offset")


class AppointmentResponse(BaseModel):
    """Response for a single appointment detail."""
    appointment: AppointmentDetail


class AppointmentCreateResponse(BaseModel):
    """Response for appointment creation."""
    message: str = "Appointment created"
    appointment_id: int = Field(..., description="ID of the created appointment")
    scheduled_start: str = Field(..., description="Scheduled start (ISO 8601)")
    scheduled_end: str = Field(..., description="Scheduled end (ISO 8601)")
    email_sent: bool = Field(False, description="Whether confirmation email was sent")
    email_error: Optional[str] = Field(None, description="Email error if sending failed")
    calendar_event_created: bool = Field(False, description="Whether Outlook event was created")
    outlook_event_id: Optional[str] = Field(None, description="Outlook calendar event ID")


class AppointmentUpdateResponse(BaseModel):
    """Response for appointment update."""
    message: str = "Appointment updated"
    appointment_id: int = Field(..., description="ID of the updated appointment")
    emails_sent: List[str] = Field(default_factory=list, description="Email addresses notified")
    sms_sent: List[str] = Field(default_factory=list, description="Phone numbers notified via SMS")
    is_reschedule: bool = Field(False, description="Whether this was a reschedule")
    new_date: Optional[str] = Field(None, description="New appointment date (formatted)")
    new_time: Optional[str] = Field(None, description="New appointment time (formatted)")


class AppointmentCancelResponse(BaseModel):
    """Response for appointment cancellation."""
    message: str = "Appointment cancelled"
    emails_sent: List[str] = Field(default_factory=list, description="Email addresses notified")
    waitlist_offered: Optional[Dict[str, Any]] = Field(None, description="Waitlist offer details if a slot was offered")


class TimelineEntry(BaseModel):
    """A single status change entry in the appointment timeline."""
    id: Optional[int] = None
    previous_status: Optional[str] = None
    new_status: Optional[str] = None
    changed_by_name: Optional[str] = None
    changed_by_user_id: Optional[int] = None
    change_source: Optional[str] = None
    notes: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    changed_at: Optional[str] = None


class AppointmentSummary(BaseModel):
    """Summary of an appointment for the timeline response."""
    title: Optional[str] = None
    attendee_name: Optional[str] = None
    scheduled_start: Optional[str] = None
    scheduled_end: Optional[str] = None
    cancellation_reason: Optional[str] = None
    reschedule_count: Optional[int] = None


class AppointmentTimelineResponse(BaseModel):
    """Response for appointment timeline endpoint."""
    appointment_id: int = Field(..., description="Appointment ID")
    current_status: str = Field(..., description="Current appointment status")
    standard_progression: List[str] = Field(
        default_factory=list,
        description="Standard status progression for the timeline widget"
    )
    history: List[TimelineEntry] = Field(default_factory=list, description="Ordered status change history")
    appointment_summary: AppointmentSummary = Field(..., description="Appointment summary details")


# ============================================================================
# LIST APPOINTMENTS
# ============================================================================

@router.get("/appointments", response_model=AppointmentListResponse)
async def list_appointments(
    request: Request,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    status: Optional[str] = None,
    lead_id: Optional[int] = None,
    loan_id: Optional[int] = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db)
):
    """List appointments with filters."""
    # S11: Cap pagination bounds to prevent abuse
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    _models = get_models()
    Appointment = _models['Appointment']

    # Query main Appointment table
    query = db.query(Appointment).filter(
        Appointment.organization_id == org_id,
        or_(
            Appointment.assigned_user_id == user.id,
            Appointment.created_by_user_id == user.id
        )
    )

    if start_date:
        query = query.filter(Appointment.scheduled_start >= datetime.combine(start_date, time.min))

    if end_date:
        query = query.filter(Appointment.scheduled_start <= datetime.combine(end_date, time.max))

    if status:
        try:
            status_enum = AppointmentStatus(status)
            query = query.filter(Appointment.status == status_enum)
        except ValueError:
            valid_statuses = [s.value for s in AppointmentStatus]
            scheduler_error(
                400, VALIDATION_ERROR,
                "Invalid appointment status filter",
                detail=f"Got '{status}', expected one of: {valid_statuses}",
            )

    if lead_id:
        query = query.filter(Appointment.lead_id == lead_id)

    if loan_id:
        query = query.filter(Appointment.loan_id == loan_id)

    appointments = query.order_by(Appointment.scheduled_start.desc()).offset(offset).limit(limit).all()

    # Convert main appointments to response format
    result_appointments = [
        {
            "id": a.id,
            "title": a.title,
            "description": a.description,
            "meeting_type": a.meeting_type.value if a.meeting_type else None,
            "meeting_mode": a.meeting_mode.value if a.meeting_mode else None,
            "scheduled_start": a.scheduled_start.isoformat(),
            "scheduled_end": a.scheduled_end.isoformat(),
            "duration_minutes": a.duration_minutes,
            "status": a.status.value if a.status else None,
            "attendee_name": a.attendee_name,
            "attendee_email": a.attendee_email,
            "video_link": a.video_link,
            "lead_id": a.lead_id,
            "loan_id": a.loan_id,
            "booked_by_ai": a.booked_by_ai,
            "created_at": a.created_at.isoformat() if a.created_at else None
        }
        for a in appointments
    ]

    # Get total count from Appointment table
    total = query.order_by(None).count()

    return {
        "appointments": result_appointments,
        "total": total,
        "limit": limit,
        "offset": offset
    }


# ============================================================================
# EXPORT APPOINTMENTS AS ICS
# ============================================================================

@router.get("/appointments/export/ics")
async def export_appointments_ics(
    request: Request,
    start_date: Optional[str] = Query(None, description="ISO date or datetime for range start"),
    end_date: Optional[str] = Query(None, description="ISO date or datetime for range end"),
    db: Session = Depends(get_db),
):
    """Export appointments as an ICS calendar file for import into external calendars.

    Defaults to the next 30 days if no date range is specified. Only includes
    appointments with status booked, confirmed, or rescheduled.
    """
    from fastapi.responses import Response
    from utils.ics_generator import generate_ics_multi_event, PRODID_MORTGAGE

    user = await get_current_user(request, db)
    org_id = _get_org_id(user)
    user_id = user.id

    _models = get_models()
    Appointment = _models['Appointment']

    # Parse date range, default to next 30 days
    now = datetime.now(timezone.utc)
    if start_date:
        try:
            start = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
        except ValueError:
            scheduler_error(
                400, VALIDATION_ERROR,
                "Invalid start_date format",
                detail="Expected ISO 8601 date or datetime string",
            )
    else:
        start = now

    if end_date:
        try:
            end = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
        except ValueError:
            scheduler_error(
                400, VALIDATION_ERROR,
                "Invalid end_date format",
                detail="Expected ISO 8601 date or datetime string",
            )
    else:
        end = start + timedelta(days=30)

    # Query appointments assigned to the current user in the date range
    appointments = db.query(Appointment).filter(
        Appointment.assigned_user_id == user_id,
        Appointment.organization_id == org_id,
        Appointment.scheduled_start >= start,
        Appointment.scheduled_start <= end,
        Appointment.status.in_([
            AppointmentStatus.BOOKED,
            AppointmentStatus.CONFIRMED,
            AppointmentStatus.RESCHEDULED,
        ]),
    ).order_by(Appointment.scheduled_start.asc()).all()

    # Build event dicts for the multi-event ICS generator
    events = []
    for appt in appointments:
        appt_end = appt.scheduled_end or (
            appt.scheduled_start + timedelta(minutes=appt.duration_minutes or DEFAULT_APPOINTMENT_DURATION_MINUTES)
        )

        description_parts = []
        if appt.description:
            description_parts.append(appt.description)
        if appt.attendee_name:
            description_parts.append(f"Attendee: {appt.attendee_name}")
        if appt.attendee_email:
            description_parts.append(f"Email: {appt.attendee_email}")
        if appt.attendee_phone:
            description_parts.append(f"Phone: {appt.attendee_phone}")
        if appt.video_link:
            description_parts.append(f"Join: {appt.video_link}")

        events.append({
            "uid": f"appt-{appt.id}@perenniaai.com",
            "summary": appt.title or "Appointment",
            "description": "\n".join(description_parts),
            "start": appt.scheduled_start,
            "end": appt_end,
            "location": appt.video_link or appt.location or "",
        })

    ics_content = generate_ics_multi_event(
        events=events,
        prodid=PRODID_MORTGAGE,
        method="PUBLISH",
        calendar_name="Perennia AI - Appointments",
    )

    filename = f"appointments-{start.strftime('%Y%m%d')}-{end.strftime('%Y%m%d')}.ics"

    return Response(
        content=ics_content,
        media_type="text/calendar",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


# ============================================================================
# GET APPOINTMENT
# ============================================================================

@router.get("/appointments/{appointment_id}", response_model=AppointmentResponse)
async def get_appointment(
    appointment_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """Get appointment details"""
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    _models = get_models()
    Appointment = _models['Appointment']

    appointment = db.query(Appointment).filter(
        Appointment.id == appointment_id,
        Appointment.organization_id == org_id,
        or_(
            Appointment.assigned_user_id == user.id,
            Appointment.created_by_user_id == user.id
        )
    ).first()

    if not appointment:
        scheduler_error(404, NOT_FOUND, "Appointment not found")

    return {
        "appointment": {
            "id": appointment.id,
            "appointment_type_id": appointment.appointment_type_id,
            "title": appointment.title,
            "description": appointment.description,
            "meeting_type": appointment.meeting_type.value if appointment.meeting_type else None,
            "meeting_mode": appointment.meeting_mode.value if appointment.meeting_mode else None,
            "scheduled_start": appointment.scheduled_start.isoformat(),
            "scheduled_end": appointment.scheduled_end.isoformat(),
            "duration_minutes": appointment.duration_minutes,
            "timezone": appointment.timezone,
            "location": appointment.location,
            "video_link": appointment.video_link,
            "phone_number": appointment.phone_number,
            "attendee_name": appointment.attendee_name,
            "attendee_email": appointment.attendee_email,
            "attendee_phone": appointment.attendee_phone,
            "attendee_notes": appointment.attendee_notes,
            "intake_responses": appointment.intake_responses,
            "status": appointment.status.value if appointment.status else None,
            "lead_id": appointment.lead_id,
            "loan_id": appointment.loan_id,
            "contact_id": appointment.contact_id,
            "assigned_user_id": appointment.assigned_user_id,
            "booked_by_ai": appointment.booked_by_ai,
            "ai_booking_context": appointment.ai_booking_context,
            "internal_notes": appointment.internal_notes,
            "meeting_notes": appointment.meeting_notes,
            "created_at": appointment.created_at.isoformat() if appointment.created_at else None,
            "updated_at": appointment.updated_at.isoformat() if appointment.updated_at else None
        }
    }


# ============================================================================
# APPOINTMENT TIMELINE
# ============================================================================

@router.get("/appointments/{appointment_id}/timeline", response_model=AppointmentTimelineResponse)
async def get_appointment_timeline(
    appointment_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """Get the full status history timeline for an appointment.

    Returns an ordered list of status transitions with timestamps, user info,
    and notes. Used by the frontend AppointmentTimeline widget.
    """
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    _models = get_models()
    Appointment = _models['Appointment']

    # Verify appointment exists and belongs to this org/user
    appointment = db.query(Appointment).filter(
        Appointment.id == appointment_id,
        Appointment.organization_id == org_id,
        or_(
            Appointment.assigned_user_id == user.id,
            Appointment.created_by_user_id == user.id
        )
    ).first()

    if not appointment:
        scheduler_error(404, NOT_FOUND, "Appointment not found")

    # Query status history
    AppointmentStatusHistory = _models.get('AppointmentStatusHistory')

    history_entries = []
    if AppointmentStatusHistory:
        entries = db.query(AppointmentStatusHistory).filter(
            AppointmentStatusHistory.appointment_id == appointment_id,
            AppointmentStatusHistory.organization_id == org_id,
        ).order_by(AppointmentStatusHistory.changed_at.asc()).all()

        history_entries = [
            {
                "id": entry.id,
                "previous_status": entry.previous_status,
                "new_status": entry.new_status,
                "changed_by_name": entry.changed_by_name,
                "changed_by_user_id": entry.changed_by_user_id,
                "change_source": entry.change_source,
                "notes": entry.notes,
                "metadata": entry.extra_data or {},
                "changed_at": entry.changed_at.isoformat() if entry.changed_at else None,
            }
            for entry in entries
        ]

    # If no history exists, synthesize from appointment timestamps
    if not history_entries:
        synthetic = []
        if appointment.created_at:
            synthetic.append({
                "id": None,
                "previous_status": None,
                "new_status": "booked",
                "changed_by_name": None,
                "changed_by_user_id": appointment.created_by_user_id,
                "change_source": "ai" if appointment.booked_by_ai else "manual",
                "notes": None,
                "metadata": {},
                "changed_at": appointment.created_at.isoformat(),
            })
        if appointment.status and appointment.status.value not in ("booked", "available", "tentative"):
            synthetic.append({
                "id": None,
                "previous_status": "booked",
                "new_status": appointment.status.value,
                "changed_by_name": None,
                "changed_by_user_id": appointment.status_changed_by,
                "change_source": "system",
                "notes": appointment.cancellation_reason if appointment.status.value == "cancelled" else None,
                "metadata": {},
                "changed_at": (appointment.status_changed_at or appointment.updated_at or appointment.created_at).isoformat()
                    if (appointment.status_changed_at or appointment.updated_at or appointment.created_at) else None,
            })
        history_entries = synthetic

    # Standard progression for the timeline widget
    standard_progression = ["booked", "confirmed", "reminded", "checked_in", "completed"]
    current_status = appointment.status.value if appointment.status else "booked"

    return {
        "appointment_id": appointment.id,
        "current_status": current_status,
        "standard_progression": standard_progression,
        "history": history_entries,
        "appointment_summary": {
            "title": appointment.title,
            "attendee_name": appointment.attendee_name,
            "scheduled_start": appointment.scheduled_start.isoformat() if appointment.scheduled_start else None,
            "scheduled_end": appointment.scheduled_end.isoformat() if appointment.scheduled_end else None,
            "cancellation_reason": appointment.cancellation_reason,
            "reschedule_count": appointment.reschedule_count,
        }
    }


# ============================================================================
# APPOINTMENT AUDIT TRAIL
# ============================================================================

@router.get("/appointments/{appointment_id}/audit-trail")
async def get_appointment_audit_trail_endpoint(
    appointment_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """Get the complete audit trail for an appointment.

    Returns a chronologically ordered list of all audit log entries for the
    specified appointment, including booking source, event type, and metadata
    from all booking paths (authenticated, public, AI pipeline).
    """
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    _models = get_models()
    Appointment = _models['Appointment']

    # Verify appointment exists and belongs to this org
    appointment = db.query(Appointment).filter(
        Appointment.id == appointment_id,
        Appointment.organization_id == org_id,
    ).first()

    if not appointment:
        scheduler_error(404, NOT_FOUND, "Appointment not found")

    trail = get_appointment_audit_trail(db, appointment_id)

    return {
        "appointment_id": appointment_id,
        "audit_trail": trail,
        "count": len(trail),
    }


# ============================================================================
# CREATE APPOINTMENT
# ============================================================================

@router.post("/appointments", response_model=AppointmentCreateResponse)
async def create_appointment_endpoint(
    appt_data: AppointmentCreate,
    request: Request,
    db: Session = Depends(get_db)
):
    """Create a new appointment (authenticated path).

    Delegates creation, conflict checking, CRM integration, and audit logging
    to the shared appointment_creation_service.  This handler retains ownership
    of auth, HTTP response shaping, and post-commit side effects (emails,
    Outlook calendar sync, enterprise audit logging).
    """
    from services.appointment_creation_service import (
        create_appointment as create_appointment_service,
    )

    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    _models = get_models()

    # Calculate end time
    scheduled_end = appt_data.scheduled_start + timedelta(minutes=appt_data.duration_minutes)
    assigned_user = appt_data.assigned_user_id or user.id

    # Validate assigned_user_id belongs to the same org (prevent cross-tenant assignment)
    if appt_data.assigned_user_id and appt_data.assigned_user_id != user.id:
        User = _models.get('User')
        if User:
            target = db.query(User).filter(
                User.id == appt_data.assigned_user_id,
                User.organization_id == org_id,
            ).first()
            if not target:
                scheduler_error(403, FORBIDDEN, "Assigned user not found in your organization")

    # --- Delegate to shared service ---
    result = await create_appointment_service(
        db=db,
        organization_id=org_id,
        assigned_user_id=assigned_user,
        created_by_user_id=user.id,
        source="authenticated",
        # Appointment fields
        title=appt_data.title,
        scheduled_start=appt_data.scheduled_start,
        scheduled_end=scheduled_end,
        duration_minutes=appt_data.duration_minutes,
        timezone=appt_data.timezone,
        attendee_name=appt_data.attendee_name,
        attendee_email=appt_data.attendee_email,
        attendee_phone=appt_data.attendee_phone,
        # Optional fields
        appointment_type_id=appt_data.appointment_type_id,
        lead_id=appt_data.lead_id,
        loan_id=appt_data.loan_id,
        contact_id=appt_data.contact_id,
        description=appt_data.description,
        meeting_type=appt_data.meeting_type,
        meeting_mode=appt_data.meeting_mode,
        intake_responses=appt_data.intake_responses,
        attendee_notes=appt_data.attendee_notes,
        booked_by_ai=appt_data.booked_by_ai,
        ai_booking_context=appt_data.ai_booking_context,
        # Control flags
        check_conflicts=True,
        check_cross_source=True,
        generate_meeting_link=True,
        create_lead_if_missing=True,
    )

    if not result.success:
        raise HTTPException(status_code=409, detail=result.error)

    appointment = result.appointment

    # Surface non-fatal warnings from the shared service (e.g. meeting link failure)
    for warning in result.warnings:
        logger.warning(f"Appointment {appointment.id} creation warning: {warning}")

    # Enterprise audit: structured log for compliance
    scheduler_audit.log_appointment_created(
        appointment, user, request=request,
        booking_source="authenticated",
    )

    # Send confirmation email if attendee email is provided
    email_sent = False
    email_error = None
    if appt_data.attendee_email:
        try:
            # Format date and time for email
            appointment_date = appointment.scheduled_start.strftime("%A, %B %d, %Y")
            appointment_time = appointment.scheduled_start.strftime("%I:%M %p")
            duration_str = f"{appointment.duration_minutes} minutes"

            # Get meeting mode display name
            meeting_mode_str = "Phone Call"
            if appointment.meeting_mode:
                mode_display = {
                    "video": "Video Call",
                    "phone": "Phone Call",
                    "in_person": "In Person",
                    "screen_share": "Screen Share",
                }
                raw_mode = appointment.meeting_mode.value if hasattr(appointment.meeting_mode, 'value') else str(appointment.meeting_mode)
                meeting_mode_str = mode_display.get(raw_mode.lower(), "Phone Call")

            # Get team member info
            team_member_name = None
            team_member_email = None
            User = _models.get('User')
            if appointment.assigned_user_id and User:
                assigned_user_obj = db.query(User).filter(User.id == appointment.assigned_user_id).first()
                if assigned_user_obj:
                    team_member_name = assigned_user_obj.first_name
                    if assigned_user_obj.last_name:
                        team_member_name += f" {assigned_user_obj.last_name}"
                    team_member_email = assigned_user_obj.email

            # Get video link if this is a video call
            video_link = appointment.video_link if appointment.video_link else None

            logger.info(f"Sending confirmation email to {_mask_email(appt_data.attendee_email)}")
            # Send confirmation email to attendee (borrower) with calendar invite
            reschedule_url = generate_reschedule_url(appointment.id, appt_data.attendee_email)
            email_result = send_appointment_confirmation_email(
                attendee_email=appt_data.attendee_email,
                attendee_name=appt_data.attendee_name or "there",
                appointment_title=appointment.title,
                appointment_date=appointment_date,
                appointment_time=appointment_time,
                duration=duration_str,
                meeting_mode=meeting_mode_str,
                team_member_name=team_member_name,
                team_member_email=team_member_email,
                video_link=video_link,
                scheduled_start=appointment.scheduled_start,
                duration_minutes=appointment.duration_minutes,
                reschedule_url=reschedule_url
            )

            email_sent = email_result.get("success", False)
            if not email_sent:
                email_error = email_result.get("error", "Unknown email error")
                logger.warning(f"Email send failed for {appt_data.attendee_email}: {email_error}")

                # Fallback: try sending via Salesforce if SendGrid failed
                try:
                    from services.salesforce.email_sync_service import SalesforceEmailSyncService
                    from salesforce_integration_models import IntegrationProfile
                    sf_email_service = SalesforceEmailSyncService()
                    # Find user's active SF integration
                    sf_profile = db.query(IntegrationProfile).filter(
                        IntegrationProfile.user_id == user.id,
                        IntegrationProfile.provider == "salesforce",
                        IntegrationProfile.is_active == True
                    ).first()
                    if sf_profile:
                        sf_html = (
                            f"<p>Hi {html.escape(appt_data.attendee_name or 'there')},</p>"
                            f"<p>Your appointment has been confirmed!</p>"
                            f"<p><strong>Date:</strong> {html.escape(appointment_date)}<br>"
                            f"<strong>Time:</strong> {html.escape(appointment_time)}<br>"
                            f"<strong>Duration:</strong> {html.escape(duration_str)}<br>"
                            f"<strong>Meeting Type:</strong> {html.escape(meeting_mode_str or '')}</p>"
                            + (f"<p><strong>With:</strong> {html.escape(team_member_name)}</p>" if team_member_name else "")
                            + (f"<p><a href='{html.escape(video_link)}'>Join Video Call</a></p>" if video_link else "")
                            + "<p>We'll send you a reminder before your appointment.</p>"
                        )
                        sf_result = await sf_email_service.send_email_via_salesforce(
                            db=db,
                            integration_profile_id=sf_profile.id,
                            to_email=appt_data.attendee_email,
                            subject=f"Appointment Confirmed: {appointment.title}",
                            html_body=sf_html
                        )
                        if sf_result.get("success"):
                            email_sent = True
                            email_error = None
                            logger.info(f"Appointment email sent via Salesforce to {_mask_email(appt_data.attendee_email)}")
                        else:
                            logger.warning(f"Salesforce email fallback also failed: {sf_result.get('message')}")
                    else:
                        logger.info("No active Salesforce integration for appointment email fallback")
                except Exception as sf_err:
                    logger.warning(f"Salesforce email fallback error: {sf_err}")

            # Send notification email to team member (loan officer) with calendar invite
            if team_member_email:
                try:
                    team_result = send_team_member_notification_email(
                        team_member_email=team_member_email,
                        team_member_name=team_member_name or "Team Member",
                        attendee_name=appt_data.attendee_name or "Client",
                        attendee_email=appt_data.attendee_email or "",
                        attendee_phone=appt_data.attendee_phone or "",
                        appointment_title=appointment.title,
                        appointment_date=appointment_date,
                        appointment_time=appointment_time,
                        duration=duration_str,
                        meeting_mode=meeting_mode_str,
                        video_link=video_link,
                        scheduled_start=appointment.scheduled_start,
                        duration_minutes=appointment.duration_minutes
                    )
                    if not (team_result.get("success") if isinstance(team_result, dict) else team_result):
                        logger.warning(f"Failed to send team member notification via SendGrid")
                        # Fallback: try Salesforce for team member notification too
                        try:
                            from services.salesforce.email_sync_service import SalesforceEmailSyncService
                            from salesforce_integration_models import IntegrationProfile
                            sf_svc = SalesforceEmailSyncService()
                            sf_prof = db.query(IntegrationProfile).filter(
                                IntegrationProfile.user_id == user.id,
                                IntegrationProfile.provider == "salesforce",
                                IntegrationProfile.is_active == True
                            ).first()
                            if sf_prof:
                                tm_subject = f"New Appointment: {appointment.title}"
                                tm_body = f"<p>New appointment with {html.escape(appt_data.attendee_name or 'Client')} on {html.escape(appointment_date)} at {html.escape(appointment_time)} ({html.escape(duration_str)}).</p>"
                                sf_tm_result = await sf_svc.send_email_via_salesforce(
                                    db=db, integration_profile_id=sf_prof.id,
                                    to_email=team_member_email, subject=tm_subject, html_body=tm_body
                                )
                                if sf_tm_result.get("success"):
                                    logger.info(f"Team member notification sent via Salesforce to {team_member_email}")
                        except Exception as sf_tm_err:
                            logger.warning(f"SF fallback for team member email failed: {sf_tm_err}")
                    else:
                        logger.info(f"Team member notification sent to {team_member_email}")
                except Exception as team_email_error:
                    logger.error(f"Error sending team member notification: {team_email_error}")
        except Exception as e:
            email_error = str(e)
            logger.error(f"Error sending confirmation email: {e}")

    # Sync to external calendars (Google Calendar, Outlook) via provider system
    calendar_event_created = False
    try:
        from services.calendar_outbound_sync import push_appointment_created
        await push_appointment_created(db, appointment, user)
        calendar_event_created = True
    except Exception as cal_error:
        logger.error(f"Outbound calendar sync failed for appointment {appointment.id}: {cal_error}")

    return {
        "message": "Appointment created",
        "appointment_id": appointment.id,
        "scheduled_start": appointment.scheduled_start.isoformat(),
        "scheduled_end": appointment.scheduled_end.isoformat(),
        "email_sent": email_sent,
        "email_error": email_error,
        "calendar_event_created": calendar_event_created,
    }


# ============================================================================
# UPDATE APPOINTMENT
# ============================================================================

@router.put("/appointments/{appointment_id}", response_model=AppointmentUpdateResponse)
async def update_appointment(
    appointment_id: int,
    appt_data: AppointmentUpdate,
    request: Request,
    db: Session = Depends(get_db)
):
    """Update an appointment and send notification emails/SMS"""
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    _models = get_models()
    Appointment = _models['Appointment']
    User = _models['User']

    appointment = db.query(Appointment).filter(
        Appointment.id == appointment_id,
        Appointment.organization_id == org_id
    ).first()

    if not appointment:
        scheduler_error(404, NOT_FOUND, "Appointment not found")

    # Check permission
    is_admin = _is_scheduler_admin(user)
    is_owner = (
        appointment.assigned_user_id == user.id or
        appointment.created_by_user_id == user.id
    )

    if not is_admin and not is_owner:
        logger.warning(f"User {user.id} attempted to update appointment {appointment_id} without permission")
        scheduler_error(403, FORBIDDEN, "You don't have permission to update this appointment")

    update_fields = appt_data.model_dump(exclude_unset=True)
    is_cancellation = False
    is_reschedule = False
    send_notification = update_fields.pop('send_notification', True)

    # Store OLD date/time before any updates for comparison
    old_date = None
    old_time = None
    if appointment.scheduled_start:
        old_local_start = _convert_utc_to_user_tz(
            appointment.scheduled_start, appointment.assigned_user_id, db, org_id=org_id
        )
        old_date = old_local_start.strftime('%B %d, %Y')
        old_time = old_local_start.strftime('%I:%M %p %Z')

    # Handle status changes
    if "status" in update_fields:
        try:
            new_status = AppointmentStatus(update_fields["status"])
            update_fields["status"] = new_status
            update_fields["status_changed_at"] = datetime.now(timezone.utc)
            update_fields["status_changed_by"] = user.id

            if new_status == AppointmentStatus.COMPLETED:
                update_fields["completed_at"] = datetime.now(timezone.utc)
            elif new_status == AppointmentStatus.NO_SHOW:
                update_fields["no_show_at"] = datetime.now(timezone.utc)
            elif new_status == AppointmentStatus.CANCELLED:
                update_fields["cancelled_at"] = datetime.now(timezone.utc)
                is_cancellation = True
        except ValueError:
            valid_statuses = [s.value for s in AppointmentStatus]
            scheduler_error(
                400, VALIDATION_ERROR,
                "Invalid appointment status",
                detail=f"Got '{update_fields['status']}', expected one of: {valid_statuses}",
            )

    # Handle meeting mode
    if "meeting_mode" in update_fields:
        try:
            update_fields["meeting_mode"] = MeetingMode(update_fields["meeting_mode"])
        except ValueError:
            valid_modes = [m.value for m in MeetingMode]
            scheduler_error(
                400, VALIDATION_ERROR,
                "Invalid meeting mode",
                detail=f"Got '{update_fields['meeting_mode']}', expected one of: {valid_modes}",
            )

    # Handle rescheduling
    if "scheduled_start" in update_fields:
        new_start = update_fields["scheduled_start"]
        if "scheduled_end" in update_fields:
            new_end = update_fields["scheduled_end"]
        else:
            duration = appt_data.duration_minutes or appointment.duration_minutes or DEFAULT_APPOINTMENT_DURATION_MINUTES
            new_end = new_start + timedelta(minutes=duration)
            update_fields["scheduled_end"] = new_end

        # Conflict check for rescheduled time (exclude self to avoid self-conflict)
        _check_appointment_conflict(
            db,
            appointment.assigned_user_id,
            new_start,
            new_end,
            org_id=org_id,
            exclude_appointment_id=appointment.id
        )
        update_fields["reschedule_count"] = (appointment.reschedule_count or 0) + 1
        is_reschedule = True

    # S9: Validate URL scheme for user-supplied links
    if "video_link" in update_fields:
        update_fields["video_link"] = _validate_url(update_fields["video_link"])

    # Validate assigned_user_id belongs to same org (prevent cross-tenant assignment)
    if "assigned_user_id" in update_fields and update_fields["assigned_user_id"]:
        new_assigned = update_fields["assigned_user_id"]
        if new_assigned != user.id:
            target_user = db.query(User).filter(
                User.id == new_assigned,
                User.organization_id == org_id,
            ).first()
            if not target_user:
                scheduler_error(403, FORBIDDEN, "Assigned user not found in your organization")

    # Apply all updates
    _protected = {'id', 'organization_id', 'created_at', 'updated_at', 'user_id'}
    audit_changes = {}
    for field, value in update_fields.items():
        if hasattr(appointment, field) and field not in _protected:
            old_val = getattr(appointment, field, None)
            setattr(appointment, field, value)
            new_str = value.value if hasattr(value, 'value') else str(value) if value is not None else None
            old_str = old_val.value if hasattr(old_val, 'value') else str(old_val) if old_val is not None else None
            if new_str != old_str:
                audit_changes[field] = {'old': old_str, 'new': new_str}

    action = 'cancelled' if is_cancellation else 'rescheduled' if is_reschedule else 'updated'
    _audit_log(db, org_id, user.id, action, 'appointment',
               entity_id=appointment_id, changes=audit_changes, request=request,
               booking_source="authenticated")
    db.commit()
    db.refresh(appointment)

    # Enterprise audit: structured log for compliance
    if is_cancellation:
        scheduler_audit.log_appointment_cancelled(
            appointment, user, reason=audit_changes.get("cancellation_reason", {}).get("new"),
            request=request,
            booking_source="authenticated",
        )
    elif is_reschedule:
        old_start_val = audit_changes.get("scheduled_start", {}).get("old")
        new_start_val = audit_changes.get("scheduled_start", {}).get("new")
        old_end_val = audit_changes.get("scheduled_end", {}).get("old")
        new_end_val = audit_changes.get("scheduled_end", {}).get("new")
        scheduler_audit.log_appointment_rescheduled(
            appointment,
            old_time=old_start_val,
            new_time=new_start_val,
            user=user,
            request=request,
            old_end=old_end_val,
            new_end=new_end_val,
            reschedule_count=appointment.reschedule_count,
            initiated_by="lo",
            booking_source="authenticated",
        )
    else:
        # Check for no-show status transition
        new_status = audit_changes.get("status", {}).get("new")
        if new_status == "no_show":
            user_name = f"{getattr(user, 'first_name', '')} {getattr(user, 'last_name', '')}".strip()
            scheduler_audit.log_no_show(
                appointment, detected_by=user_name or "manual",
                user=user, request=request,
            )
        # Log the general update for all non-cancel, non-reschedule changes
        scheduler_audit.log_appointment_updated(
            appointment, user, changes=audit_changes, request=request,
            booking_source="authenticated",
        )

    # Get updated appointment details for notifications
    attendee_email = appointment.attendee_email
    attendee_name = appointment.attendee_name or 'Valued Client'
    attendee_phone = getattr(appointment, 'attendee_phone', None)
    appointment_title = appointment.title or 'Appointment'
    duration_minutes = appointment.duration_minutes or DEFAULT_APPOINTMENT_DURATION_MINUTES
    if duration_minutes < 60:
        duration_str = f"{duration_minutes} minutes"
    else:
        hours = duration_minutes // 60
        mins = duration_minutes % 60
        duration_str = f"{hours} hour{'s' if hours >= 2 else ''}"
        if mins:
            duration_str += f" {mins} minutes"
    meeting_mode = appointment.meeting_mode.value if hasattr(appointment.meeting_mode, 'value') else str(appointment.meeting_mode or 'PHONE')
    video_link = getattr(appointment, 'video_link', None)

    # Format NEW date and time for emails
    new_date = 'TBD'
    new_time = 'TBD'
    if appointment.scheduled_start:
        new_local_start = _convert_utc_to_user_tz(
            appointment.scheduled_start, appointment.assigned_user_id, db, org_id=org_id
        )
        new_date = new_local_start.strftime('%B %d, %Y')
        new_time = new_local_start.strftime('%I:%M %p %Z')

    # Get assigned team member info
    team_member = None
    team_member_name = None
    team_member_email = None
    if appointment.assigned_user_id:
        team_member = db.query(User).filter(User.id == appointment.assigned_user_id).first()
        if team_member:
            team_member_name = team_member.full_name or team_member.email
            team_member_email = team_member.email

    # Send notifications
    emails_sent = []
    sms_sent = []

    if is_cancellation and send_notification:
        logger.info(f"Appointment {appointment_id} cancelled via PUT, sending cancellation notifications")

        if attendee_email:
            try:
                result = send_appointment_cancellation_email(
                    attendee_email=attendee_email,
                    attendee_name=attendee_name,
                    appointment_title=appointment_title,
                    appointment_date=old_date or new_date,
                    appointment_time=old_time or new_time,
                    team_member_name=team_member_name,
                    cancellation_reason=None
                )
                if result.get("success") if isinstance(result, dict) else result:
                    emails_sent.append(attendee_email)
            except Exception as e:
                logger.error(f"Failed to send attendee cancellation email: {e}")

        if team_member_email and team_member and team_member.id != user.id:
            try:
                result = send_team_member_cancellation_email(
                    team_member_email=team_member_email,
                    team_member_name=team_member_name,
                    attendee_name=attendee_name,
                    appointment_title=appointment_title,
                    appointment_date=old_date or new_date,
                    appointment_time=old_time or new_time,
                    cancellation_reason=None,
                    cancelled_by=user.full_name or user.email
                )
                if result.get("success") if isinstance(result, dict) else result:
                    emails_sent.append(team_member_email)
            except Exception as e:
                logger.error(f"Failed to send team member cancellation email: {e}")

    elif send_notification and (is_reschedule or bool(set(audit_changes.keys()) & {'scheduled_start', 'scheduled_end', 'attendee_name', 'attendee_email', 'meeting_mode', 'status', 'duration_minutes', 'video_link', 'location'})):
        logger.info(f"Appointment {appointment_id} updated, sending update notifications")

        if attendee_email:
            try:
                result = send_appointment_update_email(
                    attendee_email=attendee_email,
                    attendee_name=attendee_name,
                    appointment_title=appointment_title,
                    appointment_date=new_date,
                    appointment_time=new_time,
                    duration=duration_str,
                    meeting_mode=meeting_mode.replace('_', ' ').title(),
                    team_member_name=team_member_name,
                    team_member_email=team_member_email,
                    video_link=video_link,
                    scheduled_start=appointment.scheduled_start,
                    duration_minutes=duration_minutes,
                    old_date=old_date if is_reschedule else None,
                    old_time=old_time if is_reschedule else None
                )
                if result.get("success"):
                    emails_sent.append(attendee_email)
            except Exception as e:
                logger.error(f"Failed to send attendee update email: {e}")

        if attendee_phone:
            try:
                result = send_appointment_update_sms(
                    attendee_phone=attendee_phone,
                    attendee_name=attendee_name,
                    appointment_date=new_date,
                    appointment_time=new_time,
                    team_member_name=team_member_name
                )
                if result.get("success") if isinstance(result, dict) else result:
                    sms_sent.append(attendee_phone)
            except Exception as e:
                logger.error(f"Failed to send attendee update SMS: {e}")

    # Sync changes to external calendars (Google, Outlook)
    if is_cancellation:
        try:
            from services.calendar_outbound_sync import push_appointment_cancelled
            await push_appointment_cancelled(db, appointment, user)
        except Exception as cal_err:
            logger.error(f"Outbound calendar sync (cancel) failed for appointment {appointment_id}: {cal_err}")
    elif is_reschedule or bool(set(audit_changes.keys()) & {'scheduled_start', 'scheduled_end', 'title', 'location', 'video_link', 'attendee_email'}):
        try:
            from services.calendar_outbound_sync import push_appointment_updated
            await push_appointment_updated(db, appointment, user)
        except Exception as cal_err:
            logger.error(f"Outbound calendar sync (update) failed for appointment {appointment_id}: {cal_err}")

    return {
        "message": "Appointment updated",
        "appointment_id": appointment_id,
        "emails_sent": emails_sent,
        "sms_sent": sms_sent,
        "is_reschedule": is_reschedule,
        "new_date": new_date,
        "new_time": new_time
    }


# ============================================================================
# CANCEL APPOINTMENT
# ============================================================================

@router.post("/appointments/{appointment_id}/cancel", response_model=AppointmentCancelResponse)
async def cancel_appointment(
    appointment_id: int,
    cancel_data: Optional[CancelAppointmentRequest] = None,
    request: Request = None,
    db: Session = Depends(get_db),
    background_tasks: BackgroundTasks = None
):
    """Cancel an appointment and send cancellation notifications"""
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)
    reason = cancel_data.reason if cancel_data else None

    _models = get_models()
    Appointment = _models['Appointment']
    User = _models['User']

    # Admins can cancel any appointment in the org; non-admins only their own
    is_admin = _is_scheduler_admin(user)
    cancel_query = db.query(Appointment).filter(
        Appointment.id == appointment_id,
        Appointment.organization_id == org_id,
    )
    if not is_admin:
        cancel_query = cancel_query.filter(
            or_(
                Appointment.assigned_user_id == user.id,
                Appointment.created_by_user_id == user.id,
            )
        )
    appointment = cancel_query.first()

    if not appointment:
        scheduler_error(404, NOT_FOUND, "Appointment not found")

    # Store appointment details before cancellation for email notifications
    attendee_email = getattr(appointment, 'attendee_email', None)
    attendee_name = getattr(appointment, 'attendee_name', None) or 'Valued Client'
    appointment_title = appointment.title or 'Appointment'

    # Format date and time for emails
    if appointment.scheduled_start:
        local_start = _convert_utc_to_user_tz(
            appointment.scheduled_start, appointment.assigned_user_id, db, org_id=org_id
        )
        appointment_date = local_start.strftime('%B %d, %Y')
        appointment_time = local_start.strftime('%I:%M %p %Z')
    else:
        appointment_date = 'TBD'
        appointment_time = 'TBD'

    # Get assigned team member info
    team_member = None
    team_member_name = None
    team_member_email = None
    if appointment.assigned_user_id:
        team_member = db.query(User).filter(User.id == appointment.assigned_user_id).first()
        if team_member:
            team_member_name = team_member.full_name or team_member.email
            team_member_email = team_member.email

    # Cancel the appointment
    appointment.status = AppointmentStatus.CANCELLED
    appointment.cancelled_at = datetime.now(timezone.utc)
    appointment.cancellation_reason = reason
    appointment.status_changed_by = user.id
    appointment.status_changed_at = datetime.now(timezone.utc)

    _audit_log(db, org_id, user.id, 'cancelled', 'appointment',
               entity_id=appointment_id, changes={'reason': reason}, request=request,
               booking_source="authenticated")

    # CRM: Log cancellation activity
    _log_appointment_activity(
        db, org_id, user.id, appointment.lead_id, appointment.loan_id,
        f"Appointment cancelled: {appointment.title} - Reason: {reason or 'None given'}",
        activity_type="Note"
    )

    # CRM: Create re-engagement task
    _create_followup_task(
        db, org_id, appointment.assigned_user_id or user.id,
        appointment.lead_id, appointment.loan_id,
        title=f"Re-engage: {appointment.attendee_name or 'cancelled booking'}"[:255],
        description=f"Appointment '{appointment.title}' was cancelled. "
                    f"Reason: {reason or 'None given'}. Attempt to re-engage.",
        due_date=datetime.now(timezone.utc) + timedelta(days=1),
        priority="high"
    )

    # H-2: Single atomic commit -- cancellation + audit + activity + task
    db.commit()

    # Enterprise audit: structured log for compliance
    # Determine if cancellation is within the org's cancellation policy
    within_policy = None
    is_late_cancellation = None
    try:
        from services.cancellation_policy_service import CancellationPolicyService
        policy_svc = CancellationPolicyService(db)
        policy = policy_svc.get_or_create_policy(org_id)
        if policy and appointment.scheduled_start:
            min_notice_hours = getattr(policy, "min_notice_hours", 24)
            notice_given = (appointment.scheduled_start - datetime.now(timezone.utc).replace(tzinfo=None)).total_seconds() / 3600
            is_late_cancellation = notice_given < min_notice_hours
            within_policy = not is_late_cancellation
    except Exception as e:
        logger.debug(f"Could not check cancellation policy for audit: {e}")

    scheduler_audit.log_appointment_cancelled(
        appointment, user, reason=reason, request=request,
        within_policy=within_policy,
        is_late_cancellation=is_late_cancellation,
        booking_source="authenticated",
    )

    logger.info(f"Appointment {appointment_id} cancelled by user {user.id}")

    # Waitlist auto-offer: notify next person on the waitlist for this appointment type
    waitlist_offered = None
    try:
        from services.waitlist_service import WaitlistService
        _models = get_models()
        waitlist_svc = WaitlistService(db, _models)
        waitlist_offered = waitlist_svc.process_cancellation(appointment_id, org_id)
        if waitlist_offered:
            db.commit()
            logger.info(f"Waitlist auto-offer: offered to {waitlist_offered.get('name')} (entry {waitlist_offered.get('entry_id')})")
    except Exception as e:
        logger.warning(f"Waitlist auto-offer failed (non-blocking): {e}")

    # Send cancellation emails
    emails_sent = []

    if attendee_email:
        try:
            result = send_appointment_cancellation_email(
                attendee_email=attendee_email,
                attendee_name=attendee_name,
                appointment_title=appointment_title,
                appointment_date=appointment_date,
                appointment_time=appointment_time,
                team_member_name=team_member_name,
                cancellation_reason=reason
            )
            if result.get("success") if isinstance(result, dict) else result:
                emails_sent.append(attendee_email)
        except Exception as e:
            logger.error(f"Failed to send attendee cancellation email: {e}")

    if team_member_email and team_member and team_member.id != user.id:
        try:
            result = send_team_member_cancellation_email(
                team_member_email=team_member_email,
                team_member_name=team_member_name,
                attendee_name=attendee_name,
                appointment_title=appointment_title,
                appointment_date=appointment_date,
                appointment_time=appointment_time,
                cancellation_reason=reason,
                cancelled_by=user.full_name or user.email
            )
            if result.get("success") if isinstance(result, dict) else result:
                emails_sent.append(team_member_email)
        except Exception as e:
            logger.error(f"Failed to send team member cancellation email: {e}")

    # Delete external calendar events (Google, Outlook)
    try:
        from services.calendar_outbound_sync import push_appointment_cancelled
        await push_appointment_cancelled(db, appointment, user)
    except Exception as cal_err:
        logger.error(f"Outbound calendar sync (cancel) failed for appointment {appointment_id}: {cal_err}")

    return {
        "message": "Appointment cancelled",
        "emails_sent": emails_sent,
        "waitlist_offered": waitlist_offered,
    }
