"""
Public Booking Endpoints - Extracted from scheduler_appointment_routes.py

Unauthenticated endpoints for public-facing booking pages:
  - GET  /public/book/{slug}           - Get public booking page data
  - GET  /public/book/{slug}/slots     - Get available slots for a booking link
  - POST /public/book/{slug}/confirm   - Confirm a public booking
  - POST /public/available-slots       - Get slots for website demo scheduling
  - POST /public/book-demo/confirm     - Confirm a website demo booking

All endpoints are rate-limited (Redis with in-memory fallback).
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import and_, func
from datetime import datetime, timedelta, date, time, timezone
from typing import List, Optional
from collections import defaultdict, deque
import html
import logging
import os
import threading
import time as _time

try:
    import nh3
except ImportError:
    nh3 = None

import pytz

from smart_scheduler_models import (
    AppointmentStatus, MeetingType, MeetingMode,
)
from scheduler_models import (
    PublicBookingConfirmRequest, PublicAvailableSlotsRequest,
    WebsiteDemoBookingRequest,
)
from scheduler_email_service import (
    send_appointment_confirmation_email,
    send_appointment_confirmation_sms,
    send_team_member_notification_email,
    generate_reschedule_url,
)
from services.notification_service import notification_service
from services.microsoft_graph import create_event_via_graph, CalendarResult

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================================
# DEPENDENCY INJECTION STORAGE (set by parent module)
# ============================================================================

_get_db = None
_get_current_user_func = None
_models = None

# Parent module helpers (injected via set_dependencies)
_parent_helpers = {}


def set_dependencies(get_db_func, get_current_user_func, models_dict, helpers: dict = None):
    """Set dependencies from parent module.

    helpers dict should contain:
      - _check_appointment_conflict
      - _check_duplicate_booking
      - _log_appointment_activity
      - _ensure_lead_for_booking
      - _create_followup_task
      - _check_lo_licensing
      - _get_user_timezone
      - _generate_available_slots
      - _audit_log
    """
    global _get_db, _get_current_user_func, _models, _parent_helpers
    _get_db = get_db_func
    _get_current_user_func = get_current_user_func
    _models = models_dict
    if helpers:
        _parent_helpers.update(helpers)


def get_db():
    if _get_db is None:
        raise RuntimeError("Dependencies not set")
    yield from _get_db()


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
        logger.info("Public booking rate limiter connected to Redis")
    except Exception as e:
        logger.warning(f"Redis unavailable for public booking rate limiting: {e}")
        _rate_limit_redis = None
    return _rate_limit_redis


# In-memory rate limiter fallback when Redis is unavailable
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
        # Fallback: in-memory rate limiting (per-worker only -- degraded protection)
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
        # Redis command error -- fall back to in-memory
        logger.warning(f"Rate limit Redis error, using memory fallback: {e}")
        if not _check_memory_rate_limit(key, max_requests):
            raise HTTPException(
                status_code=429,
                detail="Too many requests. Please try again later.",
                headers={"Retry-After": str(_RATE_LIMIT_WINDOW)}
            )


# ============================================================================
# INPUT SANITIZATION & ERROR HELPERS
# ============================================================================

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


# Cloudflare Turnstile secret key -- if not set, bot verification is skipped (dev mode)
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


# ============================================================================
# CRM INTEGRATION HELPER
# ============================================================================

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


# ============================================================================
# HELPER ACCESSORS (delegate to parent module helpers)
# ============================================================================

def _check_appointment_conflict(db, assigned_user_id, start_time, end_time, org_id=None, exclude_appointment_id=None):
    return _parent_helpers['_check_appointment_conflict'](
        db, assigned_user_id, start_time, end_time, org_id=org_id,
        exclude_appointment_id=exclude_appointment_id
    )


def _check_duplicate_booking(db, attendee_email, assigned_user_id, start_time, org_id=None):
    return _parent_helpers['_check_duplicate_booking'](
        db, attendee_email, assigned_user_id, start_time, org_id=org_id
    )


def _log_appointment_activity(db, org_id, user_id, lead_id, loan_id, content, activity_type="Meeting"):
    return _parent_helpers['_log_appointment_activity'](
        db, org_id, user_id, lead_id, loan_id, content, activity_type=activity_type
    )


def _create_followup_task(db, org_id, owner_id, lead_id, loan_id, title, description, due_date, priority="medium"):
    return _parent_helpers['_create_followup_task'](
        db, org_id, owner_id, lead_id, loan_id, title=title, description=description,
        due_date=due_date, priority=priority
    )


def _check_lo_licensing(db, assigned_user_id, attendee_state, org_id=None):
    return _parent_helpers['_check_lo_licensing'](
        db, assigned_user_id, attendee_state, org_id=org_id
    )


def _get_user_timezone(db, user_id, org_id=None):
    return _parent_helpers['_get_user_timezone'](db, user_id, org_id=org_id)


def _generate_available_slots(db, user_ids, start_date, end_date, duration_minutes=30,
                               org_id=None, check_cross_source=True, **kwargs):
    return _parent_helpers['_generate_available_slots'](
        db=db, user_ids=user_ids, start_date=start_date, end_date=end_date,
        duration_minutes=duration_minutes, org_id=org_id,
        check_cross_source=check_cross_source, **kwargs
    )


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
    try:
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
                raise HTTPException(status_code=404, detail="Booking page not found")

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
                        raise HTTPException(status_code=404, detail="Booking page not found")

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
                        demo_type_query = db.query(AppointmentType).filter(
                            AppointmentType.config_id == user_config.id,
                            AppointmentType.is_active == True
                        )
                        if demo_org_id:
                            demo_type_query = demo_type_query.filter(AppointmentType.organization_id == demo_org_id)
                        user_type = demo_type_query.first()

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
            raise HTTPException(status_code=404, detail="Booking page not found")

        # H8: Atomic view count increment to prevent lost updates under concurrency
        BookingLink = _models['BookingLink']
        db.query(BookingLink).filter(BookingLink.id == link.id).update(
            {BookingLink.view_count: func.coalesce(BookingLink.view_count, 0) + 1},
            synchronize_session=False
        )
        db.commit()
        db.refresh(link)

        # Get available appointment types (scoped by org to prevent cross-tenant enumeration)
        link_type_org_id = getattr(link, 'organization_id', None)
        appointment_types = []
        if link.single_appointment_type_id:
            type_query = db.query(AppointmentType).filter(
                AppointmentType.id == link.single_appointment_type_id,
                AppointmentType.is_active == True
            )
            if link_type_org_id:
                type_query = type_query.filter(AppointmentType.organization_id == link_type_org_id)
            appt_type = type_query.first()
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
            types_query = db.query(AppointmentType).filter(
                AppointmentType.id.in_(link.appointment_type_ids),
                AppointmentType.is_active == True
            )
            if link_type_org_id:
                types_query = types_query.filter(AppointmentType.organization_id == link_type_org_id)
            types = types_query.all()
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
    except HTTPException as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=_sanitize_public_error(exc.status_code, str(exc.detail)),
            headers=getattr(exc, 'headers', None)
        )
    except Exception as e:
        logger.exception(f"Unexpected error in public booking page for slug '{slug}': {e}")
        raise HTTPException(
            status_code=500,
            detail=_sanitize_public_error(500, "")
        )


@router.get("/public/book/{slug}/slots")
async def get_public_available_slots(
    slug: str,
    appointment_type_id: int = Query(...),
    date: Optional[date] = Query(None, description="Single date to get slots for (legacy)"),
    start_date: Optional[date] = Query(None, description="Start of date range"),
    end_date: Optional[date] = Query(None, description="End of date range"),
    duration_minutes: int = Query(30),
    request: Request = None,
    db: Session = Depends(get_db)
):
    """Get available slots for public booking. Delegates to unified slot engine.

    Supports two modes:
    - Single date: ?date=YYYY-MM-DD (legacy, backward compatible)
    - Date range: ?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD (preferred)

    Date range is capped at 45 days to prevent abuse.
    """
    try:
        if request:
            _check_rate_limit(request)

        # Resolve date range: prefer start_date/end_date, fall back to single date
        if start_date and end_date:
            query_start = start_date
            query_end = end_date
            # Cap range at 45 days for public endpoint
            if (query_end - query_start).days > 45:
                query_end = query_start + timedelta(days=45)
        elif date:
            query_start = date
            query_end = date
        else:
            raise HTTPException(
                status_code=400,
                detail="Please provide a date or date range."
            )

        BookingLink = _models['BookingLink']
        link = db.query(BookingLink).filter(
            BookingLink.slug == slug,
            BookingLink.is_active == True,
            BookingLink.is_public == True
        ).first()

        if not link:
            raise HTTPException(status_code=404, detail="Booking page not found")

        user_ids = link.assigned_users if link.assigned_users else [link.user_id]
        link_org_id = getattr(link, 'organization_id', None)

        available_slots = _generate_available_slots(
            db=db,
            user_ids=user_ids,
            start_date=query_start,
            end_date=query_end,
            duration_minutes=duration_minutes,
            org_id=link_org_id,
            check_cross_source=True,
        )

        return {"available_slots": available_slots}
    except HTTPException as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=_sanitize_public_error(exc.status_code, str(exc.detail)),
            headers=getattr(exc, 'headers', None)
        )
    except Exception as e:
        logger.exception(f"Unexpected error in public slots for slug '{slug}': {e}")
        raise HTTPException(
            status_code=500,
            detail=_sanitize_public_error(500, "")
        )


@router.post("/public/book/{slug}/confirm")
async def confirm_public_booking(
    slug: str,
    booking_data: PublicBookingConfirmRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """Confirm a public booking"""
    try:
        # Rate limit public booking endpoint
        _check_rate_limit(request, max_requests=5)

        # Bot protection: Cloudflare Turnstile verification
        if _TURNSTILE_SECRET_KEY:
            if not booking_data.cf_turnstile_token:
                raise HTTPException(status_code=403, detail="Bot verification required")
            is_human = await _verify_turnstile_token(booking_data.cf_turnstile_token)
            if not is_human:
                raise HTTPException(status_code=403, detail="Bot verification failed. Please try again.")

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
            raise HTTPException(status_code=404, detail="Booking page not found")

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

        appt_type_query = db.query(AppointmentType).filter(
            AppointmentType.id == appointment_type_id,
            AppointmentType.is_active == True
        )
        if link_org_id:
            appt_type_query = appt_type_query.filter(AppointmentType.organization_id == link_org_id)
        appt_type = appt_type_query.first()

        if not appt_type:
            raise HTTPException(status_code=400, detail="Invalid booking request")

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
        licensing_warning = _check_lo_licensing(db, assigned_user_id, attendee_state, org_id=link_org_id)
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
                # H9: email_result is a dict -- extract boolean success
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
                # Build event description -- escape all user data for HTML context
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
                sms_result = send_appointment_confirmation_sms(
                    attendee_phone=attendee_phone,
                    attendee_name=attendee_name,
                    appointment_date=appointment_date,
                    appointment_time=appointment_time,
                    team_member_name=team_member_name
                )
                sms_sent = sms_result.get("success", False) if isinstance(sms_result, dict) else bool(sms_result)
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
    except HTTPException as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=_sanitize_public_error(exc.status_code, str(exc.detail)),
            headers=getattr(exc, 'headers', None)
        )
    except Exception as e:
        logger.exception(f"Unexpected error in public booking confirmation for slug '{slug}': {e}")
        raise HTTPException(
            status_code=500,
            detail=_sanitize_public_error(500, "")
        )


# ============================================================================
# PUBLIC WEBSITE DEMO SCHEDULER ENDPOINTS
# ============================================================================

@router.post("/public/available-slots")
async def get_website_demo_available_slots(
    request: PublicAvailableSlotsRequest,
    http_request: Request,
    db: Session = Depends(get_db)
):
    """
    Get available slots for website demo scheduling.

    This endpoint looks up the calendar assignment for 'website_demo' purpose
    and returns available slots from the assigned user's calendar.

    Used by the public website demo scheduler.
    """
    try:
        _check_rate_limit(http_request)
        from sqlalchemy import text

        # Dates are already validated as date type by Pydantic
        start_date = request.start_date
        end_date = request.end_date

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
            # No assignment configured - return empty slots (no internal details)
            logger.warning("No calendar assignment found for website_demo purpose")
            return {
                "available_slots": [],
                "message": "No available times found. Please try again later.",
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
            "message": "No available times found. Please try again later.",
            "configured": False
        }
    except HTTPException as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=_sanitize_public_error(exc.status_code, str(exc.detail)),
            headers=getattr(exc, 'headers', None)
        )
    except Exception as e:
        logger.exception(f"Unexpected error in public available-slots: {e}")
        raise HTTPException(
            status_code=500,
            detail=_sanitize_public_error(500, "")
        )


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
    try:
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
            logger.warning("Website demo calendar not configured - no assignment found")
            raise HTTPException(
                status_code=400,
                detail="Demo scheduling is not available right now. Please try again later."
            )

        assigned_user_id = assignment_result.assigned_user_id
        user_name = assignment_result.user_name or "Team Member"
        user_email = assignment_result.user_email
        demo_org_id = getattr(assignment_result, 'user_org_id', None)

        try:
            # Parse the start time -- handle both str and datetime
            raw_start = request.start_time
            if isinstance(raw_start, str):
                start_time_str = raw_start.replace("Z", "+00:00")
                start_time = datetime.fromisoformat(start_time_str)
            else:
                start_time = raw_start
            if start_time.tzinfo is None:
                start_time = start_time.replace(tzinfo=pytz.UTC)
        except Exception as e:
            raise HTTPException(status_code=400, detail="Invalid booking request. Please check your information and try again.")

        end_time = start_time + timedelta(minutes=request.duration_minutes)

        # Create the appointment
        Appointment = _models.get('Appointment') if _models else None
        if not Appointment:
            logger.error("Scheduler models not initialized for demo booking")
            raise HTTPException(status_code=500, detail="Something went wrong. Please try again later.")

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
        local_tz = pytz.timezone(_get_user_timezone(db, assigned_user_id, org_id=demo_org_id))
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
    except HTTPException as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=_sanitize_public_error(exc.status_code, str(exc.detail)),
            headers=getattr(exc, 'headers', None)
        )
    except Exception as e:
        logger.exception(f"Unexpected error in website demo booking: {e}")
        raise HTTPException(
            status_code=500,
            detail=_sanitize_public_error(500, "")
        )
