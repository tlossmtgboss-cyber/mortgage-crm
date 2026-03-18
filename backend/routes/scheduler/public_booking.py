"""
Public Booking Endpoints - Extracted from scheduler_appointment_routes.py

Unauthenticated endpoints for public-facing booking pages:
  - GET  /public/book/{slug}           - Get public booking page data
  - GET  /public/book/{slug}/slots     - Get available slots for a booking link
  - POST /public/book/{slug}/confirm   - Confirm a public booking
  - POST /public/available-slots       - Get slots for website demo scheduling
  - POST /public/book-demo/confirm     - Confirm a website demo booking

All endpoints are rate-limited via shared infrastructure in _helpers.py.

Appointment creation is delegated to the shared appointment_creation_service,
which handles conflict checking, duplicate detection, cross-source calendar
checks, meeting link generation, lead creation/linking, activity logging,
follow-up task creation, and audit logging.  This module retains ownership of
public-specific concerns: rate limiting, CAPTCHA, booking link validation,
routing strategy, booking counter increments, confirmation emails/SMS, Outlook
calendar event creation, confirmation token generation, and response shaping.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import and_, func
from datetime import datetime, timedelta, date, time, timezone
from typing import List, Optional
import html
import logging
import os
import secrets

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
from services.scheduler_audit_logger import scheduler_audit
from services.appointment_creation_service import (
    create_appointment as _create_appointment_via_service,
    AppointmentCreationResult,
)
from routes.scheduler.constants import (
    DEFAULT_APPOINTMENT_DURATION_MINUTES,
    ALLOWED_APPOINTMENT_DURATIONS,
    DEFAULT_BUFFER_BEFORE_MINUTES,
    DEFAULT_BUFFER_AFTER_MINUTES,
    DEFAULT_MIN_NOTICE_HOURS,
    DEFAULT_MAX_ADVANCE_DAYS,
    SLOT_GENERATION_MAX_DAYS,
    BOOKING_RATE_LIMIT_PER_EMAIL,
    BOOKING_RATE_LIMIT_PER_IP,
    DEMO_CREATE_RATE_LIMIT,
    PUBLIC_BOOKING_RATE_LIMIT,
)

# Import shared utilities from _helpers.py (single source of truth)
from routes.scheduler._helpers import (
    _sanitize_text,
    _mask_email,
    _validate_phone,
    _sanitize_public_error,
    _verify_turnstile_token,
    _get_client_ip,
    _get_rate_limit_redis,
    _check_memory_rate_limit,
    _check_rate_limit,
    _ensure_lead_for_booking,
    _RATE_LIMIT_WINDOW,
    _IS_PRODUCTION,
    _TURNSTILE_SECRET_KEY,
    get_models,
    _check_appointment_conflict,
    _check_duplicate_booking,
    _get_cross_source_conflicts,
    _has_cross_source_conflict,
    _log_appointment_activity,
    _create_followup_task,
    _check_lo_licensing,
    _get_user_timezone,
    _generate_available_slots,
    _audit_log,
)
from db import get_db

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================================
# BACKWARD COMPATIBILITY — set_dependencies is a no-op now that we use
# direct imports from _helpers.py and db.py.
# ============================================================================

def set_dependencies(get_db_func=None, get_current_user_func=None, models_dict=None, helpers: dict = None):
    """No-op — kept for backward compatibility with scheduler_appointment_routes.py."""
    pass


# ============================================================================
# BOOKING-SPECIFIC RATE LIMITS (per-email, per-IP for confirm endpoints)
# These are unique to booking endpoints and use the shared rate-limit
# infrastructure from _helpers.py.
# ============================================================================

_BOOKING_RATE_LIMIT_WINDOW = int(os.getenv("SCHEDULER_BOOKING_RATE_LIMIT_WINDOW", "3600"))  # 1 hour default
_BOOKING_MAX_PER_EMAIL = int(os.getenv("SCHEDULER_BOOKING_MAX_PER_EMAIL", str(BOOKING_RATE_LIMIT_PER_EMAIL)))
_BOOKING_MAX_PER_IP = int(os.getenv("SCHEDULER_BOOKING_MAX_PER_IP", str(BOOKING_RATE_LIMIT_PER_IP)))


async def _check_booking_ip_rate_limit(request: Request):
    """
    Tighter per-IP rate limit specifically for booking confirmation endpoints.
    Max 5 booking creations per IP per hour.
    Uses the shared _check_rate_limit infrastructure from _helpers.py with a custom key.
    """
    client_ip = _get_client_ip(request)
    key = f"sched_booking:{client_ip}"

    r = _get_rate_limit_redis()
    if r is None:
        if not await _check_memory_rate_limit(key, _BOOKING_MAX_PER_IP, _BOOKING_RATE_LIMIT_WINDOW):
            raise HTTPException(
                status_code=429,
                detail="Too many bookings. Please try again later.",
                headers={"Retry-After": str(_BOOKING_RATE_LIMIT_WINDOW)}
            )
        return

    try:
        current = r.incr(key)
        if current == 1:
            r.expire(key, _BOOKING_RATE_LIMIT_WINDOW)
        if current > _BOOKING_MAX_PER_IP:
            ttl = r.ttl(key)
            raise HTTPException(
                status_code=429,
                detail="Too many bookings. Please try again later.",
                headers={"Retry-After": str(max(ttl, 1))}
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"Booking IP rate limit Redis error, using memory fallback: {e}")
        if not await _check_memory_rate_limit(key, _BOOKING_MAX_PER_IP, _BOOKING_RATE_LIMIT_WINDOW):
            raise HTTPException(
                status_code=429,
                detail="Too many bookings. Please try again later.",
                headers={"Retry-After": str(_BOOKING_RATE_LIMIT_WINDOW)}
            )


def _check_booking_email_rate_limit(db: Session, attendee_email: str):
    """
    Per-email booking rate limit: reject if this email has 3+ bookings in the last hour.
    Queries the scheduler_appointments table directly.
    """
    if not attendee_email:
        return

    from sqlalchemy import text as sql_text
    result = db.execute(sql_text(
        "SELECT COUNT(*) as cnt FROM scheduler_appointments "
        "WHERE attendee_email = :email AND created_at > NOW() - INTERVAL '1 hour'"
    ), {"email": attendee_email}).fetchone()

    count = result.cnt if result else 0
    if count >= _BOOKING_MAX_PER_EMAIL:
        logger.warning(
            f"Email booking rate limit exceeded: {_mask_email(attendee_email)} "
            f"has {count} bookings in the last hour"
        )
        raise HTTPException(
            status_code=429,
            detail="Too many bookings. Please try again later.",
            headers={"Retry-After": str(_BOOKING_RATE_LIMIT_WINDOW)}
        )


# Helper functions (_check_appointment_conflict, _check_duplicate_booking,
# _log_appointment_activity, _create_followup_task, _check_lo_licensing,
# _get_user_timezone, _generate_available_slots, _audit_log) are now
# imported directly from _helpers.py above.


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
        await _check_rate_limit(request)
        BookingLink = get_models()['BookingLink']
        AppointmentType = get_models()['AppointmentType']
        User = get_models().get('User')

        # Slug must be globally unique (enforced by DB constraint).
        # Query by slug + active + public; org_id derived from the link itself.
        link = db.query(BookingLink).filter(
            BookingLink.slug == slug,
            BookingLink.is_active == True,
            BookingLink.is_public == True
        ).first()

        # Auto-create booking link only for the "demo" slug to prevent user enumeration
        if not link:
            if slug != "demo":
                raise HTTPException(status_code=404, detail="Booking page not found")

            # Tighter rate limit for demo auto-creation to prevent spam
            await _check_rate_limit(request, max_requests=DEMO_CREATE_RATE_LIMIT, custom_key=f"sched_demo_create:{_get_client_ip(request)}")

            try:
                SchedulerConfig = get_models()['SchedulerConfig']

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
                                default_duration_minutes=DEFAULT_APPOINTMENT_DURATION_MINUTES,
                                min_notice_hours=DEFAULT_MIN_NOTICE_HOURS,
                                max_advance_days=DEFAULT_MAX_ADVANCE_DAYS,
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
                                default_duration_minutes=DEFAULT_APPOINTMENT_DURATION_MINUTES,
                                allowed_durations=ALLOWED_APPOINTMENT_DURATIONS,
                                meeting_type="consultation",
                                default_mode="phone",
                                color="#2563eb",
                                icon="phone",
                                is_public=True,
                                is_active=True,
                                requires_confirmation=False,
                                buffer_before_minutes=DEFAULT_BUFFER_BEFORE_MINUTES,
                                buffer_after_minutes=DEFAULT_BUFFER_AFTER_MINUTES
                            )
                            db.add(user_type)
                            db.flush()

                        # Guard: check if a demo link already exists for this org
                        # (may have been created by a concurrent request or previously deactivated)
                        existing_demo_link_query = db.query(BookingLink).filter(
                            BookingLink.slug == "demo"
                        )
                        if demo_org_id:
                            existing_demo_link_query = existing_demo_link_query.filter(
                                BookingLink.organization_id == demo_org_id
                            )
                        existing_demo_link = existing_demo_link_query.first()

                        if existing_demo_link:
                            # Re-activate and update the existing link instead of creating a new one
                            existing_demo_link.is_active = True
                            existing_demo_link.is_public = True
                            existing_demo_link.appointment_type_ids = [user_type.id]
                            link = existing_demo_link
                        else:
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
                logger.exception(f"Error auto-creating booking link for {slug}")
                # Creation was attempted but failed — return 500, not 404
                raise HTTPException(status_code=500, detail="Unable to create booking page")

        if not link:
            raise HTTPException(status_code=404, detail="Booking page not found")

        # Check if the booking link has expired
        if link.expires_at and link.expires_at < datetime.now(timezone.utc):
            raise HTTPException(
                status_code=410,
                detail="This booking link has expired. Please request a new one."
            )

        # H8: Atomic view count increment to prevent lost updates under concurrency
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
    duration_minutes: int = Query(DEFAULT_APPOINTMENT_DURATION_MINUTES),
    request: Request = None,
    db: Session = Depends(get_db)
):
    """Get available slots for public booking. Delegates to unified slot engine.

    Supports two modes:
    - Single date: ?date=YYYY-MM-DD (legacy, backward compatible)
    - Date range: ?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD (preferred)

    Date range is capped at SLOT_GENERATION_MAX_DAYS days to prevent abuse.
    """
    try:
        if request:
            await _check_rate_limit(request)

        # Resolve date range: prefer start_date/end_date, fall back to single date
        if start_date and end_date:
            query_start = start_date
            query_end = end_date
            # Cap range at SLOT_GENERATION_MAX_DAYS for public endpoint
            if (query_end - query_start).days > SLOT_GENERATION_MAX_DAYS:
                query_end = query_start + timedelta(days=SLOT_GENERATION_MAX_DAYS)
        elif date:
            query_start = date
            query_end = date
        else:
            raise HTTPException(
                status_code=400,
                detail="Please provide a date or date range."
            )

        BookingLink = get_models()['BookingLink']
        link = db.query(BookingLink).filter(
            BookingLink.slug == slug,
            BookingLink.is_active == True,
            BookingLink.is_public == True
        ).first()

        if not link:
            raise HTTPException(status_code=404, detail="Booking page not found")

        # Check if the booking link has expired
        if link.expires_at and link.expires_at < datetime.now(timezone.utc):
            raise HTTPException(
                status_code=410,
                detail="This booking link has expired. Please request a new one."
            )

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
    """Confirm a public booking.

    Public-specific validation (rate limiting, CAPTCHA, booking link checks) is
    handled here.  The actual appointment creation (conflict checking, persistence,
    lead linking, activity logging, follow-up tasks, audit logging, meeting link
    generation) is delegated to the shared appointment_creation_service.
    """
    try:
        # ==================================================================
        # PUBLIC-SPECIFIC VALIDATION (rate limiting, CAPTCHA, link checks)
        # ==================================================================

        # Rate limit public booking endpoint
        await _check_rate_limit(request, max_requests=BOOKING_RATE_LIMIT_PER_EMAIL)

        # Anti-spam: per-IP booking rate limit
        await _check_booking_ip_rate_limit(request)

        # Anti-spam: per-email booking rate limit
        _check_booking_email_rate_limit(db, booking_data.attendee_email)

        # Bot protection: Cloudflare Turnstile verification
        # Always run verification -- _verify_turnstile_token handles missing key
        # (rejects in production, allows in dev/test)
        if not booking_data.cf_turnstile_token:
            if _TURNSTILE_SECRET_KEY or _IS_PRODUCTION:
                raise HTTPException(status_code=403, detail="Bot verification required")
        else:
            is_human = await _verify_turnstile_token(booking_data.cf_turnstile_token)
            if not is_human:
                raise HTTPException(status_code=403, detail="Bot verification failed. Please try again.")

        # Extract and sanitize data from request body
        appointment_type_id = booking_data.appointment_type_id
        slot_start = booking_data.start_time
        duration_minutes = booking_data.duration_minutes
        attendee_name = _sanitize_text(booking_data.attendee_name)
        attendee_email = booking_data.attendee_email  # Already validated by EmailStr
        attendee_phone = _validate_phone(booking_data.attendee_phone)
        attendee_phone = _sanitize_text(attendee_phone)
        notes_text = _sanitize_text(booking_data.notes)
        intake_responses = {"notes": notes_text} if notes_text else {}
        BookingLink = get_models()['BookingLink']
        AppointmentType = get_models()['AppointmentType']
        Appointment = get_models()['Appointment']

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
            raise HTTPException(status_code=410, detail="This booking link has expired. Please request a new one.")
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
        meeting_mode_str_raw = "video"
        if booking_data.meeting_mode:
            meeting_mode_str_raw = booking_data.meeting_mode.lower()

        slot_end = slot_start + timedelta(minutes=duration_minutes)

        # ==================================================================
        # H8: Atomic booking count increments (staged before service commit)
        # This runs on the same db session, so it will be committed atomically
        # with the appointment creation inside the shared service.
        # ==================================================================
        from sqlalchemy import func as sqlfunc
        db.query(BookingLink).filter(BookingLink.id == link.id).update(
            {
                BookingLink.booking_count: sqlfunc.coalesce(BookingLink.booking_count, 0) + 1,
                BookingLink.current_bookings: sqlfunc.coalesce(BookingLink.current_bookings, 0) + 1,
                BookingLink.last_booked_at: datetime.now(timezone.utc),
            },
            synchronize_session=False
        )

        # ==================================================================
        # DELEGATE TO SHARED APPOINTMENT CREATION SERVICE
        # Handles: conflict check, duplicate check, cross-source check,
        #          appointment persistence, meeting link generation,
        #          lead creation/linking, activity logging, follow-up task,
        #          audit logging, and db.commit().
        # ==================================================================
        # Resolve the assigned LO's timezone for the appointment record
        lo_timezone = _get_user_timezone(db, assigned_user_id, org_id=link_org_id)

        result: AppointmentCreationResult = await _create_appointment_via_service(
            db=db,
            organization_id=link_org_id,
            assigned_user_id=assigned_user_id,
            created_by_user_id=None,  # Public booking -- no authenticated user
            source="public_booking",
            title=f"{appt_type.type_name} with {attendee_name}",
            scheduled_start=slot_start,
            scheduled_end=slot_end,
            duration_minutes=duration_minutes,
            timezone=lo_timezone,
            attendee_name=attendee_name,
            attendee_email=attendee_email,
            attendee_phone=attendee_phone,
            appointment_type_id=appointment_type_id,
            description=appt_type.description,
            meeting_type=getattr(appt_type, 'meeting_type', None) if appt_type else None,
            meeting_mode=meeting_mode_str_raw,
            intake_responses=intake_responses,
            external_source="booking_link",
            check_conflicts=True,
            check_cross_source=True,
            generate_meeting_link=True,
            create_lead_if_missing=True,
        )

        # Translate service failure to HTTP error
        if not result.success:
            raise HTTPException(status_code=409, detail=result.error)

        appointment = result.appointment
        video_link = result.video_link

        # Fallback room code for video meetings
        room_code = None
        meeting_mode_enum = MeetingMode.VIDEO
        if booking_data.meeting_mode:
            mode_map = {"video": MeetingMode.VIDEO, "phone": MeetingMode.PHONE, "in_person": MeetingMode.IN_PERSON}
            meeting_mode_enum = mode_map.get(meeting_mode_str_raw, MeetingMode.VIDEO)

        if meeting_mode_enum == MeetingMode.VIDEO:
            room_code = secrets.token_urlsafe(8) if not video_link else None

        # ==================================================================
        # PUBLIC-SPECIFIC POST-CREATION SIDE EFFECTS
        # (enterprise audit, Outlook calendar, emails/SMS, confirmation token)
        # ==================================================================

        # Enterprise audit: structured log for compliance (public booking path)
        scheduler_audit.log_appointment_created(
            appointment, user={"id": None},
            request=request,
            booking_source="public_booking",
            booking_path_details={
                "booking_link_slug": slug,
                "booking_link_id": link.id,
                "appointment_type": appt_type.type_name if appt_type else None,
            },
        )

        logger.info(f"Public booking confirmed: {appointment.id} via link {slug}")

        # C3: Soft licensing check (advisory only)
        attendee_state = None
        if intake_responses:
            attendee_state = intake_responses.get("state") or intake_responses.get("property_state")
        licensing_warning = _check_lo_licensing(db, assigned_user_id, attendee_state, org_id=link_org_id)
        if licensing_warning:
            logger.warning(f"Appointment {appointment.id}: {licensing_warning}")

        # Prepare confirmation details
        appointment_date = appointment.scheduled_start.strftime("%A, %B %d, %Y")
        appointment_time = appointment.scheduled_start.strftime("%I:%M %p")
        duration_str = f"{duration_minutes} minutes"

        # Get meeting mode display string
        meeting_mode_str = "Video Call"
        if meeting_mode_enum == MeetingMode.PHONE:
            meeting_mode_str = "Phone Call"
        elif meeting_mode_enum == MeetingMode.IN_PERSON:
            meeting_mode_str = "In Person"

        # Get team member name and email - prefer explicit parameter, then try to fetch from user
        team_member_name = booking_data.team_member_name
        team_member_email = None

        User = get_models().get('User')
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
                    team_member_name=team_member_name,
                    organization_id=link_org_id
                )
                sms_sent = sms_result.get("success", False) if isinstance(sms_result, dict) else bool(sms_result)
            except Exception as e:
                logger.error(f"Error sending confirmation SMS: {e}")

        # Generate confirmation token for rich confirmation page
        confirmation_token = None
        confirmation_url = None
        try:
            from routes.scheduler.confirmation import _generate_confirmation_token
            confirmation_token = _generate_confirmation_token(
                appointment.id, attendee_email or ""
            )
            frontend_url = os.getenv("FRONTEND_URL", "https://app.perenniaai.com")
            confirmation_url = (
                f"{frontend_url}/booking/confirmation/{appointment.id}"
                f"?token={confirmation_token}"
            )
        except Exception as token_err:
            logger.warning(f"Could not generate confirmation token: {token_err}")

        return {
            "message": "Appointment booked successfully",
            "appointment_id": appointment.id,
            "scheduled_start": appointment.scheduled_start.isoformat(),
            "scheduled_end": appointment.scheduled_end.isoformat(),
            "video_link": video_link,
            "room_code": room_code,
            "confirmation_token": confirmation_token,
            "confirmation_url": confirmation_url,
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
        await _check_rate_limit(http_request)
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
        if booking_link_id and get_models():
            BookingLink = get_models().get('BookingLink')
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
    duration_minutes: int = DEFAULT_APPOINTMENT_DURATION_MINUTES,
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
    """Confirm a website demo booking.

    Public-specific validation (rate limiting, calendar assignment lookup) is
    handled here.  The actual appointment creation is delegated to the shared
    appointment_creation_service.
    """
    try:
        # ==================================================================
        # PUBLIC-SPECIFIC VALIDATION (rate limiting, assignment lookup)
        # ==================================================================

        # Rate limit public demo booking endpoint
        await _check_rate_limit(http_request, max_requests=BOOKING_RATE_LIMIT_PER_EMAIL)

        # Anti-spam: per-IP booking rate limit
        await _check_booking_ip_rate_limit(http_request)

        # Anti-spam: per-email booking rate limit
        _check_booking_email_rate_limit(db, request.attendee_email)

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

        # Validate and sanitize user-supplied text
        safe_name = _sanitize_text(request.attendee_name)
        safe_phone = _validate_phone(request.attendee_phone)
        safe_phone = _sanitize_text(safe_phone)
        safe_notes = _sanitize_text(request.notes)

        # Determine meeting mode string for the shared service
        demo_meeting_mode = "video" if request.meeting_mode == "video" else "phone"

        # ==================================================================
        # DELEGATE TO SHARED APPOINTMENT CREATION SERVICE
        # Handles: conflict check, duplicate check, cross-source check,
        #          appointment persistence, lead creation/linking, activity
        #          logging, follow-up task, audit logging, and db.commit().
        # ==================================================================
        # Resolve the assigned LO's timezone for the appointment record
        demo_lo_timezone = _get_user_timezone(db, assigned_user_id, org_id=demo_org_id)

        result: AppointmentCreationResult = await _create_appointment_via_service(
            db=db,
            organization_id=demo_org_id,
            assigned_user_id=assigned_user_id,
            created_by_user_id=None,  # Public booking -- no authenticated user
            source="public_booking",
            title=f"Platform Demo with {safe_name}",
            scheduled_start=start_time,
            scheduled_end=end_time,
            duration_minutes=request.duration_minutes,
            timezone=demo_lo_timezone,
            attendee_name=safe_name,
            attendee_email=request.attendee_email,
            attendee_phone=safe_phone,
            meeting_type="custom",
            meeting_mode=demo_meeting_mode,
            internal_notes=safe_notes,
            external_source="website_demo",
            check_conflicts=True,
            check_cross_source=True,
            generate_meeting_link=(demo_meeting_mode == "video"),
            create_lead_if_missing=True,
        )

        # Translate service failure to HTTP error
        if not result.success:
            raise HTTPException(status_code=409, detail=result.error)

        new_appointment = result.appointment

        # ==================================================================
        # PUBLIC-SPECIFIC POST-CREATION SIDE EFFECTS
        # (enterprise audit, confirmation email, response shaping)
        # ==================================================================

        # Enterprise audit: structured log for compliance (demo booking path)
        scheduler_audit.log_appointment_created(
            new_appointment, user={"id": None},
            booking_source="public_booking",
            booking_path_details={
                "demo_booking": True,
                "external_source": "website_demo",
            },
        )

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
