"""
Scheduler Appointment Routes - Appointments & Booking
Consolidated from:
  - scheduler_appointment_routes.py (appointments, availability, booking links, public booking)
  - scheduler_enhanced_routes.py (resources, soft holds, SLA, analytics, group sessions, campaigns)

URL prefix: /api/v1/scheduler/ (applied by parent aggregator)

Extracted sub-modules:
  - routes/scheduler/appointments_crud.py  (appointment CRUD, booking links, AI recs, no-show risk)
  - routes/scheduler/blocked_time.py       (blocked time CRUD, lunch/OOO management)
  - routes/scheduler/public_booking.py     (public booking endpoints, unauthenticated)

Remaining in this file:
- GET/POST /email-service-status, /test-email
- GET/POST/DELETE /availability
- POST /reminders/process
- Enhanced: resources, soft holds, SLA, no-show detect/recover, analytics, group sessions, campaigns
- Shared helpers: cross-source conflict detection, slot generation engine, audit log, CRM helpers
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

from sqlalchemy import func, desc, case, String, extract

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

# Enhanced scheduler imports (resources, soft holds, SLA, analytics, etc.)
try:
    from scheduler_enhancements import (
        ResourceType, ResourceStatus, SchedulingMode, SoftHoldStatus,
        ReminderType, BookingChannel, DEFAULT_REMINDER_PROFILES,
        ResourceCreate, ResourceUpdate, SoftHoldCreate, GroupSessionCreate,
        CampaignBookingCreate, AnalyticsQuery,
        calculate_show_rate, calculate_no_show_rate, get_optimal_slot_score,
        parse_natural_language_time, generate_ics_content
    )
    _ENHANCED_IMPORTS_AVAILABLE = True
except ImportError:
    _ENHANCED_IMPORTS_AVAILABLE = False
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

# Public booking endpoints extracted to separate module
from routes.scheduler.public_booking import (
    router as _public_booking_router,
    set_dependencies as _set_public_booking_deps,
)

# Appointment CRUD, booking links, AI recommendations — extracted
from routes.scheduler.appointments_crud import (
    router as _appointments_crud_router,
    set_dependencies as _set_appointments_crud_deps,
)

# Blocked time CRUD (lunch breaks, OOO, capacity blocks) — extracted
from routes.scheduler.blocked_time import (
    router as _blocked_time_router,
    set_dependencies as _set_blocked_time_deps,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# Include extracted sub-routers
router.include_router(_public_booking_router)
router.include_router(_appointments_crud_router)
router.include_router(_blocked_time_router)


# ============================================================================
# CROSS-SOURCE CONFLICT HELPERS
# ============================================================================

def _get_cross_source_conflicts(db, target_user_id: int, start_dt, end_dt, org_id: int = None):
    """
    Gather all busy time blocks from all 3 calendar sources for a user.
    Returns a list of (start, end) tuples representing occupied time.
    org_id filtering is ALWAYS applied when provided (mandatory for tenant isolation).
    """
    conflicts = []

    # Source 1: v2 Appointment (scheduler_appointments) — canonical table
    if _models and _models.get('Appointment'):
        try:
            V2Appt = _models['Appointment']
            v2_query = db.query(V2Appt).filter(
                V2Appt.assigned_user_id == target_user_id,
                V2Appt.status.in_([AppointmentStatus.BOOKED, AppointmentStatus.TENTATIVE]),
                V2Appt.scheduled_start >= start_dt,
                V2Appt.scheduled_start <= end_dt
            )
            if org_id:
                v2_query = v2_query.filter(V2Appt.organization_id == org_id)
            v2_appts = v2_query.all()
            for a in v2_appts:
                if a.scheduled_start and a.scheduled_end:
                    conflicts.append((a.scheduled_start, a.scheduled_end))
        except Exception as e:
            logger.warning(f"v2 Appointment cross-source check unavailable: {e}")

    # Source 1b: Legacy ScheduledAppointment (scheduled_appointments) — deprecated, kept for backward compat
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
        logger.debug(f"Legacy ScheduledAppointment cross-source check skipped: {e}")

    # Source 2: CalendarEvent (manual calendar entries)
    try:
        from database.models.communication import CalendarEvent
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
_enhanced_models = None


def set_dependencies(get_db_func, get_current_user_func, models_dict):
    """Set dependencies from parent module"""
    global _get_db, _get_current_user_func, _models
    _get_db = get_db_func
    _get_current_user_func = get_current_user_func
    _models = models_dict

    _shared_helpers = {
        '_check_appointment_conflict': _check_appointment_conflict,
        '_check_duplicate_booking': _check_duplicate_booking,
        '_log_appointment_activity': _log_appointment_activity,
        '_ensure_lead_for_booking': _ensure_lead_for_booking,
        '_create_followup_task': _create_followup_task,
        '_check_lo_licensing': _check_lo_licensing,
        '_get_user_timezone': _get_user_timezone,
        '_generate_available_slots': _generate_available_slots,
        '_audit_log': _audit_log,
        '_validate_url': _validate_url,
        '_mask_email': _mask_email,
        '_create_comm_failure_task': _create_comm_failure_task,
        '_calculate_no_show_risk': _calculate_no_show_risk,
    }

    # Wire up the extracted sub-modules
    _set_public_booking_deps(get_db_func, get_current_user_func, models_dict, helpers=_shared_helpers)
    _set_appointments_crud_deps(get_db_func, get_current_user_func, models_dict, helpers=_shared_helpers)
    _set_blocked_time_deps(get_db_func, get_current_user_func, models_dict, helpers={'_audit_log': _audit_log})


from db import get_db


def set_enhanced_dependencies(get_db_func, get_current_user_func, models_dict, enhanced_models_dict):
    """Set dependencies for enhanced scheduler features (resources, soft holds, SLA, etc.)"""
    global _get_db, _get_current_user_func, _models, _enhanced_models
    _get_db = get_db_func
    _get_current_user_func = get_current_user_func
    _models = models_dict
    _enhanced_models = enhanced_models_dict

    _shared_helpers = {
        '_check_appointment_conflict': _check_appointment_conflict,
        '_check_duplicate_booking': _check_duplicate_booking,
        '_log_appointment_activity': _log_appointment_activity,
        '_ensure_lead_for_booking': _ensure_lead_for_booking,
        '_create_followup_task': _create_followup_task,
        '_check_lo_licensing': _check_lo_licensing,
        '_get_user_timezone': _get_user_timezone,
        '_generate_available_slots': _generate_available_slots,
        '_audit_log': _audit_log,
        '_validate_url': _validate_url,
        '_mask_email': _mask_email,
        '_create_comm_failure_task': _create_comm_failure_task,
        '_calculate_no_show_risk': _calculate_no_show_risk,
    }

    # Wire up the extracted sub-modules
    _set_public_booking_deps(get_db_func, get_current_user_func, models_dict, helpers=_shared_helpers)
    _set_appointments_crud_deps(get_db_func, get_current_user_func, models_dict, helpers=_shared_helpers)
    _set_blocked_time_deps(get_db_func, get_current_user_func, models_dict, helpers={'_audit_log': _audit_log})


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
    Only true security roles qualify — 'leadership' and 'management' are display titles, not admin grants.
    """
    role = getattr(user, 'permission_role', '') or getattr(user, 'role', '') or ''
    return role.lower() in ('admin', 'site_admin', 'platform_admin')


def _get_user_timezone(db, user_id: int, org_id: int = None) -> str:
    """Get user's configured timezone from SchedulerConfig, defaulting to America/Chicago.
    Scoped by org_id to prevent cross-tenant config exposure."""
    SchedulerConfig = _models.get('SchedulerConfig')
    if SchedulerConfig and user_id:
        tz_query = db.query(SchedulerConfig).filter(SchedulerConfig.user_id == user_id)
        if org_id:
            tz_query = tz_query.filter(SchedulerConfig.organization_id == org_id)
        config = tz_query.first()
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
_memory_rate_check_count = 0  # Counter for periodic cleanup
_MEMORY_CLEANUP_INTERVAL = 500  # Sweep empty keys every N checks


def _check_memory_rate_limit(key: str, max_requests: int, window_seconds: int = _RATE_LIMIT_WINDOW) -> bool:
    """
    In-memory sliding window rate limit. Returns True if allowed, False if over limit.
    Thread-safe via lock. Not multi-process safe (per-worker protection only).
    Periodically evicts empty keys to prevent unbounded memory growth.
    """
    global _memory_rate_check_count
    now = _time.time()
    with _memory_rate_lock:
        timestamps = _memory_rate_limits[key]
        # Evict expired timestamps
        while timestamps and timestamps[0] < now - window_seconds:
            timestamps.popleft()
        if len(timestamps) >= max_requests:
            return False
        timestamps.append(now)

        # Periodic cleanup: remove keys with empty deques to prevent memory growth
        _memory_rate_check_count += 1
        if _memory_rate_check_count >= _MEMORY_CLEANUP_INTERVAL:
            _memory_rate_check_count = 0
            empty_keys = [k for k, v in _memory_rate_limits.items() if not v]
            for k in empty_keys:
                del _memory_rate_limits[k]
            if empty_keys:
                logger.debug(f"Rate limiter cleanup: evicted {len(empty_keys)} expired keys")

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
        # Fallback: in-memory rate limiting (per-worker only — degraded protection)
        logger.error("Rate limiter: Redis unavailable, using per-worker memory fallback. "
                      "Effective limit is multiplied by worker count. Restore Redis ASAP.")
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


def _sanitize_public_error(status_code: int, detail: str) -> str:
    """
    Map internal error details to safe, user-friendly messages for public endpoints.
    Prevents leaking SQL errors, stack traces, model names, or internal state.
    """
    safe_messages = {
        400: "Invalid booking request. Please check your information and try again.",
        403: "This action is not allowed.",
        404: "Booking page not found.",
        409: "This time slot has already been booked. Please select another time.",
        410: "This booking link is no longer available.",
        429: "Too many requests. Please wait a moment and try again.",
    }
    if status_code in safe_messages:
        return safe_messages[status_code]
    # For all 5xx and unknown codes, return a generic message
    return "Something went wrong. Please try again later."


# Cloudflare Turnstile secret key — if not set, bot verification is skipped (dev mode)
_TURNSTILE_SECRET_KEY = os.getenv("TURNSTILE_SECRET_KEY")


async def _verify_turnstile_token(token: str) -> bool:
    """
    Verify a Cloudflare Turnstile token by POSTing to Cloudflare's siteverify endpoint.
    Returns True if the token is valid, False otherwise.
    """
    import httpx
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                "https://challenges.cloudflare.com/turnstile/v0/siteverify",
                data={
                    "secret": _TURNSTILE_SECRET_KEY,
                    "response": token,
                },
            )
            result = response.json()
            if result.get("success"):
                return True
            logger.warning(f"Turnstile verification failed: {result.get('error-codes', [])}")
            return False
    except Exception as e:
        logger.error(f"Turnstile verification error: {e}")
        return False


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


def _check_appointment_conflict(db, assigned_user_id: int, start_time, end_time, org_id: int = None, exclude_appointment_id=None):
    """
    Check for overlapping appointments using SELECT FOR UPDATE to prevent double-booking.
    Raises HTTPException 409 if a conflict is found or rows are locked by another transaction.
    exclude_appointment_id: skip this appointment (used when rescheduling to avoid self-conflict).
    org_id: ALWAYS applied when provided for tenant isolation.
    """
    from sqlalchemy.exc import OperationalError
    Appointment = _models['Appointment']
    filters = [
        Appointment.assigned_user_id == assigned_user_id,
        Appointment.status.notin_([AppointmentStatus.CANCELLED.value, 'no_show', 'cancelled']),
        Appointment.scheduled_start < end_time,
        Appointment.scheduled_end > start_time,
    ]
    # Always scope by org_id when available (mandatory for tenant isolation)
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
                              start_time, org_id: int = None, window_minutes=30):
    """
    Check for an existing booking with the same attendee_email + same LO
    within ±window_minutes of the proposed start_time.
    Raises HTTPException 409 if a duplicate is found.
    org_id: ALWAYS applied when provided for tenant isolation.
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
    # Always scope by org_id when available (mandatory for tenant isolation)
    if org_id is not None:
        filters.append(Appointment.organization_id == org_id)

    duplicate = db.query(Appointment).filter(and_(*filters)).first()
    if duplicate:
        logger.info(f"Duplicate booking detected: existing appointment {duplicate.id} for {attendee_email}")
        raise HTTPException(
            status_code=409,
            detail="A booking for this email already exists at this time."
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
    """R5: Create a high-priority task when all communication channels fail.
    Note: Does NOT commit — caller owns the transaction boundary."""
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
        logger.info(f"Created communication failure escalation task for {attendee_name}")
    except Exception as e:
        logger.error(f"Failed to create escalation task: {e}")


def _check_lo_licensing(db, assigned_user_id: int, attendee_state: str, org_id: int = None) -> Optional[str]:
    """
    C3: Soft check — verify LO has NMLS number on file.
    Returns a warning string if concern, None if OK. Advisory only.
    Scoped by org_id to prevent cross-tenant user enumeration.
    """
    if not attendee_state:
        return None

    try:
        from database.models.core import User
        lo_query = db.query(User).filter(User.id == assigned_user_id)
        if org_id:
            lo_query = lo_query.filter(User.organization_id == org_id)
        assigned = lo_query.first()
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
    if not _is_scheduler_admin(current_user):
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
# APPOINTMENT ENDPOINTS -> extracted to routes/scheduler/appointments_crud.py
# (list, get, create, update, cancel, booking links, available-slots, AI recommend, no-show risk)
# ============================================================================


# ============================================================================
# BLOCKED TIME ENDPOINTS -> extracted to routes/scheduler/blocked_time.py
# ============================================================================


# ============================================================================
# BOOKING LINK ENDPOINTS -> extracted to routes/scheduler/appointments_crud.py
# ============================================================================


# NOTE: Code below this line was extracted to routes/scheduler/ submodules.
# Orphaned dead code removed during March 2026 enterprise hardening sprint.
