"""
Scheduler Appointment Routes
Extracted from smart_scheduler_routes.py

Endpoints:
- GET/POST /email-service-status, /test-email
- GET/POST/DELETE /availability
- GET/POST/PUT /appointments, POST /appointments/{id}/cancel
- GET/POST/DELETE /blocked-times
- GET/POST/DELETE /booking-links
- POST /available-slots
- POST /ai-recommend-slots
- GET /public/book/{slug}, GET /public/book/{slug}/slots, POST /public/book/{slug}/confirm
- POST /public/available-slots, POST /public/book-demo/confirm
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from datetime import datetime, timedelta, date, time, timezone
from typing import List, Optional
from pydantic import BaseModel, EmailStr
import html
import logging
import pytz
import os
import uuid as uuid_lib

try:
    import nh3
except ImportError:
    nh3 = None

from smart_scheduler_models import (
    AppointmentStatus, MeetingType, MeetingMode, RoutingStrategy,
    DayOfWeek, SlotPriority, DEFAULT_WORKING_HOURS
)
from scheduler_models import (
    AvailabilitySlotCreate, AppointmentCreate, AppointmentUpdate,
    BlockedTimeCreate, BookingLinkCreate, AvailableSlotsRequest,
    PublicBookingConfirmRequest, PublicAvailableSlotsRequest,
    CancelAppointmentRequest, WebsiteDemoBookingRequest
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
    send_with_sms_fallback,
    send_appointment_reminder_email,
    send_appointment_reminder_sms,
)
from services.notification_service import notification_service
from services.microsoft_graph import create_event_via_graph, CalendarResult

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================================
# CROSS-SOURCE CONFLICT HELPERS
# ============================================================================

def _get_cross_source_conflicts(db, target_user_id: int, start_dt, end_dt, org_id=None):
    """
    Gather all busy time blocks from all 3 calendar sources for a user.
    Returns a list of (start, end) tuples representing occupied time.
    """
    conflicts = []

    # Source 1: ScheduledAppointment (AI-booked appointments)
    try:
        from services.smart_scheduler_service import ScheduledAppointment as SAModel
        sa_query = db.query(SAModel).filter(
            SAModel.loan_officer_id == target_user_id,
            SAModel.status.in_(["scheduled", "confirmed"]),
            SAModel.start_time >= start_dt,
            SAModel.start_time <= end_dt
        )
        if org_id:
            sa_query = sa_query.filter(SAModel.organization_id == org_id)
        sa_appts = sa_query.all()
        for a in sa_appts:
            if a.start_time and a.end_time:
                conflicts.append((a.start_time, a.end_time))
    except Exception as e:
        logger.warning(f"ScheduledAppointment cross-source check unavailable: {e}")

    # Source 2: CalendarEvent (manual calendar entries)
    try:
        import main
        CalendarEvent = main.CalendarEvent
        cal_query = db.query(CalendarEvent).filter(
            CalendarEvent.user_id == target_user_id,
            CalendarEvent.status != "cancelled",
            CalendarEvent.start_time >= start_dt,
            CalendarEvent.start_time <= end_dt
        )
        if org_id:
            cal_query = cal_query.filter(CalendarEvent.organization_id == org_id)
        cal_events = cal_query.all()
        for e in cal_events:
            if e.start_time and e.end_time:
                conflicts.append((e.start_time, e.end_time))
    except Exception as ex:
        logger.warning(f"CalendarEvent cross-source check unavailable: {ex}")

    # Source 3: CRMCalendarEvent (Salesforce-synced events)
    try:
        from models.calendar_sync_models import CRMCalendarEvent
        crm_query = db.query(CRMCalendarEvent).filter(
            CRMCalendarEvent.owner_user_id == target_user_id,
            CRMCalendarEvent.status != "canceled",
            CRMCalendarEvent.start_at >= start_dt,
            CRMCalendarEvent.start_at <= end_dt
        )
        if org_id:
            crm_query = crm_query.filter(CRMCalendarEvent.organization_id == org_id)
        crm_events = crm_query.all()
        for e in crm_events:
            if e.start_at and e.end_at:
                conflicts.append((e.start_at, e.end_at))
    except Exception as ex:
        logger.warning(f"CRMCalendarEvent cross-source check unavailable: {ex}")

    return conflicts


def _has_cross_source_conflict(conflicts, slot_start, slot_end, buffer_before=0, buffer_after=0):
    """Check if a proposed slot conflicts with any cross-source busy time."""
    for busy_start, busy_end in conflicts:
        buffered_start = busy_start - timedelta(minutes=buffer_before)
        buffered_end = busy_end + timedelta(minutes=buffer_after)
        if slot_start < buffered_end and slot_end > buffered_start:
            return True
    return False

# ============================================================================
# DEPENDENCY INJECTION STORAGE
# ============================================================================

_get_db = None
_get_current_user_func = None
_models = None


def set_dependencies(get_db_func, get_current_user_func, models_dict):
    """Set dependencies from parent module"""
    global _get_db, _get_current_user_func, _models
    _get_db = get_db_func
    _get_current_user_func = get_current_user_func
    _models = models_dict


def get_db():
    if _get_db is None:
        raise RuntimeError("Dependencies not set")
    yield from _get_db()


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


def _get_user_timezone(db, user_id: int) -> str:
    """Get user's configured timezone from SchedulerConfig, defaulting to America/Chicago."""
    SchedulerConfig = _models.get('SchedulerConfig')
    if SchedulerConfig and user_id:
        config = db.query(SchedulerConfig).filter(SchedulerConfig.user_id == user_id).first()
        if config and getattr(config, 'timezone', None):
            return config.timezone
    return 'America/Chicago'


# ============================================================================
# RATE LIMITING (Redis-backed, multi-process safe)
# ============================================================================

_RATE_LIMIT_WINDOW = 60  # seconds
_RATE_LIMIT_MAX_PUBLIC = 10  # max requests per window for public endpoints

# Lazy Redis connection for rate limiting
_rate_limit_redis = None
_rate_limit_redis_checked = False


def _get_rate_limit_redis():
    """Get or create Redis connection for rate limiting. Returns None if unavailable."""
    global _rate_limit_redis, _rate_limit_redis_checked
    if _rate_limit_redis_checked:
        return _rate_limit_redis
    _rate_limit_redis_checked = True
    try:
        import redis as redis_lib
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        _rate_limit_redis = redis_lib.Redis.from_url(
            redis_url, decode_responses=True, socket_connect_timeout=2
        )
        _rate_limit_redis.ping()
        logger.info("Scheduler rate limiter connected to Redis")
    except Exception as e:
        logger.warning(f"Redis unavailable for scheduler rate limiting: {e}")
        _rate_limit_redis = None
    return _rate_limit_redis


# R4: In-memory rate limiter fallback when Redis is unavailable
import time as _time
from collections import defaultdict, deque
import threading

_memory_rate_limits = defaultdict(deque)  # key -> deque of timestamps
_memory_rate_lock = threading.Lock()


def _check_memory_rate_limit(key: str, max_requests: int, window_seconds: int = _RATE_LIMIT_WINDOW) -> bool:
    """
    In-memory sliding window rate limit. Returns True if allowed, False if over limit.
    Thread-safe via lock. Not multi-process safe (single worker protection only).
    """
    now = _time.time()
    with _memory_rate_lock:
        timestamps = _memory_rate_limits[key]
        # Evict expired timestamps
        while timestamps and timestamps[0] < now - window_seconds:
            timestamps.popleft()
        if len(timestamps) >= max_requests:
            return False
        timestamps.append(now)
        return True


def _check_rate_limit(request: Request, max_requests: int = _RATE_LIMIT_MAX_PUBLIC):
    """
    Redis-backed rate limiter keyed by client IP + path.
    Falls back to in-memory rate limiting if Redis is unavailable.
    """
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()
    else:
        client_ip = request.client.host if request.client else "unknown"

    key = f"sched_rl:{request.url.path}:{client_ip}"

    r = _get_rate_limit_redis()
    if r is None:
        # Fallback: in-memory rate limiting instead of allowing all
        if not _check_memory_rate_limit(key, max_requests):
            raise HTTPException(
                status_code=429,
                detail="Too many requests. Please try again later.",
                headers={"Retry-After": str(_RATE_LIMIT_WINDOW)}
            )
        return

    try:
        current = r.incr(key)
        if current == 1:
            r.expire(key, _RATE_LIMIT_WINDOW)
        if current > max_requests:
            ttl = r.ttl(key)
            raise HTTPException(
                status_code=429,
                detail="Too many requests. Please try again later.",
                headers={"Retry-After": str(max(ttl, 1))}
            )
    except HTTPException:
        raise
    except Exception as e:
        # Redis command error — fall back to in-memory
        logger.warning(f"Rate limit Redis error, using memory fallback: {e}")
        if not _check_memory_rate_limit(key, max_requests):
            raise HTTPException(
                status_code=429,
                detail="Too many requests. Please try again later.",
                headers={"Retry-After": str(_RATE_LIMIT_WINDOW)}
            )


def _sanitize_text(value: Optional[str]) -> Optional[str]:
    """Sanitize user-supplied text input, stripping all HTML."""
    if value is None:
        return None
    if nh3:
        return nh3.clean(value, tags=set())
    # Fallback: html.escape
    return html.escape(value)


def _mask_email(email: Optional[str]) -> str:
    """Mask email for logging: j***@example.com"""
    if not email or '@' not in email:
        return '***'
    local, domain = email.split('@', 1)
    return f"{local[0]}***@{domain}" if local else f"***@{domain}"


def _validate_url(value: Optional[str]) -> Optional[str]:
    """Validate URL has safe scheme (http/https only). Returns None for unsafe URLs."""
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    from urllib.parse import urlparse
    try:
        parsed = urlparse(value)
        if parsed.scheme not in ('http', 'https'):
            logger.warning(f"Rejected URL with unsafe scheme: {parsed.scheme}")
            return None
        return value
    except Exception:
        return None


def _audit_log(db, org_id: int, user_id: int, action: str, entity_type: str,
               entity_id: int = None, changes: dict = None, request: Request = None):
    """Record an audit log entry for scheduler operations."""
    AuditLog = _models.get('SchedulerAuditLog')
    if not AuditLog:
        return
    try:
        entry = AuditLog(
            organization_id=org_id,
            user_id=user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            changes=changes,
            ip_address=request.client.host if request and request.client else None,
            user_agent=str(request.headers.get('user-agent', ''))[:255] if request else None,
        )
        db.add(entry)
        # Don't commit here — let the caller's commit include this
    except Exception as e:
        logger.warning(f"Failed to write audit log: {e}")


def _check_appointment_conflict(db, assigned_user_id: int, start_time, end_time, org_id=None, exclude_appointment_id=None):
    """
    Check for overlapping appointments using SELECT FOR UPDATE to prevent double-booking.
    Raises HTTPException 409 if a conflict is found or rows are locked by another transaction.
    exclude_appointment_id: skip this appointment (used when rescheduling to avoid self-conflict).
    """
    from sqlalchemy.exc import OperationalError
    Appointment = _models['Appointment']
    filters = [
        Appointment.assigned_user_id == assigned_user_id,
        Appointment.status.notin_([AppointmentStatus.CANCELLED.value, 'no_show', 'cancelled']),
        Appointment.scheduled_start < end_time,
        Appointment.scheduled_end > start_time,
    ]
    if org_id is not None:
        filters.append(Appointment.organization_id == org_id)
    if exclude_appointment_id is not None:
        filters.append(Appointment.id != exclude_appointment_id)

    try:
        conflict = db.query(Appointment).filter(and_(*filters)).with_for_update(nowait=True).first()
    except OperationalError:
        # Row is locked by another transaction — treat as conflict
        raise HTTPException(
            status_code=409,
            detail="This time slot is being booked by another user. Please select a different time."
        )
    if conflict:
        raise HTTPException(
            status_code=409,
            detail="This time slot is no longer available. Please select a different time."
        )


# C2: Duplicate booking detection
def _check_duplicate_booking(db, attendee_email: str, assigned_user_id: int,
                              start_time, org_id=None, window_minutes=30):
    """
    Check for an existing booking with the same attendee_email + same LO
    within ±window_minutes of the proposed start_time.
    Raises HTTPException 409 if a duplicate is found.
    """
    if not attendee_email:
        return  # No email to check against

    Appointment = _models['Appointment']
    window_start = start_time - timedelta(minutes=window_minutes)
    window_end = start_time + timedelta(minutes=window_minutes)

    filters = [
        Appointment.attendee_email == attendee_email,
        Appointment.assigned_user_id == assigned_user_id,
        Appointment.status.notin_([AppointmentStatus.CANCELLED.value, 'cancelled']),
        Appointment.scheduled_start >= window_start,
        Appointment.scheduled_start <= window_end,
    ]
    if org_id is not None:
        filters.append(Appointment.organization_id == org_id)

    duplicate = db.query(Appointment).filter(and_(*filters)).first()
    if duplicate:
        raise HTTPException(
            status_code=409,
            detail=f"A booking for this email already exists at this time. "
                   f"Existing appointment ID: {duplicate.id}"
        )


# ============================================================================
# CRM INTEGRATION HELPERS (Module 2 + Module 8)
# ============================================================================

def _log_appointment_activity(db, org_id: int, user_id: int, lead_id: int,
                               loan_id: int, content: str,
                               activity_type: str = "Meeting"):
    """Log an appointment-related activity to the CRM Activity table."""
    try:
        from database.models.communication import Activity
        from database.enums import ActivityType

        type_map = {
            "Meeting": ActivityType.MEETING,
            "Note": ActivityType.NOTE,
            "Email": ActivityType.EMAIL,
        }

        activity = Activity(
            organization_id=org_id,
            type=type_map.get(activity_type, ActivityType.MEETING),
            content=content[:2000],  # Truncate to safe length
            lead_id=lead_id,
            loan_id=loan_id,
            user_id=user_id,
        )
        db.add(activity)
        logger.debug(f"Activity logged: {content[:80]}")
    except ImportError:
        logger.debug("Activity model not available, skipping activity log")
    except Exception as e:
        logger.error(f"Failed to log appointment activity: {e}")


def _ensure_lead_for_booking(db, attendee_email: str, attendee_name: str,
                              attendee_phone: str, assigned_user_id: int,
                              org_id: int) -> Optional[int]:
    """
    Find or create a Lead record for a booking attendee.
    Dedup: Match on email + organization_id. Returns lead_id or None.
    """
    if not attendee_email:
        return None

    try:
        from database.models.lead_loan import Lead
    except ImportError:
        logger.debug("Lead model not available, skipping lead creation")
        return None

    try:
        existing = db.query(Lead).filter(
            Lead.email == attendee_email,
            Lead.organization_id == org_id
        ).first()

        if existing:
            existing.last_contact = datetime.now(timezone.utc)
            logger.info(f"Linked booking to existing lead {existing.id} ({_mask_email(attendee_email)})")
            return existing.id

        # Parse name into first/last
        name_parts = (attendee_name or "").strip().split(None, 1)
        first_name = name_parts[0] if name_parts else ""
        last_name = name_parts[1] if len(name_parts) > 1 else ""

        new_lead = Lead(
            organization_id=org_id,
            name=attendee_name or attendee_email,
            first_name=first_name,
            last_name=last_name,
            email=attendee_email,
            phone=attendee_phone,
            stage="New",
            source="scheduler",
            owner_id=assigned_user_id,
            last_contact=datetime.now(timezone.utc),
            lead_received_date=datetime.now(timezone.utc),
        )
        db.add(new_lead)
        db.flush()  # Get the ID without committing

        logger.info(f"Created new lead {new_lead.id} from booking ({_mask_email(attendee_email)})")
        return new_lead.id

    except Exception as e:
        logger.error(f"Failed to ensure lead for booking: {e}")
        return None


def _create_followup_task(db, org_id: int, owner_id: int, lead_id: int,
                           loan_id: int, title: str, description: str,
                           due_date, priority: str = "medium"):
    """Create a follow-up task linked to a lead/loan."""
    try:
        from database.models.task import Task

        task = Task(
            organization_id=org_id,
            title=title[:255],
            description=description[:2000],
            status="pending",
            priority=priority,
            due_date=due_date,
            owner_id=owner_id,
            lead_id=lead_id,
            loan_id=loan_id,
        )
        db.add(task)
        logger.info(f"Follow-up task created: {title[:80]}")
    except ImportError:
        logger.debug("Task model not available, skipping task creation")
    except Exception as e:
        logger.error(f"Failed to create follow-up task: {e}")


def _create_comm_failure_task(db, org_id: int, assigned_user_id: int,
                               attendee_name: str, error_msg: str):
    """R5: Create a high-priority task when all communication channels fail."""
    try:
        from database.models.task import Task
        task = Task(
            organization_id=org_id,
            title=f"Communication failure: {attendee_name or 'Client'}"[:255],
            description=f"All email/SMS attempts failed. Manual follow-up required.\nError: {error_msg}"[:2000],
            priority="high",
            status="pending",
            owner_id=assigned_user_id,
            due_date=datetime.now(timezone.utc) + timedelta(hours=4),
        )
        db.add(task)
        db.commit()
        logger.info(f"Created communication failure escalation task for {attendee_name}")
    except Exception as e:
        logger.error(f"Failed to create escalation task: {e}")


def _check_lo_licensing(db, assigned_user_id: int, attendee_state: str) -> Optional[str]:
    """
    C3: Soft check — verify LO has NMLS number on file.
    Returns a warning string if concern, None if OK. Advisory only.
    """
    if not attendee_state:
        return None

    try:
        from database.models.core import User
        assigned = db.query(User).filter(User.id == assigned_user_id).first()
        if not assigned:
            return f"Warning: Could not verify LO licensing - user {assigned_user_id} not found"

        nmls = getattr(assigned, 'nmls_number', None)
        if not nmls:
            name = f"{getattr(assigned, 'first_name', '')} {getattr(assigned, 'last_name', '')}".strip()
            return (f"Warning: LO {name} has no NMLS number on file. "
                    f"Cannot verify licensing for state {attendee_state}.")

        logger.info(f"LO licensing check: NMLS#{nmls} for state {attendee_state}")
        return None
    except ImportError:
        return None
    except Exception as e:
        logger.warning(f"LO licensing check failed: {e}")
        return None


# ============================================================================
# EMAIL SERVICE STATUS ENDPOINT
# ============================================================================

@router.get("/email-service-status")
async def get_email_service_status(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Check if email service is properly configured (authenticated)"""
    sendgrid_configured = bool(os.getenv("SENDGRID_API_KEY"))
    sendgrid_from_email = os.getenv("SENDGRID_FROM_EMAIL", "sarah@reply.perenniaai.com")

    return {
        "sendgrid_configured": sendgrid_configured,
        "from_email": sendgrid_from_email,
        "status": "ready" if sendgrid_configured else "not_configured",
        "message": "Email service is ready to send" if sendgrid_configured else "SendGrid API key not configured - emails will be logged only (dry run)"
    }


@router.post("/test-email")
async def test_email_send(
    to_email: str = Query(..., description="Email address to send test to"),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Test endpoint to send a test email (authenticated, admin-only)"""
    # Require admin role
    user_role = getattr(current_user, 'role', None)
    if user_role not in ('admin', 'platform_admin', 'site_admin'):
        raise HTTPException(status_code=403, detail="Admin access required")

    try:
        time_sent = datetime.now(timezone.utc).isoformat()
        result = notification_service.send_email(
            to_email=to_email,
            subject="Test Email from Perennia CRM",
            html_content=f"""
            <html>
            <body style="font-family: Arial, sans-serif; padding: 20px;">
                <h2>Test Email</h2>
                <p>This is a test email from Perennia CRM to verify SendGrid is working.</p>
                <p>Time sent: {html.escape(time_sent)}</p>
            </body>
            </html>
            """,
            plain_content=f"Test email from Perennia CRM. Time: {time_sent}"
        )

        return {
            "test_result": result,
            "to_email": to_email,
            "from_email": os.getenv("SENDGRID_FROM_EMAIL", "sarah@reply.perenniaai.com"),
            "sendgrid_key_present": bool(os.getenv("SENDGRID_API_KEY")),
        }
    except Exception as e:
        logger.exception(f"Test email failed: {e}")
        return {
            "test_result": {"success": False, "error": "Email send failed"},
            "to_email": to_email
        }


# ============================================================================
# AVAILABILITY ENDPOINTS
# ============================================================================

@router.get("/availability")
async def get_availability(
    request: Request,
    start_date: date = Query(...),
    end_date: date = Query(...),
    user_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Get availability slots for a date range"""
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    SchedulerConfig = _models['SchedulerConfig']
    AvailabilitySlot = _models['AvailabilitySlot']
    BlockedTime = _models['BlockedTime']
    Appointment = _models['Appointment']

    target_user_id = user_id or user.id

    # S1: Validate target user belongs to same organization (prevent cross-tenant IDOR)
    if user_id and user_id != user.id:
        User = _models.get('User')
        if User:
            target_user = db.query(User).filter(
                User.id == user_id,
                User.organization_id == org_id
            ).first()
            if not target_user:
                raise HTTPException(status_code=403, detail="User not found in your organization")

    # Get config
    config = db.query(SchedulerConfig).filter(
        SchedulerConfig.user_id == target_user_id,
        SchedulerConfig.organization_id == org_id
    ).first()

    if not config:
        # Return default working hours
        return {
            "availability": [],
            "working_hours": DEFAULT_WORKING_HOURS,
            "blocked_times": [],
            "existing_appointments": []
        }

    # Get custom availability slots
    slots = db.query(AvailabilitySlot).filter(
        AvailabilitySlot.config_id == config.id,
        AvailabilitySlot.is_active == True,
        or_(
            AvailabilitySlot.is_recurring == True,
            and_(
                AvailabilitySlot.specific_date >= start_date,
                AvailabilitySlot.specific_date <= end_date
            )
        )
    ).all()

    # Get blocked times
    start_dt = datetime.combine(start_date, time.min)
    end_dt = datetime.combine(end_date, time.max)

    blocked = db.query(BlockedTime).filter(
        BlockedTime.is_active == True,
        BlockedTime.organization_id == org_id,
        or_(
            BlockedTime.user_id == target_user_id,
            and_(BlockedTime.applies_to_all_users == True, BlockedTime.organization_id == org_id)
        ),
        BlockedTime.start_datetime <= end_dt,
        BlockedTime.end_datetime >= start_dt
    ).all()

    # Get existing appointments
    appointments = db.query(Appointment).filter(
        Appointment.organization_id == org_id,
        Appointment.assigned_user_id == target_user_id,
        Appointment.status.in_([AppointmentStatus.BOOKED, AppointmentStatus.TENTATIVE]),
        Appointment.scheduled_start >= start_dt,
        Appointment.scheduled_start <= end_dt
    ).all()

    return {
        "availability": [
            {
                "id": s.id,
                "day_of_week": s.day_of_week.value if s.day_of_week else None,
                "specific_date": s.specific_date.isoformat() if s.specific_date else None,
                "start_time": s.start_time.strftime("%H:%M"),
                "end_time": s.end_time.strftime("%H:%M"),
                "priority": s.priority.value if s.priority else "standard",
                "is_recurring": s.is_recurring
            }
            for s in slots
        ],
        "working_hours": config.working_hours or DEFAULT_WORKING_HOURS,
        "blocked_times": [
            {
                "id": b.id,
                "title": b.title,
                "start": b.start_datetime.isoformat(),
                "end": b.end_datetime.isoformat(),
                "all_day": b.all_day,
                "block_type": b.block_type
            }
            for b in blocked
        ],
        "existing_appointments": [
            {
                "id": a.id,
                "title": a.title,
                "start": a.scheduled_start.isoformat(),
                "end": a.scheduled_end.isoformat(),
                "status": a.status.value if a.status else "booked"
            }
            for a in appointments
        ]
    }


@router.post("/availability/slots")
async def create_availability_slot(
    slot_data: AvailabilitySlotCreate,
    request: Request,
    db: Session = Depends(get_db)
):
    """Create a custom availability slot"""
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    SchedulerConfig = _models['SchedulerConfig']
    AvailabilitySlot = _models['AvailabilitySlot']

    config = db.query(SchedulerConfig).filter(
        SchedulerConfig.user_id == user.id,
        SchedulerConfig.organization_id == org_id
    ).first()

    if not config:
        raise HTTPException(status_code=400, detail="Please create scheduler config first")

    # Parse times
    try:
        start_time_parsed = datetime.strptime(slot_data.start_time, "%H:%M").time()
        end_time_parsed = datetime.strptime(slot_data.end_time, "%H:%M").time()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid time format. Use HH:MM")

    # Parse day of week
    day_of_week = None
    if slot_data.day_of_week:
        try:
            day_of_week = DayOfWeek(slot_data.day_of_week.lower())
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid day of week")

    # Parse priority
    priority = SlotPriority.STANDARD
    if slot_data.priority:
        try:
            priority = SlotPriority(slot_data.priority.lower())
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid priority: {slot_data.priority}")

    # Validate max_bookings
    if slot_data.max_bookings is not None and slot_data.max_bookings < 1:
        raise HTTPException(status_code=400, detail="max_bookings must be at least 1")

    slot = AvailabilitySlot(
        organization_id=org_id,
        config_id=config.id,
        user_id=user.id,
        day_of_week=day_of_week,
        specific_date=slot_data.specific_date,
        start_time=start_time_parsed,
        end_time=end_time_parsed,
        priority=priority,
        is_recurring=slot_data.is_recurring,
        allowed_meeting_types=slot_data.allowed_meeting_types,
        max_bookings=max(1, slot_data.max_bookings or 1)
    )

    db.add(slot)
    db.commit()
    db.refresh(slot)

    return {"message": "Availability slot created", "slot_id": slot.id}


@router.delete("/availability/slots/{slot_id}")
async def delete_availability_slot(
    slot_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """Delete an availability slot"""
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    AvailabilitySlot = _models['AvailabilitySlot']

    slot = db.query(AvailabilitySlot).filter(
        AvailabilitySlot.id == slot_id,
        AvailabilitySlot.user_id == user.id,
        AvailabilitySlot.organization_id == org_id
    ).first()

    if not slot:
        raise HTTPException(status_code=404, detail="Slot not found")

    db.delete(slot)
    db.commit()

    return {"message": "Slot deleted"}


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

    # Also query ScheduledAppointment table (AI-booked appointments)
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

        ai_appointments = ai_query.order_by(ScheduledAppointment.start_time.desc()).limit(limit).all()

        # Convert AI appointments to same response format
        for a in ai_appointments:
            result_appointments.append({
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
        logger.warning(f"Could not fetch ScheduledAppointments: {e}")

    # Sort combined results by scheduled_start
    result_appointments.sort(
        key=lambda x: x.get('scheduled_start') or x.get('start_time') or '',
        reverse=True
    )

    total = len(result_appointments)

    return {
        "appointments": result_appointments,
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
    db.commit()
    db.refresh(appointment)
    # Backfill entity_id now that we have it
    _audit_log(db, org_id, user.id, '_id_backfill', 'appointment', entity_id=appointment.id)
    db.commit()

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

    db.commit()

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
                    if not team_result:
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
                db.commit()
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
    user_role = getattr(user, 'permission_role', '') or getattr(user, 'role', '') or ''
    is_admin = user_role.lower() in ['admin', 'leadership', 'management', 'site_admin', 'platform_admin']
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
    tz = pytz.timezone(_get_user_timezone(db, appointment.assigned_user_id))
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
                success = send_appointment_cancellation_email(
                    attendee_email=attendee_email,
                    attendee_name=attendee_name,
                    appointment_title=appointment_title,
                    appointment_date=old_date or new_date,
                    appointment_time=old_time or new_time,
                    team_member_name=team_member_name,
                    cancellation_reason=None
                )
                if success:
                    emails_sent.append(attendee_email)
            except Exception as e:
                logger.error(f"Failed to send attendee cancellation email: {e}")

        if team_member_email and team_member and team_member.id != user.id:
            try:
                success = send_team_member_cancellation_email(
                    team_member_email=team_member_email,
                    team_member_name=team_member_name,
                    attendee_name=attendee_name,
                    appointment_title=appointment_title,
                    appointment_date=old_date or new_date,
                    appointment_time=old_time or new_time,
                    cancellation_reason=None,
                    cancelled_by=user.full_name or user.email
                )
                if success:
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
                success = send_appointment_update_sms(
                    attendee_phone=attendee_phone,
                    attendee_name=attendee_name,
                    appointment_date=new_date,
                    appointment_time=new_time,
                    team_member_name=team_member_name
                )
                if success:
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
        tz = pytz.timezone(_get_user_timezone(db, appointment.assigned_user_id))
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
    db.commit()

    logger.info(f"Appointment {appointment_id} cancelled by user {user.id}")

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
    db.commit()

    # Send cancellation emails
    emails_sent = []

    # Send to attendee if they have an email
    if attendee_email:
        try:
            success = send_appointment_cancellation_email(
                attendee_email=attendee_email,
                attendee_name=attendee_name,
                appointment_title=appointment_title,
                appointment_date=appointment_date,
                appointment_time=appointment_time,
                team_member_name=team_member_name,
                cancellation_reason=reason
            )
            if success:
                emails_sent.append(attendee_email)
        except Exception as e:
            logger.error(f"Failed to send attendee cancellation email: {e}")

    # Send to assigned team member if different from canceller
    if team_member_email and team_member and team_member.id != user.id:
        try:
            success = send_team_member_cancellation_email(
                team_member_email=team_member_email,
                team_member_name=team_member_name,
                attendee_name=attendee_name,
                appointment_title=appointment_title,
                appointment_date=appointment_date,
                appointment_time=appointment_time,
                cancellation_reason=reason,
                cancelled_by=user.full_name or user.email
            )
            if success:
                emails_sent.append(team_member_email)
        except Exception as e:
            logger.error(f"Failed to send team member cancellation email: {e}")

    return {
        "message": "Appointment cancelled",
        "emails_sent": emails_sent
    }


# ============================================================================
# BLOCKED TIME ENDPOINTS
# ============================================================================

@router.get("/blocked-times")
async def list_blocked_times(
    request: Request,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    db: Session = Depends(get_db)
):
    """List blocked time periods"""
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    BlockedTime = _models['BlockedTime']

    query = db.query(BlockedTime).filter(
        BlockedTime.is_active == True,
        BlockedTime.organization_id == org_id,
        or_(
            BlockedTime.user_id == user.id,
            and_(BlockedTime.applies_to_all_users == True, BlockedTime.organization_id == org_id)
        )
    )

    if start_date:
        query = query.filter(BlockedTime.end_datetime >= datetime.combine(start_date, time.min))

    if end_date:
        query = query.filter(BlockedTime.start_datetime <= datetime.combine(end_date, time.max))

    blocked = query.order_by(BlockedTime.start_datetime).all()

    return {
        "blocked_times": [
            {
                "id": b.id,
                "title": b.title,
                "description": b.description,
                "block_type": b.block_type,
                "start_datetime": b.start_datetime.isoformat(),
                "end_datetime": b.end_datetime.isoformat(),
                "all_day": b.all_day,
                "is_recurring": b.is_recurring,
                "recurrence_pattern": b.recurrence_pattern,
                "applies_to_all_users": b.applies_to_all_users
            }
            for b in blocked
        ]
    }


@router.post("/blocked-times")
async def create_blocked_time(
    block_data: BlockedTimeCreate,
    request: Request,
    db: Session = Depends(get_db)
):
    """Create a blocked time period"""
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    BlockedTime = _models['BlockedTime']

    # H1: Only admins can set applies_to_all_users
    applies_to_all = False
    if block_data.applies_to_all_users:
        user_role = getattr(user, 'permission_role', '') or getattr(user, 'role', '') or ''
        if user_role.lower() in ('admin', 'leadership', 'management', 'site_admin', 'platform_admin'):
            applies_to_all = True
        else:
            raise HTTPException(status_code=403, detail="Only admins can block time for all users")

    blocked = BlockedTime(
        organization_id=org_id,
        user_id=user.id,
        title=block_data.title,
        description=block_data.description,
        block_type=block_data.block_type,
        start_datetime=block_data.start_datetime,
        end_datetime=block_data.end_datetime,
        all_day=block_data.all_day,
        is_recurring=block_data.is_recurring,
        recurrence_pattern=block_data.recurrence_pattern,
        applies_to_all_users=applies_to_all,
        created_by_id=user.id
    )

    db.add(blocked)
    _audit_log(db, org_id, user.id, 'created', 'blocked_time',
               changes={'title': block_data.title, 'applies_to_all': applies_to_all}, request=request)
    db.commit()
    db.refresh(blocked)

    return {"message": "Blocked time created", "blocked_time_id": blocked.id}


@router.delete("/blocked-times/{block_id}")
async def delete_blocked_time(
    block_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """Delete a blocked time period"""
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    BlockedTime = _models['BlockedTime']

    blocked = db.query(BlockedTime).filter(
        BlockedTime.id == block_id,
        BlockedTime.organization_id == org_id,
        BlockedTime.user_id == user.id
    ).first()

    if not blocked:
        raise HTTPException(status_code=404, detail="Blocked time not found")

    _audit_log(db, org_id, user.id, 'deleted', 'blocked_time',
               entity_id=block_id, changes={'title': blocked.title}, request=request)
    db.delete(blocked)
    db.commit()

    return {"message": "Blocked time deleted"}


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
# UNIFIED SLOT GENERATION ENGINE
# ============================================================================

def _generate_available_slots(
    db: Session,
    user_ids: list,
    start_date: date,
    end_date: date,
    duration_minutes: int = 30,
    org_id: int = None,
    max_per_day: int = None,
    check_cross_source: bool = True,
    include_user_id: bool = False,
    include_day_name: bool = False,
    time_key_format: str = "start",  # "start"→{start,end} or "start_time"→{start_time,end_time}
) -> list:
    """
    Unified slot generator used by all availability endpoints.

    Computes available time slots for one or more users by checking:
    - Working hours from SchedulerConfig
    - Blocked times
    - Existing appointments (with buffers)
    - Cross-source calendar conflicts (if enabled)
    - Lunch break (if configured)
    - Minimum notice period
    - Max meetings per day (if set)

    Returns a sorted list of slot dicts. Key names controlled by params:
      time_key_format="start"      → {"start": ..., "end": ...}
      time_key_format="start_time" → {"start_time": ...Z, "end_time": ...Z}
    """
    SchedulerConfig = _models.get('SchedulerConfig')
    BlockedTime = _models.get('BlockedTime')
    Appointment = _models.get('Appointment')

    if not SchedulerConfig or not BlockedTime or not Appointment:
        logger.error("Scheduler models not available for slot generation")
        return []

    # Validate date range
    if start_date > end_date:
        raise HTTPException(status_code=400, detail="start_date must be before or equal to end_date")
    if (end_date - start_date).days > 90:
        raise HTTPException(status_code=400, detail="Date range cannot exceed 90 days")

    now = datetime.now(timezone.utc).replace(tzinfo=None)  # naive UTC — consistent with datetime.combine() outputs
    all_slots = []

    for user_id in user_ids:
        # Load user config
        config_query = db.query(SchedulerConfig).filter(
            SchedulerConfig.user_id == user_id
        )
        if org_id:
            config_query = config_query.filter(SchedulerConfig.organization_id == org_id)
        config = config_query.first()

        working_hours = config.working_hours if config else DEFAULT_WORKING_HOURS
        buffer_before = config.buffer_before_minutes if config else 5
        buffer_after = config.buffer_after_minutes if config else 5
        min_notice = config.min_notice_hours if config else 2
        user_max_per_day = max_per_day or (config.max_meetings_per_day if config else None)
        enforce_lunch = getattr(config, 'enforce_lunch_break', True) if config else True
        lunch_start_time = getattr(config, 'lunch_break_start', time(12, 0)) if config else time(12, 0)
        lunch_end_time = getattr(config, 'lunch_break_end', time(13, 0)) if config else time(13, 0)

        min_booking_time = now + timedelta(hours=min_notice)
        start_dt = datetime.combine(start_date, time.min)
        end_dt = datetime.combine(end_date, time.max)

        # Query blocked times
        blocked_query = db.query(BlockedTime).filter(
            BlockedTime.is_active == True,
            or_(
                BlockedTime.user_id == user_id,
                BlockedTime.applies_to_all_users == True
            ),
            BlockedTime.start_datetime <= end_dt,
            BlockedTime.end_datetime >= start_dt
        )
        if org_id:
            blocked_query = blocked_query.filter(BlockedTime.organization_id == org_id)
        blocked_times = blocked_query.all()

        # Query existing appointments
        appt_query = db.query(Appointment).filter(
            Appointment.assigned_user_id == user_id,
            Appointment.status.in_([AppointmentStatus.BOOKED, AppointmentStatus.TENTATIVE]),
            Appointment.scheduled_start >= start_dt,
            Appointment.scheduled_start <= end_dt
        )
        if org_id:
            appt_query = appt_query.filter(Appointment.organization_id == org_id)
        existing_appts = appt_query.all()

        # Cross-source conflicts
        cross_source_busy = (
            _get_cross_source_conflicts(db, user_id, start_dt, end_dt, org_id=org_id)
            if check_cross_source else []
        )

        # Generate slots day by day
        current_date = start_date
        while current_date <= end_date:
            day_name = current_date.strftime("%A").lower()
            day_hours = working_hours.get(day_name, {})

            if not day_hours.get("enabled", False):
                current_date += timedelta(days=1)
                continue

            # Check max meetings per day
            if user_max_per_day:
                day_appts = [a for a in existing_appts
                             if a.scheduled_start.date() == current_date]
                day_cross = [c for c in cross_source_busy
                             if c[0].date() == current_date]
                if (len(day_appts) + len(day_cross)) >= user_max_per_day:
                    current_date += timedelta(days=1)
                    continue

            # Parse working hours
            try:
                work_start = datetime.strptime(day_hours.get("start", "09:00"), "%H:%M").time()
                work_end = datetime.strptime(day_hours.get("end", "17:00"), "%H:%M").time()
            except ValueError:
                current_date += timedelta(days=1)
                continue

            slot_start = datetime.combine(current_date, work_start)
            day_end = datetime.combine(current_date, work_end)
            lunch_start = datetime.combine(current_date, lunch_start_time) if enforce_lunch else None
            lunch_end = datetime.combine(current_date, lunch_end_time) if enforce_lunch else None

            while slot_start + timedelta(minutes=duration_minutes) <= day_end:
                slot_end = slot_start + timedelta(minutes=duration_minutes)

                # Skip past/too-soon slots
                if slot_start < min_booking_time:
                    slot_start += timedelta(minutes=30)
                    continue

                # Skip lunch break
                if lunch_start and lunch_end and slot_start < lunch_end and slot_end > lunch_start:
                    slot_start += timedelta(minutes=30)
                    continue

                # Check blocked times
                is_blocked = any(
                    slot_start < bt.end_datetime and slot_end > bt.start_datetime
                    for bt in blocked_times
                )
                if is_blocked:
                    slot_start += timedelta(minutes=30)
                    continue

                # Check appointment conflicts (with buffers)
                has_conflict = any(
                    slot_start < (appt.scheduled_end + timedelta(minutes=buffer_after)) and
                    slot_end > (appt.scheduled_start - timedelta(minutes=buffer_before))
                    for appt in existing_appts
                )

                # Check cross-source conflicts
                if not has_conflict and cross_source_busy:
                    has_conflict = _has_cross_source_conflict(
                        cross_source_busy, slot_start, slot_end,
                        buffer_before, buffer_after
                    )

                if not has_conflict:
                    # Build slot dict based on format params
                    if time_key_format == "start_time":
                        slot = {
                            "start_time": slot_start.isoformat() + "Z",
                            "end_time": slot_end.isoformat() + "Z",
                            "date": current_date.isoformat(),
                        }
                    else:
                        slot = {
                            "start": slot_start.isoformat(),
                            "end": slot_end.isoformat(),
                            "date": current_date.isoformat(),
                        }
                    if include_user_id:
                        slot["user_id"] = user_id
                    if include_day_name:
                        slot["day"] = day_name
                    all_slots.append(slot)

                slot_start += timedelta(minutes=30)

            current_date += timedelta(days=1)

    # Deduplicate and sort
    sort_key = "start_time" if time_key_format == "start_time" else "start"
    unique_slots = list({s[sort_key]: s for s in all_slots}.values())
    unique_slots.sort(key=lambda x: x[sort_key])
    return unique_slots


# ============================================================================
# SLOT AVAILABILITY ENGINE
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


# ============================================================================
# AI SLOT RECOMMENDATIONS
# ============================================================================

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
# PUBLIC BOOKING ENDPOINTS (No auth required)
# ============================================================================

@router.get("/public/book/{slug}")
async def get_public_booking_page(
    slug: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """Get public booking page data"""
    _check_rate_limit(request)
    BookingLink = _models['BookingLink']
    AppointmentType = _models['AppointmentType']
    User = _models.get('User')

    link = db.query(BookingLink).filter(
        BookingLink.slug == slug,
        BookingLink.is_active == True,
        BookingLink.is_public == True
    ).first()

    # Auto-create booking link only for the "demo" slug to prevent user enumeration
    if not link:
        if slug != "demo":
            raise HTTPException(status_code=404, detail="Booking link not found")

        try:
            SchedulerConfig = _models['SchedulerConfig']

            if User:
                # For demo slug, use a user who already has a scheduler config (not just any admin)
                target_user = db.query(User).join(
                    SchedulerConfig, SchedulerConfig.user_id == User.id
                ).filter(
                    SchedulerConfig.is_active == True
                ).first()
                if not target_user:
                    # No user with scheduler config; demo not available
                    raise HTTPException(status_code=404, detail="Demo booking not available. No scheduler configured.")

                if target_user:
                    demo_org_id = getattr(target_user, 'organization_id', None)
                    user_name = getattr(target_user, 'full_name', None) or getattr(target_user, 'name', 'Loan Officer')
                    first_name = user_name.split()[0] if user_name else 'Loan Officer'

                    # Get or create SchedulerConfig for this user
                    config_query = db.query(SchedulerConfig).filter(
                        SchedulerConfig.user_id == target_user.id
                    )
                    if demo_org_id:
                        config_query = config_query.filter(SchedulerConfig.organization_id == demo_org_id)
                    user_config = config_query.first()

                    if not user_config:
                        user_config = SchedulerConfig(
                            organization_id=demo_org_id,
                            user_id=target_user.id,
                            config_name=f"{first_name}'s Schedule",
                            description=f"Availability settings for {user_name}",
                            timezone="America/New_York",
                            default_duration_minutes=30,
                            min_notice_hours=2,
                            max_advance_days=60,
                            is_active=True
                        )
                        db.add(user_config)
                        db.flush()

                    # Get or create appointment type for this user
                    user_type = db.query(AppointmentType).filter(
                        AppointmentType.config_id == user_config.id,
                        AppointmentType.is_active == True
                    ).first()

                    if not user_type:
                        user_type = AppointmentType(
                            organization_id=demo_org_id,
                            config_id=user_config.id,
                            type_name="Product Demo",
                            type_key="demo_consultation",
                            description="Schedule a personalized demo of our platform",
                            default_duration_minutes=30,
                            allowed_durations=[15, 30, 45, 60],
                            meeting_type="consultation",
                            default_mode="phone",
                            color="#2563eb",
                            icon="phone",
                            is_public=True,
                            is_active=True,
                            requires_confirmation=False,
                            buffer_before_minutes=5,
                            buffer_after_minutes=5
                        )
                        db.add(user_type)
                        db.flush()

                    link = BookingLink(
                        organization_id=demo_org_id,
                        user_id=target_user.id,
                        slug=slug,
                        link_name="Schedule a Demo",
                        description="Book a personalized demo of Perennia AI",
                        is_active=True,
                        is_public=True,
                        appointment_type_ids=[user_type.id],
                        custom_title="Schedule Your Demo",
                        custom_description="See how Perennia AI can transform your mortgage operations."
                    )
                    db.add(link)
                    db.commit()
                    logger.info(f"Auto-created booking link for slug: {slug}")
        except Exception as e:
            logger.error(f"Error auto-creating booking link for {slug}: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")

    if not link:
        raise HTTPException(status_code=404, detail="Booking link not found")

    # H8: Atomic view count increment to prevent lost updates under concurrency
    BookingLink = _models['BookingLink']
    from sqlalchemy import func
    db.query(BookingLink).filter(BookingLink.id == link.id).update(
        {BookingLink.view_count: func.coalesce(BookingLink.view_count, 0) + 1},
        synchronize_session=False
    )
    db.commit()
    db.refresh(link)

    # Get available appointment types
    appointment_types = []
    if link.single_appointment_type_id:
        appt_type = db.query(AppointmentType).filter(
            AppointmentType.id == link.single_appointment_type_id,
            AppointmentType.is_active == True
        ).first()
        if appt_type:
            appointment_types.append({
                "id": appt_type.id,
                "type_key": appt_type.type_key,
                "type_name": appt_type.type_name,
                "description": appt_type.description,
                "default_duration_minutes": appt_type.default_duration_minutes,
                "allowed_durations": appt_type.allowed_durations,
                "intake_questions": appt_type.intake_questions,
                "color": appt_type.color
            })
    elif link.appointment_type_ids:
        types = db.query(AppointmentType).filter(
            AppointmentType.id.in_(link.appointment_type_ids),
            AppointmentType.is_active == True
        ).all()
        for t in types:
            appointment_types.append({
                "id": t.id,
                "type_key": t.type_key,
                "type_name": t.type_name,
                "description": t.description,
                "default_duration_minutes": t.default_duration_minutes,
                "allowed_durations": t.allowed_durations,
                "intake_questions": t.intake_questions,
                "color": t.color
            })

    return {
        "booking_page": {
            "title": link.custom_title or link.link_name,
            "description": link.custom_description or link.description,
            "logo_url": link.custom_logo_url,
            "color": link.custom_color,
            "appointment_types": appointment_types
        }
    }


@router.get("/public/book/{slug}/slots")
async def get_public_available_slots(
    slug: str,
    appointment_type_id: int = Query(...),
    date: date = Query(..., description="Date to get slots for"),
    duration_minutes: int = Query(30),
    request: Request = None,
    db: Session = Depends(get_db)
):
    """Get available slots for public booking. Delegates to unified slot engine."""
    if request:
        _check_rate_limit(request)

    BookingLink = _models['BookingLink']
    link = db.query(BookingLink).filter(
        BookingLink.slug == slug,
        BookingLink.is_active == True,
        BookingLink.is_public == True
    ).first()

    if not link:
        raise HTTPException(status_code=404, detail="Booking link not found")

    user_ids = link.assigned_users if link.assigned_users else [link.user_id]
    link_org_id = getattr(link, 'organization_id', None)

    available_slots = _generate_available_slots(
        db=db,
        user_ids=user_ids,
        start_date=date,
        end_date=date,
        duration_minutes=duration_minutes,
        org_id=link_org_id,
        check_cross_source=True,
    )

    return {"available_slots": available_slots}


@router.post("/public/book/{slug}/confirm")
async def confirm_public_booking(
    slug: str,
    booking_data: PublicBookingConfirmRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """Confirm a public booking"""
    # Rate limit public booking endpoint
    _check_rate_limit(request, max_requests=5)

    # Extract and sanitize data from request body
    appointment_type_id = booking_data.appointment_type_id
    slot_start = booking_data.start_time
    duration_minutes = booking_data.duration_minutes
    attendee_name = _sanitize_text(booking_data.attendee_name)
    attendee_email = booking_data.attendee_email  # Already validated by EmailStr
    attendee_phone = _sanitize_text(booking_data.attendee_phone)
    notes_text = _sanitize_text(booking_data.notes)
    intake_responses = {"notes": notes_text} if notes_text else {}
    BookingLink = _models['BookingLink']
    AppointmentType = _models['AppointmentType']
    Appointment = _models['Appointment']

    link = db.query(BookingLink).filter(
        BookingLink.slug == slug,
        BookingLink.is_active == True,
        BookingLink.is_public == True
    ).first()

    if not link:
        raise HTTPException(status_code=404, detail="Booking link not found")

    # H5: Enforce booking link limits
    now_utc = datetime.now(timezone.utc)
    if link.expires_at and link.expires_at < now_utc:
        raise HTTPException(status_code=410, detail="This booking link has expired")
    if link.available_from and link.available_from > now_utc:
        raise HTTPException(status_code=410, detail="This booking link is not yet active")
    if link.available_until and link.available_until < now_utc:
        raise HTTPException(status_code=410, detail="This booking link is no longer available")
    if link.max_bookings is not None and (link.booking_count or 0) >= link.max_bookings:
        raise HTTPException(status_code=410, detail="This booking link has reached its maximum number of bookings")

    # Derive org_id from the booking link for tenant isolation
    link_org_id = getattr(link, 'organization_id', None)

    if link.max_per_person is not None:
        max_per_query = db.query(Appointment).filter(
            Appointment.attendee_email == booking_data.attendee_email,
            Appointment.status.notin_(['cancelled', 'no_show']),
            Appointment.external_source == 'booking_link'
        )
        if link_org_id:
            max_per_query = max_per_query.filter(Appointment.organization_id == link_org_id)
        existing_count = max_per_query.count()
        if existing_count >= link.max_per_person:
            raise HTTPException(status_code=429, detail="You have reached the maximum number of bookings allowed")

    appt_type = db.query(AppointmentType).filter(
        AppointmentType.id == appointment_type_id,
        AppointmentType.is_active == True
    ).first()

    if not appt_type:
        raise HTTPException(status_code=404, detail="Appointment type not found")

    # RT1: Determine assigned user via routing strategy
    if booking_data.team_member_id:
        assigned_user_id = booking_data.team_member_id
    else:
        try:
            from services.scheduler_routing_service import assign_loan_officer
            strategy_str = link.routing_strategy.value if hasattr(link.routing_strategy, 'value') else str(link.routing_strategy or "direct")
            assigned_user_id = assign_loan_officer(
                db=db,
                org_id=link_org_id,
                strategy=strategy_str,
                appointment_time=slot_start,
                booking_link=link,
            )
            if not assigned_user_id:
                assigned_user_id = link.user_id  # Final fallback
            logger.info(f"Routing strategy '{strategy_str}' assigned user {assigned_user_id}")
        except Exception as routing_err:
            logger.warning(f"Routing service failed, using link owner: {routing_err}")
            assigned_user_id = link.user_id

    # Determine meeting mode from request or default to VIDEO
    meeting_mode = MeetingMode.VIDEO
    if booking_data.meeting_mode:
        mode_map = {"video": MeetingMode.VIDEO, "phone": MeetingMode.PHONE, "in_person": MeetingMode.IN_PERSON}
        meeting_mode = mode_map.get(booking_data.meeting_mode.lower(), MeetingMode.VIDEO)

    # Create appointment
    slot_end = slot_start + timedelta(minutes=duration_minutes)

    # C1: Prevent double-booking with SELECT FOR UPDATE conflict check
    _check_appointment_conflict(db, assigned_user_id, slot_start, slot_end, org_id=link_org_id)
    # C2: Prevent duplicate booking by same attendee
    _check_duplicate_booking(db, attendee_email, assigned_user_id, slot_start, org_id=link_org_id)

    appointment = Appointment(
        organization_id=link_org_id,
        appointment_type_id=appointment_type_id,
        assigned_user_id=assigned_user_id,
        title=f"{appt_type.type_name} with {attendee_name}",
        description=appt_type.description,
        meeting_type=appt_type.meeting_type,
        meeting_mode=meeting_mode,
        scheduled_start=slot_start,
        scheduled_end=slot_end,
        duration_minutes=duration_minutes,
        attendee_name=attendee_name,
        attendee_email=attendee_email,
        attendee_phone=attendee_phone,
        intake_responses=intake_responses,
        status=AppointmentStatus.BOOKED,
        status_changed_at=datetime.now(timezone.utc),
        external_source="booking_link"
    )

    db.add(appointment)

    # H8: Atomic booking count increments
    from sqlalchemy import func as sqlfunc
    db.query(BookingLink).filter(BookingLink.id == link.id).update(
        {
            BookingLink.booking_count: sqlfunc.coalesce(BookingLink.booking_count, 0) + 1,
            BookingLink.current_bookings: sqlfunc.coalesce(BookingLink.current_bookings, 0) + 1,
            BookingLink.last_booked_at: datetime.now(timezone.utc),
        },
        synchronize_session=False
    )

    # Create video meeting room if meeting mode is VIDEO
    video_link = None
    room_code = None
    if meeting_mode == MeetingMode.VIDEO:
        try:
            # Try to create a video meeting room
            VideoMeetingRoom = _models.get('VideoMeetingRoom')
            if VideoMeetingRoom:
                import secrets
                import string

                # Generate room code
                chars = string.ascii_uppercase + string.digits
                code = ''.join(secrets.choice(chars) for _ in range(9))
                room_code = f"MTG-{code[:3]}-{code[3:6]}-{code[6:]}"

                video_room = VideoMeetingRoom(
                    room_code=room_code,
                    room_name=f"Video Call - {attendee_name}",
                    room_description=f"Scheduled video call with {attendee_name}",
                    provider="internal",
                    host_user_id=assigned_user_id,
                    scheduled_start=slot_start,
                    scheduled_end=slot_end,
                    duration_minutes=duration_minutes,
                    status="scheduled",
                    waiting_room_enabled=True,
                    recording_enabled=True,
                    transcription_enabled=True,
                    ai_assistant_enabled=True,
                    meeting_type="scheduled_call",
                    created_by=assigned_user_id
                )
                db.add(video_room)
                db.flush()  # Get the video room ID

                # Update appointment with video link
                base_url = os.getenv("FRONTEND_URL", "https://perenniaai.com")
                video_link = f"{base_url}/meeting/{room_code}"
                appointment.video_link = video_link
                appointment.video_meeting_id = video_room.id

                logger.info(f"Created video meeting room {room_code} for appointment")
        except Exception as e:
            logger.warning(f"Could not create video meeting room: {e}")
            # Continue without video room - appointment still gets created

    db.commit()
    db.refresh(appointment)

    logger.info(f"Public booking confirmed: {appointment.id} via link {slug}")

    # CRM Integration: Create/link lead
    lead_id = _ensure_lead_for_booking(
        db, attendee_email, attendee_name, attendee_phone,
        assigned_user_id, link_org_id
    )
    if lead_id and not appointment.lead_id:
        appointment.lead_id = lead_id

    # CRM: Log activity
    _log_appointment_activity(
        db, link_org_id, assigned_user_id, lead_id, None,
        f"Public booking confirmed: {appointment.title} on "
        f"{appointment.scheduled_start.strftime('%m/%d/%Y %I:%M %p') if appointment.scheduled_start else 'TBD'}"
    )

    # CRM: Create follow-up task
    _create_followup_task(
        db, link_org_id, assigned_user_id, lead_id, None,
        title=f"Follow up after: {appointment.title}"[:255],
        description=f"Follow up with {attendee_name or 'attendee'} after "
                    f"meeting on {appointment.scheduled_start.strftime('%m/%d/%Y') if appointment.scheduled_start else 'TBD'}",
        due_date=appointment.scheduled_end + timedelta(days=1) if appointment.scheduled_end else datetime.now(timezone.utc) + timedelta(days=2),
    )

    # C3: Soft licensing check
    attendee_state = None
    if intake_responses:
        attendee_state = intake_responses.get("state") or intake_responses.get("property_state")
    licensing_warning = _check_lo_licensing(db, assigned_user_id, attendee_state)
    if licensing_warning:
        logger.warning(f"Appointment {appointment.id}: {licensing_warning}")

    db.commit()

    # Prepare confirmation details
    appointment_date = appointment.scheduled_start.strftime("%A, %B %d, %Y")
    appointment_time = appointment.scheduled_start.strftime("%I:%M %p")
    duration_str = f"{duration_minutes} minutes"

    # Get meeting mode display string
    meeting_mode_str = "Video Call"
    if meeting_mode == MeetingMode.PHONE:
        meeting_mode_str = "Phone Call"
    elif meeting_mode == MeetingMode.IN_PERSON:
        meeting_mode_str = "In Person"

    # Get team member name and email - prefer explicit parameter, then try to fetch from user
    team_member_name = booking_data.team_member_name
    team_member_email = None

    User = _models.get('User')
    if assigned_user_id and User:
        assigned_user = db.query(User).filter(User.id == assigned_user_id).first()
        if assigned_user:
            if not team_member_name:
                team_member_name = assigned_user.first_name
                if assigned_user.last_name:
                    team_member_name += f" {assigned_user.last_name}"
            team_member_email = assigned_user.email

    if not team_member_name and intake_responses and intake_responses.get("notes"):
        notes = intake_responses.get("notes", "")
        if "Appointment with:" in notes:
            team_member_name = notes.split("Appointment with:")[-1].strip()

    # Send email confirmation with calendar invite
    email_sent = False
    sms_sent = False

    if attendee_email:
        try:
            reschedule_url = generate_reschedule_url(appointment.id, attendee_email, slug=slug)
            email_result = send_appointment_confirmation_email(
                attendee_email=attendee_email,
                attendee_name=attendee_name,
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
            # H9: email_result is a dict — extract boolean success
            email_sent = email_result.get("success", False) if isinstance(email_result, dict) else bool(email_result)
            logger.info(f"Confirmation email sent to {_mask_email(attendee_email)}, email_sent={email_sent}")
        except Exception as e:
            logger.error(f"Error sending confirmation email: {e}")

    # Also send notification to team member
    if team_member_email:
        try:
            send_team_member_notification_email(
                team_member_email=team_member_email,
                team_member_name=team_member_name or "Team Member",
                attendee_name=attendee_name,
                attendee_email=attendee_email or "",
                attendee_phone=attendee_phone or "",
                appointment_title=appointment.title,
                appointment_date=appointment_date,
                appointment_time=appointment_time,
                duration=duration_str,
                meeting_mode=meeting_mode_str,
                video_link=video_link,
                scheduled_start=appointment.scheduled_start,
                duration_minutes=appointment.duration_minutes
            )
            logger.info(f"Team member notification sent to {team_member_email}")
        except Exception as team_email_error:
            logger.error(f"Error sending team member notification: {team_email_error}")

    # Auto-create calendar event in team member's Outlook calendar
    calendar_event_created = False
    outlook_event_id = None
    if assigned_user_id:
        try:
            # Build event description — escape all user data for HTML context
            event_description = f"""
            <h3>Client Meeting</h3>
            <p><strong>Client:</strong> {html.escape(attendee_name or 'Not specified')}</p>
            <p><strong>Email:</strong> {html.escape(attendee_email or 'Not specified')}</p>
            <p><strong>Phone:</strong> {html.escape(attendee_phone or 'Not specified')}</p>
            <p><strong>Meeting Type:</strong> {html.escape(meeting_mode_str or '')}</p>
            """
            if appointment.description:
                event_description += f"<p><strong>Notes:</strong> {html.escape(appointment.description)}</p>"
            if video_link:
                event_description += f"<p><strong>Video Link:</strong> <a href='{html.escape(video_link)}'>{html.escape(video_link)}</a></p>"

            # Create calendar event via Microsoft Graph
            calendar_result: CalendarResult = await create_event_via_graph(
                user_id=assigned_user_id,
                subject=f"Meeting: {attendee_name or 'Client'} - {appointment.title}",
                start=appointment.scheduled_start,
                end=appointment.scheduled_end,
                db=db,
                attendees=[attendee_email] if attendee_email else None,
                location=video_link if video_link else None,
                add_teams_link=False,
                body=event_description
            )

            if calendar_result.success:
                calendar_event_created = True
                outlook_event_id = calendar_result.event_id
                # Store the event ID in the appointment for future updates/deletions
                appointment.outlook_event_id = outlook_event_id
                db.commit()
                logger.info(f"Outlook calendar event created for public booking {appointment.id}: {outlook_event_id}")
            else:
                logger.warning(f"Could not create Outlook calendar event for public booking: {calendar_result.error}")

        except Exception as cal_error:
            logger.error(f"Error creating Outlook calendar event for public booking: {cal_error}")

    if attendee_phone:
        try:
            sms_sent = send_appointment_confirmation_sms(
                attendee_phone=attendee_phone,
                attendee_name=attendee_name,
                appointment_date=appointment_date,
                appointment_time=appointment_time,
                team_member_name=team_member_name
            )
        except Exception as e:
            logger.error(f"Error sending confirmation SMS: {e}")

    return {
        "message": "Appointment booked successfully",
        "appointment_id": appointment.id,
        "scheduled_start": appointment.scheduled_start.isoformat(),
        "scheduled_end": appointment.scheduled_end.isoformat(),
        "video_link": video_link,
        "room_code": room_code,
        "confirmation_details": {
            "title": appointment.title,
            "date": appointment_date,
            "time": appointment_time,
            "duration": duration_str,
            "meeting_mode": meeting_mode_str,
            "team_member": team_member_name
        },
        "notifications": {
            "email_sent": email_sent,
            "sms_sent": sms_sent,
            "calendar_event_created": calendar_event_created
        },
        "outlook_event_id": outlook_event_id
    }


# ============================================================================
# PUBLIC WEBSITE DEMO SCHEDULER ENDPOINT
# ============================================================================

@router.post("/public/available-slots")
async def get_website_demo_available_slots(
    request: PublicAvailableSlotsRequest,
    http_request: Request,
    db: Session = Depends(get_db)
):
    _check_rate_limit(http_request)
    """
    Get available slots for website demo scheduling.

    This endpoint looks up the calendar assignment for 'website_demo' purpose
    and returns available slots from the assigned user's calendar.

    Used by the public website demo scheduler.
    """
    from sqlalchemy import text

    try:
        # Parse dates
        start_date = datetime.strptime(request.start_date, "%Y-%m-%d").date()
        end_date = datetime.strptime(request.end_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    # Look up calendar assignment for website_demo purpose
    assignment_result = db.execute(text("""
        SELECT ca.id, ca.assigned_user_id, ca.calendly_url, ca.booking_link_id,
               u.full_name as user_name, u.email as user_email
        FROM calendar_assignments ca
        LEFT JOIN users u ON u.id = ca.assigned_user_id
        WHERE ca.purpose = 'website_demo' AND ca.is_active = true
        LIMIT 1
    """)).fetchone()

    if not assignment_result:
        # No assignment configured - return empty slots with helpful message
        logger.warning("No calendar assignment found for website_demo purpose")
        return {
            "available_slots": [],
            "message": "Website demo calendar not configured. Please assign a team member in Calendar Management.",
            "configured": False
        }

    assigned_user_id = assignment_result.assigned_user_id
    calendly_url = assignment_result.calendly_url
    booking_link_id = assignment_result.booking_link_id

    # If there's a booking link configured, use it
    if booking_link_id and _models:
        BookingLink = _models.get('BookingLink')
        if BookingLink:
            link = db.query(BookingLink).filter(
                BookingLink.id == booking_link_id,
                BookingLink.is_active == True
            ).first()
            if link:
                # Use the booking link's assigned users
                link_org_id = getattr(link, 'organization_id', None)
                user_ids = link.assigned_users if link.assigned_users else [link.user_id]
                return await _generate_slots_for_users(
                    db, user_ids, start_date, end_date, request.duration_minutes,
                    org_id=link_org_id
                )

    # If there's an assigned user, get their availability
    if assigned_user_id:
        return await _generate_slots_for_users(
            db, [assigned_user_id], start_date, end_date, request.duration_minutes
        )

    # If there's a Calendly URL, redirect to Calendly
    if calendly_url:
        return {
            "available_slots": [],
            "calendly_url": calendly_url,
            "message": "Please use the Calendly link to schedule",
            "configured": True
        }

    return {
        "available_slots": [],
        "message": "No calendar configuration found",
        "configured": False
    }


async def _generate_slots_for_users(
    db: Session,
    user_ids: List[int],
    start_date: date,
    end_date: date,
    duration_minutes: int = 30,
    org_id: Optional[int] = None
) -> dict:
    """Generate available slots for a list of users. Delegates to unified slot engine."""
    available_slots = _generate_available_slots(
        db=db,
        user_ids=user_ids,
        start_date=start_date,
        end_date=end_date,
        duration_minutes=duration_minutes,
        org_id=org_id,
        check_cross_source=False,
        include_user_id=True,
        time_key_format="start_time",
    )

    return {
        "available_slots": available_slots,
        "configured": True,
        "slot_count": len(available_slots)
    }


# ============================================================================
# R3: AUTOMATED REMINDER PROCESSING
# ============================================================================

@router.post("/reminders/process", include_in_schema=False)
async def process_reminders(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Internal endpoint: process pending appointment reminders.
    Called by cron/background scheduler. Requires API key authentication.
    """
    api_key = request.headers.get("X-API-Key")
    expected_key = os.getenv("INTERNAL_API_KEY")
    if not expected_key or api_key != expected_key:
        raise HTTPException(status_code=403, detail="Invalid API key")

    if _models is None:
        raise HTTPException(status_code=500, detail="Models not initialized")

    Appointment = _models['Appointment']
    AppointmentReminder = _models.get('AppointmentReminder')

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    sent_count = 0
    error_count = 0

    for hours_before in [24, 1]:
        if hours_before == 24:
            window_start = now + timedelta(hours=23)
            window_end = now + timedelta(hours=25)
        else:
            window_start = now + timedelta(minutes=50)
            window_end = now + timedelta(minutes=70)

        # Find appointments in the reminder window
        filters = [
            Appointment.scheduled_start >= window_start,
            Appointment.scheduled_start <= window_end,
            Appointment.status == AppointmentStatus.BOOKED,
        ]

        # Exclude already-reminded appointments if model available
        if AppointmentReminder:
            from sqlalchemy import text
            already_reminded_ids = [
                r[0] for r in db.execute(text(
                    "SELECT appointment_id FROM scheduler_reminders "
                    "WHERE hours_before = :hb AND status IN ('sent', 'delivered')"
                ), {"hb": hours_before}).fetchall()
            ]
            if already_reminded_ids:
                filters.append(~Appointment.id.in_(already_reminded_ids))

        appointments = db.query(Appointment).filter(and_(*filters)).limit(500).all()

        for appt in appointments:
            # Send email reminder
            if appt.attendee_email:
                try:
                    appointment_date = appt.scheduled_start.strftime("%B %d, %Y") if appt.scheduled_start else ""
                    appointment_time = appt.scheduled_start.strftime("%I:%M %p") if appt.scheduled_start else ""

                    email_result = send_appointment_reminder_email(
                        attendee_email=appt.attendee_email,
                        attendee_name=appt.attendee_name or "there",
                        appointment_title=appt.title,
                        appointment_date=appointment_date,
                        appointment_time=appointment_time,
                        hours_before=hours_before,
                        meeting_mode="Phone Call",
                    )
                    if email_result.get("success"):
                        sent_count += 1
                    else:
                        error_count += 1
                except Exception as e:
                    logger.error(f"Reminder email failed for appt {appt.id}: {e}")
                    error_count += 1

            # Send SMS reminder
            if appt.attendee_phone:
                try:
                    send_appointment_reminder_sms(
                        attendee_phone=appt.attendee_phone,
                        attendee_name=appt.attendee_name or "there",
                        appointment_date=appt.scheduled_start.strftime("%B %d, %Y") if appt.scheduled_start else "",
                        appointment_time=appt.scheduled_start.strftime("%I:%M %p") if appt.scheduled_start else "",
                        hours_before=hours_before,
                    )
                except Exception as e:
                    logger.error(f"Reminder SMS failed for appt {appt.id}: {e}")

            # Record reminder if model available
            if AppointmentReminder:
                try:
                    from smart_scheduler_models import ReminderChannel, ReminderStatus
                    reminder = AppointmentReminder(
                        organization_id=appt.organization_id,
                        appointment_id=appt.id,
                        hours_before=hours_before,
                        scheduled_for=appt.scheduled_start - timedelta(hours=hours_before),
                        status=ReminderStatus.SENT,
                        channel=ReminderChannel.EMAIL,
                        sent_at=now,
                    )
                    db.add(reminder)
                except Exception:
                    pass

        db.commit()

    return {"sent": sent_count, "errors": error_count, "message": f"Processed reminders: {sent_count} sent, {error_count} errors"}


@router.post("/public/book-demo/confirm")
async def confirm_website_demo_booking(
    request: WebsiteDemoBookingRequest,
    http_request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Confirm a website demo booking.

    This endpoint creates an appointment using the calendar assignment
    for 'website_demo' purpose.
    """
    # Rate limit public demo booking endpoint
    _check_rate_limit(http_request, max_requests=5)

    from sqlalchemy import text

    # Look up calendar assignment for website_demo purpose
    assignment_result = db.execute(text("""
        SELECT ca.id, ca.assigned_user_id, ca.calendly_url, ca.booking_link_id,
               u.full_name as user_name, u.email as user_email, u.organization_id as user_org_id
        FROM calendar_assignments ca
        LEFT JOIN users u ON u.id = ca.assigned_user_id
        WHERE ca.purpose = 'website_demo' AND ca.is_active = true
        LIMIT 1
    """)).fetchone()

    if not assignment_result or not assignment_result.assigned_user_id:
        raise HTTPException(
            status_code=400,
            detail="Website demo calendar not configured. Please assign a team member in Calendar Management."
        )

    assigned_user_id = assignment_result.assigned_user_id
    user_name = assignment_result.user_name or "Team Member"
    user_email = assignment_result.user_email
    demo_org_id = getattr(assignment_result, 'user_org_id', None)

    try:
        # Parse the start time — handle both str and datetime
        raw_start = request.start_time
        if isinstance(raw_start, str):
            start_time_str = raw_start.replace("Z", "+00:00")
            start_time = datetime.fromisoformat(start_time_str)
        else:
            start_time = raw_start
        if start_time.tzinfo is None:
            start_time = start_time.replace(tzinfo=pytz.UTC)
    except Exception as e:
        raise HTTPException(status_code=400, detail="Invalid start_time format")

    end_time = start_time + timedelta(minutes=request.duration_minutes)

    # Create the appointment
    Appointment = _models.get('Appointment') if _models else None
    if not Appointment:
        raise HTTPException(status_code=500, detail="Scheduler not initialized")

    # Prevent double-booking
    _check_appointment_conflict(db, assigned_user_id, start_time, end_time, org_id=demo_org_id)

    # Sanitize user-supplied text
    safe_name = _sanitize_text(request.attendee_name)
    safe_phone = _sanitize_text(request.attendee_phone)
    safe_notes = _sanitize_text(request.notes)

    new_appointment = Appointment(
        organization_id=demo_org_id,
        assigned_user_id=assigned_user_id,
        scheduled_start=start_time,
        scheduled_end=end_time,
        duration_minutes=request.duration_minutes,
        attendee_name=safe_name,
        attendee_email=request.attendee_email,
        attendee_phone=safe_phone,
        title=f"Platform Demo with {safe_name}",
        meeting_type=MeetingType.CUSTOM,
        meeting_mode=MeetingMode.VIDEO if request.meeting_mode == "video" else MeetingMode.PHONE,
        status=AppointmentStatus.BOOKED,
        status_changed_at=datetime.now(timezone.utc),
        internal_notes=safe_notes,
        external_source="website_demo"
    )

    db.add(new_appointment)
    db.commit()
    db.refresh(new_appointment)

    # Format confirmation details
    local_tz = pytz.timezone(_get_user_timezone(db, assigned_user_id))
    local_start = start_time.astimezone(local_tz)
    date_str = local_start.strftime("%A, %B %d, %Y")
    time_str = local_start.strftime("%-I:%M %p %Z")

    # Send confirmation email in background
    try:
        background_tasks.add_task(
            notification_service.send_appointment_confirmation,
            borrower_email=request.attendee_email,
            borrower_name=request.attendee_name,
            appointment_type="Platform Demo",
            appointment_time=start_time,
            lo_name=user_name,
            phone_number=request.attendee_phone,
            appointment_id=str(new_appointment.id),
            duration_minutes=request.duration_minutes,
            lo_email=user_email
        )
    except Exception as e:
        logger.warning(f"Failed to queue confirmation email: {e}")

    logger.info(f"Website demo booked: {new_appointment.id} for {_mask_email(request.attendee_email)}")

    return {
        "success": True,
        "appointment_id": new_appointment.id,
        "confirmation_details": {
            "date": date_str,
            "time": time_str,
            "duration": f"{request.duration_minutes} minutes",
            "meeting_mode": request.meeting_mode.title(),
            "host_name": user_name
        },
        "message": f"Demo scheduled with {user_name}"
    }
