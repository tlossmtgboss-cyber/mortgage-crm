"""
Scheduler Appointments CRUD - Appointment lifecycle management.

Extracted from routes/scheduler_appointment_routes.py

Endpoints:
  - GET    /appointments                          List appointments with filters
  - GET    /appointments/{appointment_id}         Get appointment details
  - POST   /appointments                          Create a new appointment
  - PUT    /appointments/{appointment_id}         Update an appointment
  - POST   /appointments/{appointment_id}/cancel  Cancel an appointment
  - GET    /booking-links/all                     List all org booking links (admin)
  - GET    /booking-links                         List user's booking links
  - POST   /booking-links                         Create a booking link
  - DELETE /booking-links/{link_id}               Delete (deactivate) a booking link
  - POST   /available-slots                       Get available time slots
  - POST   /ai-recommend-slots                    AI-recommended time slots
  - GET    /appointments/{id}/no-show-risk        No-show risk for one appointment
  - GET    /analytics/no-show-risks               Batch no-show risk for a date
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func, desc, case, String, extract
from datetime import datetime, timedelta, date, time, timezone
from typing import List, Optional
import html
import logging
import pytz

from smart_scheduler_models import (
    AppointmentStatus, MeetingType, MeetingMode, RoutingStrategy,
    DEFAULT_WORKING_HOURS,
)
from scheduler_models import (
    AppointmentCreate, AppointmentUpdate,
    BookingLinkCreate, AvailableSlotsRequest,
    CancelAppointmentRequest,
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
from services.microsoft_graph import create_event_via_graph, CalendarResult

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================================
# DEPENDENCY INJECTION STORAGE
# ============================================================================

_get_db = None
_get_current_user_func = None
_models = None
_helpers = None


def set_dependencies(get_db_func, get_current_user_func, models_dict, helpers=None):
    """Set dependencies from parent module.

    helpers dict should contain:
        _check_appointment_conflict, _check_duplicate_booking,
        _log_appointment_activity, _ensure_lead_for_booking,
        _create_followup_task, _check_lo_licensing,
        _get_user_timezone, _generate_available_slots, _audit_log,
        _validate_url, _mask_email, _create_comm_failure_task,
        _calculate_no_show_risk
    """
    global _get_db, _get_current_user_func, _models, _helpers
    _get_db = get_db_func
    _get_current_user_func = get_current_user_func
    _models = models_dict
    _helpers = helpers or {}


from db import get_db


async def get_current_user(request: Request, db: Session = Depends(get_db)):
    if _get_current_user_func is None:
        raise RuntimeError("Dependencies not set")
    auth_header = request.headers.get("Authorization", "")
    token = auth_header[7:] if auth_header.startswith("Bearer ") else ""
    return await _get_current_user_func(token=token, request=request, db=db)


def _get_org_id(user) -> int:
    """Get organization_id from user, raise 403 if missing."""
    org_id = getattr(user, 'organization_id', None)
    if org_id is None:
        raise HTTPException(status_code=403, detail="No organization context")
    return org_id


def _is_scheduler_admin(user) -> bool:
    """
    Standardized admin check for scheduler endpoints.
    Uses permission_role (primary) with role fallback.
    Only true security roles qualify.
    """
    role = getattr(user, 'permission_role', '') or getattr(user, 'role', '') or ''
    return role.lower() in ('admin', 'site_admin', 'platform_admin')


# Helper accessors — delegate to the parent helpers dict
def _check_appointment_conflict(db, assigned_user_id, start_time, end_time, org_id=None, exclude_appointment_id=None):
    return _helpers['_check_appointment_conflict'](db, assigned_user_id, start_time, end_time, org_id=org_id, exclude_appointment_id=exclude_appointment_id)


def _check_duplicate_booking(db, attendee_email, assigned_user_id, start_time, org_id=None, window_minutes=30):
    return _helpers['_check_duplicate_booking'](db, attendee_email, assigned_user_id, start_time, org_id=org_id, window_minutes=window_minutes)


def _log_appointment_activity(db, org_id, user_id, lead_id, loan_id, content, activity_type="Meeting"):
    return _helpers['_log_appointment_activity'](db, org_id, user_id, lead_id, loan_id, content, activity_type=activity_type)


def _ensure_lead_for_booking(db, attendee_email, attendee_name, attendee_phone, assigned_user_id, org_id):
    return _helpers['_ensure_lead_for_booking'](db, attendee_email, attendee_name, attendee_phone, assigned_user_id, org_id)


def _create_followup_task(db, org_id, owner_id, lead_id, loan_id, title, description, due_date, priority="medium"):
    return _helpers['_create_followup_task'](db, org_id, owner_id, lead_id, loan_id, title, description, due_date, priority=priority)


def _get_user_timezone(db, user_id, org_id=None):
    return _helpers['_get_user_timezone'](db, user_id, org_id=org_id)


def _generate_available_slots(db, user_ids, start_date, end_date, duration_minutes=30,
                               org_id=None, max_per_day=None, check_cross_source=True,
                               include_user_id=False, include_day_name=False,
                               time_key_format="start"):
    return _helpers['_generate_available_slots'](
        db=db, user_ids=user_ids, start_date=start_date, end_date=end_date,
        duration_minutes=duration_minutes, org_id=org_id, max_per_day=max_per_day,
        check_cross_source=check_cross_source, include_user_id=include_user_id,
        include_day_name=include_day_name, time_key_format=time_key_format,
    )


def _audit_log(db, org_id, user_id, action, entity_type, entity_id=None, changes=None, request=None):
    return _helpers['_audit_log'](db, org_id, user_id, action, entity_type, entity_id=entity_id, changes=changes, request=request)


def _validate_url(value):
    return _helpers['_validate_url'](value)


def _mask_email(email):
    return _helpers['_mask_email'](email)


def _calculate_no_show_risk(appointment, db, Appointment, AppointmentStatus, org_id):
    return _helpers['_calculate_no_show_risk'](appointment, db, Appointment, AppointmentStatus, org_id)


# ============================================================================
# APPOINTMENT ENDPOINTS
# ============================================================================

@router.get("/appointments")
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
    """List appointments with filters - includes both Appointment and ScheduledAppointment tables"""
    # S11: Cap pagination bounds to prevent abuse
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

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
            raise HTTPException(status_code=400, detail=f"Invalid status filter: {status}")

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

    # DEPRECATED: Also query legacy ScheduledAppointment table (scheduled_appointments)
    # This table is from the v1 SmartSchedulerService. New bookings go to scheduler_appointments (v2).
    # Kept here temporarily to surface any legacy data that hasn't been migrated.
    ai_appointments_data = []
    ai_total = 0
    try:
        from services.smart_scheduler_service import ScheduledAppointment

        ai_query = db.query(ScheduledAppointment).filter(
            ScheduledAppointment.loan_officer_id == user.id,
            ScheduledAppointment.organization_id == org_id
        )

        if start_date:
            ai_query = ai_query.filter(ScheduledAppointment.start_time >= datetime.combine(start_date, time.min))

        if end_date:
            ai_query = ai_query.filter(ScheduledAppointment.start_time <= datetime.combine(end_date, time.max))

        if status:
            ai_query = ai_query.filter(ScheduledAppointment.status == status)

        # Get total count for AI appointments
        ai_total = ai_query.count()

        # Apply same offset/limit as main query for consistent pagination
        ai_results = ai_query.order_by(ScheduledAppointment.start_time.desc()).offset(offset).limit(limit).all()

        # Convert legacy AI appointments to same response format
        for a in ai_results:
            ai_appointments_data.append({
                "id": f"ai-{a.id}",
                "appointment_id": a.appointment_id,
                "title": f"Appointment with {a.contact_name}",
                "description": a.notes,
                "meeting_type": a.appointment_type,
                "meeting_mode": "PHONE",
                "scheduled_start": a.start_time.isoformat() if a.start_time else None,
                "scheduled_end": a.end_time.isoformat() if a.end_time else None,
                "start_time": a.start_time.isoformat() if a.start_time else None,
                "end_time": a.end_time.isoformat() if a.end_time else None,
                "duration_minutes": a.duration_minutes,
                "status": a.status.upper() if a.status else "BOOKED",
                "attendee_name": a.contact_name,
                "contact_name": a.contact_name,
                "attendee_email": a.contact_email,
                "contact_email": a.contact_email,
                "contact_phone": a.contact_phone,
                "video_link": a.meeting_link,
                "lead_id": a.contact_id,
                "loan_id": None,
                "booked_by_ai": True,
                "booked_via": a.booked_via,
                "created_at": a.created_at.isoformat() if a.created_at else None
            })
    except Exception as e:
        logger.debug(f"Legacy ScheduledAppointments query skipped: {e}")

    # Merge and sort the page-slice from both sources
    result_appointments.extend(ai_appointments_data)
    result_appointments.sort(
        key=lambda x: x.get('scheduled_start') or x.get('start_time') or '',
        reverse=True
    )

    # Get accurate total count from main Appointment table
    main_total = query.order_by(None).count()
    total = main_total + ai_total

    return {
        "appointments": result_appointments[:limit],  # Cap to limit after merge
        "total": total,
        "limit": limit,
        "offset": offset
    }


@router.get("/appointments/{appointment_id}")
async def get_appointment(
    appointment_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """Get appointment details"""
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

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
        raise HTTPException(status_code=404, detail="Appointment not found")

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


@router.get("/appointments/{appointment_id}/timeline")
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
        raise HTTPException(status_code=404, detail="Appointment not found")

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
                "metadata": entry.metadata or {},
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


@router.post("/appointments")
async def create_appointment(
    appt_data: AppointmentCreate,
    request: Request,
    db: Session = Depends(get_db)
):
    """Create a new appointment"""
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    Appointment = _models['Appointment']

    # Calculate end time
    scheduled_end = appt_data.scheduled_start + timedelta(minutes=appt_data.duration_minutes)

    # Check for conflicts before creating
    assigned_user = appt_data.assigned_user_id or user.id
    _check_appointment_conflict(db, assigned_user, appt_data.scheduled_start, scheduled_end, org_id=org_id)
    _check_duplicate_booking(db, appt_data.attendee_email, assigned_user, appt_data.scheduled_start, org_id=org_id)

    # Parse enums
    meeting_type = MeetingType.CUSTOM
    if appt_data.meeting_type:
        try:
            meeting_type = MeetingType(appt_data.meeting_type)
        except ValueError:
            pass

    meeting_mode = MeetingMode.VIDEO
    if appt_data.meeting_mode:
        try:
            meeting_mode = MeetingMode(appt_data.meeting_mode)
        except ValueError:
            pass

    appointment = Appointment(
        organization_id=org_id,
        appointment_type_id=appt_data.appointment_type_id,
        assigned_user_id=appt_data.assigned_user_id or user.id,
        created_by_user_id=user.id,
        lead_id=appt_data.lead_id,
        loan_id=appt_data.loan_id,
        contact_id=appt_data.contact_id,
        title=appt_data.title,
        description=appt_data.description,
        meeting_type=meeting_type,
        meeting_mode=meeting_mode,
        scheduled_start=appt_data.scheduled_start,
        scheduled_end=scheduled_end,
        duration_minutes=appt_data.duration_minutes,
        timezone=appt_data.timezone,
        attendee_name=appt_data.attendee_name,
        attendee_email=appt_data.attendee_email,
        attendee_phone=appt_data.attendee_phone,
        attendee_notes=appt_data.attendee_notes,
        intake_responses=appt_data.intake_responses,
        status=AppointmentStatus.BOOKED,
        status_changed_at=datetime.now(timezone.utc),
        booked_by_ai=appt_data.booked_by_ai,
        ai_booking_context=appt_data.ai_booking_context
    )

    db.add(appointment)
    _audit_log(db, org_id, user.id, 'created', 'appointment', changes={
        'title': appt_data.title,
        'attendee_email': appt_data.attendee_email,
        'scheduled_start': appt_data.scheduled_start.isoformat() if appt_data.scheduled_start else None,
    }, request=request)
    db.flush()  # Get appointment.id without committing
    # Backfill entity_id now that we have it
    _audit_log(db, org_id, user.id, '_id_backfill', 'appointment', entity_id=appointment.id)

    logger.info(f"Appointment created: {appointment.id} by user {user.id}")

    # CRM Integration: Create/link lead if not already linked
    if not appointment.lead_id and appt_data.attendee_email:
        lead_id = _ensure_lead_for_booking(
            db, appt_data.attendee_email, appt_data.attendee_name,
            appt_data.attendee_phone, appointment.assigned_user_id, org_id
        )
        if lead_id:
            appointment.lead_id = lead_id

    # CRM: Log activity
    _log_appointment_activity(
        db, org_id, user.id, appointment.lead_id, appointment.loan_id,
        f"Appointment scheduled: {appointment.title} on "
        f"{appointment.scheduled_start.strftime('%m/%d/%Y %I:%M %p') if appointment.scheduled_start else 'TBD'}"
    )

    # CRM: Create follow-up task
    if appointment.scheduled_end:
        _create_followup_task(
            db, org_id, appointment.assigned_user_id,
            appointment.lead_id, appointment.loan_id,
            title=f"Follow up after: {appointment.title}"[:255],
            description=f"Follow up with {appt_data.attendee_name or 'attendee'} after "
                        f"meeting on {appointment.scheduled_start.strftime('%m/%d/%Y') if appointment.scheduled_start else 'TBD'}",
            due_date=appointment.scheduled_end + timedelta(days=1),
        )

    # H-2: Single atomic commit — appointment + audit + lead + activity + task
    db.commit()
    db.refresh(appointment)

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
                assigned_user = db.query(User).filter(User.id == appointment.assigned_user_id).first()
                if assigned_user:
                    team_member_name = assigned_user.first_name
                    if assigned_user.last_name:
                        team_member_name += f" {assigned_user.last_name}"
                    team_member_email = assigned_user.email

            # Get video link if this is a video call
            video_link = None
            if appointment.video_link:
                video_link = appointment.video_link

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

    # Auto-create calendar event in team member's Outlook calendar
    calendar_event_created = False
    outlook_event_id = None

    # Get video_link from appointment (set earlier in the flow)
    calendar_video_link = appointment.video_link if appointment.video_link else None

    # Get meeting mode string for calendar event
    calendar_meeting_mode = "Phone Call"
    if appointment.meeting_mode:
        mode_display_map = {
            "video": "Video Call",
            "phone": "Phone Call",
            "in_person": "In Person",
            "screen_share": "Screen Share",
        }
        mode_val = appointment.meeting_mode.value if hasattr(appointment.meeting_mode, 'value') else str(appointment.meeting_mode)
        calendar_meeting_mode = mode_display_map.get(mode_val.lower(), "Phone Call")

    if appointment.assigned_user_id:
        try:
            # Build event description — escape all user data for HTML context
            event_description = f"""
            <h3>Client Meeting</h3>
            <p><strong>Client:</strong> {html.escape(appt_data.attendee_name or 'Not specified')}</p>
            <p><strong>Email:</strong> {html.escape(appt_data.attendee_email or 'Not specified')}</p>
            <p><strong>Phone:</strong> {html.escape(appt_data.attendee_phone or 'Not specified')}</p>
            <p><strong>Meeting Type:</strong> {html.escape(calendar_meeting_mode)}</p>
            """
            if appointment.description:
                event_description += f"<p><strong>Notes:</strong> {html.escape(appointment.description)}</p>"
            if calendar_video_link:
                event_description += f"<p><strong>Video Link:</strong> <a href='{html.escape(calendar_video_link)}'>{html.escape(calendar_video_link)}</a></p>"

            # Create calendar event via Microsoft Graph
            calendar_result: CalendarResult = await create_event_via_graph(
                user_id=appointment.assigned_user_id,
                subject=f"Meeting: {appt_data.attendee_name or 'Client'} - {appointment.title}",
                start=appointment.scheduled_start,
                end=appointment.scheduled_end,
                db=db,
                attendees=[appt_data.attendee_email] if appt_data.attendee_email else None,
                location=calendar_video_link if calendar_video_link else None,
                add_teams_link=False,  # Don't add Teams link since we may already have a video link
                body=event_description
            )

            if calendar_result.success:
                calendar_event_created = True
                outlook_event_id = calendar_result.event_id
                # Store the event ID in the appointment for future updates/deletions
                appointment.outlook_event_id = outlook_event_id
                db.commit()  # Separate commit OK — appointment already persisted, this is best-effort metadata
                logger.info(f"Outlook calendar event created for appointment {appointment.id}: {outlook_event_id}")
            else:
                logger.warning(f"Could not create Outlook calendar event: {calendar_result.error}")

        except Exception as cal_error:
            logger.error(f"Error creating Outlook calendar event: {cal_error}")

    return {
        "message": "Appointment created",
        "appointment_id": appointment.id,
        "scheduled_start": appointment.scheduled_start.isoformat(),
        "scheduled_end": appointment.scheduled_end.isoformat(),
        "email_sent": email_sent,
        "email_error": email_error,
        "calendar_event_created": calendar_event_created,
        "outlook_event_id": outlook_event_id
    }


@router.put("/appointments/{appointment_id}")
async def update_appointment(
    appointment_id: int,
    appt_data: AppointmentUpdate,
    request: Request,
    db: Session = Depends(get_db)
):
    """Update an appointment and send notification emails/SMS"""
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    Appointment = _models['Appointment']
    User = _models['User']

    # First try to find the appointment
    appointment = db.query(Appointment).filter(
        Appointment.id == appointment_id,
        Appointment.organization_id == org_id
    ).first()

    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")

    # Check permission - allow if user is admin, assigned to the appointment, or created it
    is_admin = _is_scheduler_admin(user)
    is_owner = (
        appointment.assigned_user_id == user.id or
        appointment.created_by_user_id == user.id
    )

    if not is_admin and not is_owner:
        logger.warning(f"User {user.id} attempted to update appointment {appointment_id} without permission")
        raise HTTPException(status_code=403, detail="You don't have permission to update this appointment")

    update_fields = appt_data.model_dump(exclude_unset=True)
    is_cancellation = False
    is_reschedule = False
    send_notification = update_fields.pop('send_notification', True)  # Remove from fields, default to True

    # Store OLD date/time before any updates for comparison
    old_date = None
    old_time = None
    tz = pytz.timezone(_get_user_timezone(db, appointment.assigned_user_id, org_id=org_id))
    if appointment.scheduled_start:
        old_local_start = appointment.scheduled_start.replace(tzinfo=pytz.UTC).astimezone(tz)
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
            raise HTTPException(status_code=400, detail=f"Invalid status: {update_fields['status']}")

    # Handle meeting mode
    if "meeting_mode" in update_fields:
        try:
            update_fields["meeting_mode"] = MeetingMode(update_fields["meeting_mode"])
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid meeting mode: {update_fields['meeting_mode']}")

    # Handle rescheduling - check if date/time changed
    if "scheduled_start" in update_fields:
        new_start = update_fields["scheduled_start"]
        # Check if scheduled_end was also provided, otherwise calculate it
        if "scheduled_end" in update_fields:
            new_end = update_fields["scheduled_end"]
        else:
            # Calculate from duration
            duration = appt_data.duration_minutes or appointment.duration_minutes or 30
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

    # Apply all updates
    _protected = {'id', 'organization_id', 'created_at', 'updated_at', 'user_id'}
    audit_changes = {}
    for field, value in update_fields.items():
        if hasattr(appointment, field) and field not in _protected:
            old_val = getattr(appointment, field, None)
            setattr(appointment, field, value)
            # Track changes for audit log (serialize values)
            new_str = value.value if hasattr(value, 'value') else str(value) if value is not None else None
            old_str = old_val.value if hasattr(old_val, 'value') else str(old_val) if old_val is not None else None
            if new_str != old_str:
                audit_changes[field] = {'old': old_str, 'new': new_str}

    action = 'cancelled' if is_cancellation else 'rescheduled' if is_reschedule else 'updated'
    _audit_log(db, org_id, user.id, action, 'appointment',
               entity_id=appointment_id, changes=audit_changes, request=request)
    db.commit()
    db.refresh(appointment)

    # Get updated appointment details for notifications
    attendee_email = appointment.attendee_email
    attendee_name = appointment.attendee_name or 'Valued Client'
    attendee_phone = getattr(appointment, 'attendee_phone', None)
    appointment_title = appointment.title or 'Appointment'
    duration_minutes = appointment.duration_minutes or 30
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
        new_local_start = appointment.scheduled_start.replace(tzinfo=pytz.UTC).astimezone(tz)
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
        # H15: Only send update notifications for material changes (time, attendee, mode, status)
        logger.info(f"Appointment {appointment_id} updated, sending update notifications")

        # Send update email to attendee
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

        # Send update SMS to attendee
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

    return {
        "message": "Appointment updated",
        "appointment_id": appointment_id,
        "emails_sent": emails_sent,
        "sms_sent": sms_sent,
        "is_reschedule": is_reschedule,
        "new_date": new_date,
        "new_time": new_time
    }


@router.post("/appointments/{appointment_id}/cancel")
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

    Appointment = _models['Appointment']
    User = _models['User']

    appointment = db.query(Appointment).filter(
        Appointment.id == appointment_id,
        Appointment.organization_id == org_id,
        or_(
            Appointment.assigned_user_id == user.id,
            Appointment.created_by_user_id == user.id
        )
    ).first()

    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")

    # Store appointment details before cancellation for email notifications
    attendee_email = getattr(appointment, 'attendee_email', None)
    attendee_name = getattr(appointment, 'attendee_name', None) or 'Valued Client'
    appointment_title = appointment.title or 'Appointment'

    # Format date and time for emails
    if appointment.scheduled_start:
        tz = pytz.timezone(_get_user_timezone(db, appointment.assigned_user_id, org_id=org_id))
        local_start = appointment.scheduled_start.replace(tzinfo=pytz.UTC).astimezone(tz)
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
               entity_id=appointment_id, changes={'reason': reason}, request=request)

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

    # H-2: Single atomic commit — cancellation + audit + activity + task
    db.commit()

    logger.info(f"Appointment {appointment_id} cancelled by user {user.id}")

    # Send cancellation emails
    emails_sent = []

    # Send to attendee if they have an email
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

    # Send to assigned team member if different from canceller
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

    return {
        "message": "Appointment cancelled",
        "emails_sent": emails_sent
    }


# ============================================================================
# BOOKING LINK ENDPOINTS
# ============================================================================

@router.get("/booking-links/all")
async def list_all_booking_links(
    request: Request,
    db: Session = Depends(get_db)
):
    """List all active booking links for admin use (calendar assignment)"""
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    # H4: Require admin role to list all org booking links
    user_role = getattr(user, 'permission_role', '') or getattr(user, 'role', '') or ''
    if user_role.lower() not in ('admin', 'leadership', 'management', 'site_admin', 'platform_admin'):
        raise HTTPException(status_code=403, detail="Admin access required to list all booking links")

    BookingLink = _models['BookingLink']
    User = _models.get('User')

    links = db.query(BookingLink).filter(
        BookingLink.is_active == True,
        BookingLink.organization_id == org_id
    ).all()

    # Batch-load owners to avoid N+1 queries
    owner_ids = [link.user_id for link in links if link.user_id]
    owners_map = {}
    if owner_ids and User:
        owners = db.query(User).filter(User.id.in_(owner_ids)).all()
        owners_map = {o.id: getattr(o, 'full_name', f"{o.first_name} {o.last_name}") for o in owners}

    result = []
    for link in links:
        link_data = {
            "id": link.id,
            "slug": link.slug,
            "link_name": link.link_name,
            "description": link.description,
            "url": f"/book/{link.slug}",
            "is_public": link.is_public,
            "user_id": link.user_id,
            "owner_name": owners_map.get(link.user_id) if link.user_id else None,
            "created_at": link.created_at.isoformat() if link.created_at else None
        }
        result.append(link_data)

    return {"booking_links": result}


@router.get("/booking-links")
async def list_booking_links(
    request: Request,
    db: Session = Depends(get_db)
):
    """List user's booking links"""
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    BookingLink = _models['BookingLink']

    links = db.query(BookingLink).filter(
        BookingLink.user_id == user.id,
        BookingLink.organization_id == org_id,
        BookingLink.is_active == True
    ).all()

    return {
        "booking_links": [
            {
                "id": link.id,
                "slug": link.slug,
                "link_name": link.link_name,
                "description": link.description,
                "url": f"/book/{link.slug}",
                "is_public": link.is_public,
                "view_count": link.view_count,
                "booking_count": link.booking_count,
                "last_booked_at": link.last_booked_at.isoformat() if link.last_booked_at else None,
                "created_at": link.created_at.isoformat() if link.created_at else None
            }
            for link in links
        ]
    }


@router.post("/booking-links")
async def create_booking_link(
    link_data: BookingLinkCreate,
    request: Request,
    db: Session = Depends(get_db)
):
    """Create a booking link"""
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    BookingLink = _models['BookingLink']

    # Check for duplicate slug globally — public lookup is cross-org so slugs must be unique
    existing = db.query(BookingLink).filter(
        BookingLink.slug == link_data.slug,
        BookingLink.is_active == True
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="This booking link slug is already in use. Please choose a different one.")

    # Parse routing strategy
    routing_strategy = RoutingStrategy.RELATIONSHIP
    if link_data.routing_strategy:
        try:
            routing_strategy = RoutingStrategy(link_data.routing_strategy)
        except ValueError:
            pass

    link = BookingLink(
        organization_id=org_id,
        user_id=user.id,
        slug=link_data.slug,
        link_name=link_data.link_name,
        description=link_data.description,
        appointment_type_ids=link_data.appointment_type_ids,
        single_appointment_type_id=link_data.single_appointment_type_id,
        is_public=link_data.is_public,
        custom_title=link_data.custom_title,
        custom_description=link_data.custom_description,
        routing_strategy=routing_strategy,
        assigned_users=link_data.assigned_users
    )

    db.add(link)
    _audit_log(db, org_id, user.id, 'created', 'booking_link',
               changes={'slug': link_data.slug, 'link_name': link_data.link_name}, request=request)
    db.commit()
    db.refresh(link)

    return {
        "message": "Booking link created",
        "link_id": link.id,
        "url": f"/book/{link.slug}"
    }


@router.delete("/booking-links/{link_id}")
async def delete_booking_link(
    link_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """Delete a booking link"""
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    BookingLink = _models['BookingLink']

    link = db.query(BookingLink).filter(
        BookingLink.id == link_id,
        BookingLink.organization_id == org_id,
        BookingLink.user_id == user.id
    ).first()

    if not link:
        raise HTTPException(status_code=404, detail="Booking link not found")

    link.is_active = False
    _audit_log(db, org_id, user.id, 'deleted', 'booking_link',
               entity_id=link_id, changes={'slug': link.slug}, request=request)
    db.commit()

    return {"message": "Booking link deactivated"}


# ============================================================================
# SLOT AVAILABILITY & AI RECOMMENDATIONS
# ============================================================================

@router.post("/available-slots")
async def get_available_slots(
    slot_request: AvailableSlotsRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Get available time slots for booking.
    Delegates to the unified _generate_available_slots engine.
    """
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)
    user_ids = slot_request.user_ids if slot_request.user_ids else [user.id]

    available_slots = _generate_available_slots(
        db=db,
        user_ids=user_ids,
        start_date=slot_request.start_date,
        end_date=slot_request.end_date,
        duration_minutes=slot_request.duration_minutes,
        org_id=org_id,
        max_per_day=8,  # Default max per day for authenticated endpoint
        check_cross_source=True,
        include_user_id=True,
        include_day_name=True,
    )

    return {
        "available_slots": available_slots,
        "total_slots": len(available_slots),
        "request": {
            "start_date": slot_request.start_date.isoformat(),
            "end_date": slot_request.end_date.isoformat(),
            "duration_minutes": slot_request.duration_minutes,
            "user_ids": user_ids
        }
    }


@router.post("/ai-recommend-slots")
async def ai_recommend_slots(
    slot_request: AvailableSlotsRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Get AI-recommended time slots based on:
    - User preferences
    - Lead/loan context
    - Historical patterns
    - Optimal meeting times
    """
    user = await get_current_user(request, db)

    # First get available slots
    available_response = await get_available_slots(slot_request, request, db)
    available_slots = available_response.get("available_slots", [])

    if not available_slots:
        return {
            "recommendations": [],
            "message": "No available slots found in the requested range"
        }

    # Score each slot
    recommendations = []

    for slot in available_slots[:20]:  # Limit to first 20 for performance
        score = 1.0
        reasons = []

        # Parse the slot time
        try:
            slot_dt = datetime.fromisoformat(slot["start"])
        except (ValueError, TypeError):
            continue
        hour = slot_dt.hour
        day_name = slot["day"]

        # Score based on time of day (prefer mid-morning and early afternoon)
        if 9 <= hour <= 11:
            score += 0.3
            reasons.append("Optimal morning time slot")
        elif 14 <= hour <= 16:
            score += 0.2
            reasons.append("Good afternoon time slot")
        elif hour < 9 or hour > 17:
            score -= 0.2
            reasons.append("Outside peak hours")

        # Score based on day of week
        if day_name in ["tuesday", "wednesday", "thursday"]:
            score += 0.1
            reasons.append("Mid-week availability")
        elif day_name == "monday":
            score -= 0.1
            reasons.append("Monday may have competing priorities")
        elif day_name == "friday":
            score -= 0.1
            reasons.append("Friday afternoon may have lower engagement")

        # Bonus for sooner availability
        days_from_now = (slot_dt.date() - datetime.now(timezone.utc).date()).days
        if days_from_now <= 2:
            score += 0.2
            reasons.append("Soon availability - strike while hot")
        elif days_from_now > 7:
            score -= 0.1
            reasons.append("Further out - lead may cool")

        recommendations.append({
            "slot": slot,
            "score": round(score, 2),
            "reasons": reasons
        })

    # Sort by score descending
    recommendations.sort(key=lambda x: x["score"], reverse=True)

    return {
        "recommendations": recommendations[:5],  # Top 5
        "total_available": len(available_slots)
    }


# ============================================================================
# NO-SHOW RISK SCORING ENDPOINTS
# ============================================================================

@router.get("/appointments/{appointment_id}/no-show-risk")
async def get_appointment_no_show_risk(
    appointment_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Get predictive no-show risk score for a single appointment.
    Score 0-100 with risk level (low/medium/high) and contributing factors.
    """
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    if _models is None:
        raise HTTPException(status_code=500, detail="Models not initialized")

    Appointment = _models['Appointment']
    from database.enums import AppointmentStatus as _AppointmentStatus

    appointment = db.query(Appointment).filter(
        Appointment.id == appointment_id,
        Appointment.organization_id == org_id
    ).first()

    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")

    risk = _calculate_no_show_risk(appointment, db, Appointment, _AppointmentStatus, org_id)

    return {
        "appointment_id": appointment_id,
        "attendee_name": appointment.attendee_name,
        "attendee_email": appointment.attendee_email,
        "scheduled_start": appointment.scheduled_start.isoformat() if appointment.scheduled_start else None,
        "status": appointment.status.value if appointment.status else None,
        **risk
    }


@router.get("/analytics/no-show-risks")
async def get_batch_no_show_risks(
    request: Request,
    target_date: date = Query(..., alias="date", description="Date to score (YYYY-MM-DD)"),
    db: Session = Depends(get_db)
):
    """
    Get no-show risk scores for all appointments on a given date.
    Returns a list sorted by risk score descending (highest risk first).
    """
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    if _models is None:
        raise HTTPException(status_code=500, detail="Models not initialized")

    Appointment = _models['Appointment']
    from database.enums import AppointmentStatus as _AppointmentStatus

    start_dt = datetime.combine(target_date, time.min)
    end_dt = datetime.combine(target_date, time.max)

    appointments = db.query(Appointment).filter(
        Appointment.organization_id == org_id,
        Appointment.scheduled_start >= start_dt,
        Appointment.scheduled_start <= end_dt,
        Appointment.status.notin_([_AppointmentStatus.CANCELLED])
    ).order_by(Appointment.scheduled_start).all()

    results = []
    for appt in appointments:
        risk = _calculate_no_show_risk(appt, db, Appointment, _AppointmentStatus, org_id)
        results.append({
            "appointment_id": appt.id,
            "title": appt.title,
            "attendee_name": appt.attendee_name,
            "attendee_email": appt.attendee_email,
            "scheduled_start": appt.scheduled_start.isoformat() if appt.scheduled_start else None,
            "status": appt.status.value if appt.status else None,
            "meeting_type": appt.meeting_type.value if appt.meeting_type else None,
            **risk
        })

    # Sort by score descending (highest risk first)
    results.sort(key=lambda r: r["score"], reverse=True)

    # Summary counts
    high_risk = len([r for r in results if r["risk_level"] == "high"])
    medium_risk = len([r for r in results if r["risk_level"] == "medium"])
    low_risk = len([r for r in results if r["risk_level"] == "low"])

    return {
        "date": target_date.isoformat(),
        "total_appointments": len(results),
        "risk_summary": {
            "high": high_risk,
            "medium": medium_risk,
            "low": low_risk
        },
        "avg_risk_score": round(sum(r["score"] for r in results) / len(results), 1) if results else 0,
        "appointments": results
    }
