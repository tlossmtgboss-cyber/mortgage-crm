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
    DEFAULT_TIMEZONE,
)
from routes.scheduler.error_responses import (
    scheduler_error, validation_error, not_found_error,
    conflict_error, rate_limit_error, internal_error,
    forbidden_error, SLOT_UNAVAILABLE,
)

# Import shared utilities from _helpers.py (single source of truth)
from routes.scheduler._helpers import (
    _sanitize_text,
    _mask_email,
    _validate_phone,
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
from routes.scheduler._crm_integration import NMLSBlockingError
from routes.scheduler.middleware import get_correlated_logger
from db import get_db

import re as _re

logger = get_correlated_logger(__name__)

# AGENT-001: Prompt injection sanitizer for AI booking context
_INJECTION_PATTERNS = _re.compile(
    r'(ignore\s+(all\s+)?previous\s+instructions|you\s+are\s+now|system\s*:\s*|<\s*/?script'
    r'|disregard\s+prior|forget\s+everything|new\s+persona|act\s+as\b|pretend\s+you'
    r'|override\s+instructions|\[INST\]|<<SYS>>|</s>)',
    _re.IGNORECASE
)

# AGENT-001: Additional patterns for free-text fields flowing into AI context
_FREE_TEXT_INJECTION_PATTERNS = _re.compile(
    r'(ignore|forget|disregard)\s+(all\s+)?(previous|above|prior)\s+(instructions?|prompts?|rules?)'
    r'|you\s+are\s+(now|a)\s+'
    r'|system\s*:\s*',
    _re.IGNORECASE
)

# AGENT-002: Schema for ai_booking_context JSON column
AI_BOOKING_CONTEXT_SCHEMA = {
    "required_keys": {"source", "booking_time"},
    "optional_keys": {"intake_responses", "notes", "routing_reason", "confidence_score",
                      "vapi_call_id", "booked_at", "rule_id", "urgency", "regulation",
                      "loan_stage", "converted_from_hold", "hold_source", "conversation_id",
                      "routing_decision"},  # COMP-007: LO routing rationale for RESPA compliance
}


def _sanitize_for_ai_context(text: str) -> str:
    """Strip potential prompt injection from user input before AI context.

    AGENT-001: Applied to attendee_name, attendee_notes, and free-text
    intake_responses before they are stored in ai_booking_context.
    """
    if not text:
        return text
    # Remove common prompt injection patterns
    text = _FREE_TEXT_INJECTION_PATTERNS.sub('[FILTERED]', text)
    # Truncate to reasonable length
    return text[:500]


def _validate_ai_booking_context(context: dict) -> dict:
    """Validate and sanitize ai_booking_context dict shape.

    AGENT-002: Ensures required keys are present (adds defaults if missing),
    strips unknown keys, and applies prompt injection sanitization to all
    string values.
    """
    if not context or not isinstance(context, dict):
        return {"source": "unknown", "booking_time": datetime.now(timezone.utc).isoformat()}

    allowed_keys = AI_BOOKING_CONTEXT_SCHEMA["required_keys"] | AI_BOOKING_CONTEXT_SCHEMA["optional_keys"]

    # Strip unknown keys
    stripped = {k: v for k, v in context.items() if k in allowed_keys}

    # Log if keys were stripped
    removed_keys = set(context.keys()) - allowed_keys
    if removed_keys:
        logger.warning("Stripped unknown keys from ai_booking_context: %s", removed_keys)

    # Ensure required keys are present
    if "source" not in stripped:
        stripped["source"] = "unknown"
    if "booking_time" not in stripped:
        stripped["booking_time"] = datetime.now(timezone.utc).isoformat()

    return stripped


def _sanitize_ai_context(context):
    """Sanitize AI booking context to prevent prompt injection and validate schema.

    Combines AGENT-001 (prompt injection sanitization) and AGENT-002 (schema
    validation) into a single pass.
    """
    if not context or not isinstance(context, dict):
        return context

    # AGENT-002: Validate schema first
    context = _validate_ai_booking_context(context)

    # AGENT-001: Sanitize string values
    sanitized = {}
    for key, value in context.items():
        if isinstance(value, str):
            value = value[:2000]  # Truncate
            if _INJECTION_PATTERNS.search(value):
                logger.warning("Potential prompt injection in ai_booking_context field '%s'", key)
                sanitized[key] = "[REDACTED: suspicious content]"
            else:
                sanitized[key] = value
        elif isinstance(value, dict):
            # Recursively sanitize nested dicts (but don't schema-validate sub-dicts)
            sub = {}
            for sk, sv in value.items():
                if isinstance(sv, str):
                    sv = sv[:2000]
                    if _INJECTION_PATTERNS.search(sv):
                        logger.warning("Potential prompt injection in ai_booking_context nested field '%s.%s'", key, sk)
                        sub[sk] = "[REDACTED: suspicious content]"
                    else:
                        sub[sk] = sv
                else:
                    sub[sk] = sv
            sanitized[key] = sub
        else:
            sanitized[key] = value
    return sanitized


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

# L1: Maximum number of slots returned by public endpoints. If more slots exist,
# the response includes truncated=true so the client knows to narrow its date range.
_PUBLIC_SLOT_CAP = 500


async def _check_booking_ip_rate_limit(request: Request):
    """
    Tighter per-IP rate limit specifically for booking confirmation endpoints.
    Max 5 booking creations per IP per hour.
    Uses the shared _check_rate_limit infrastructure from _helpers.py with a custom key.
    """
    client_ip = _get_client_ip(request)
    key = f"sched_booking:{client_ip}"

    r = await _get_rate_limit_redis()
    if r is None:
        if not await _check_memory_rate_limit(key, _BOOKING_MAX_PER_IP, _BOOKING_RATE_LIMIT_WINDOW):
            rate_limit_error("Too many bookings. Please try again later.")
        return

    try:
        current = await r.incr(key)
        if current == 1:
            await r.expire(key, _BOOKING_RATE_LIMIT_WINDOW)
        if current > _BOOKING_MAX_PER_IP:
            rate_limit_error("Too many bookings. Please try again later.")
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"Booking IP rate limit Redis error, using memory fallback: {e}")
        if not await _check_memory_rate_limit(key, _BOOKING_MAX_PER_IP, _BOOKING_RATE_LIMIT_WINDOW):
            rate_limit_error("Too many bookings. Please try again later.")


def _check_booking_email_rate_limit(db: Session, attendee_email: str, org_id: int = None):
    """
    Per-email booking rate limit: reject if this email has 3+ bookings in the last hour.
    Queries the scheduler_appointments table directly, scoped by org_id for tenant isolation.
    """
    if not attendee_email:
        return

    if org_id is None:
        logger.warning("_check_booking_email_rate_limit called without org_id; skipping rate limit to avoid unscoped query")
        return

    from sqlalchemy import text as sql_text
    normalized_email = attendee_email.strip().lower()
    query = (
        "SELECT COUNT(*) as cnt FROM scheduler_appointments "
        "WHERE LOWER(attendee_email) = :email AND created_at > NOW() - INTERVAL '1 hour'"
        " AND organization_id = :org_id"
    )
    params = {"email": normalized_email, "org_id": org_id}
    result = db.execute(sql_text(query), params).fetchone()

    count = result.cnt if result else 0
    if count >= _BOOKING_MAX_PER_EMAIL:
        logger.warning(
            f"Email booking rate limit exceeded: {_mask_email(attendee_email)} "
            f"has {count} bookings in the last hour"
        )
        rate_limit_error("Too many bookings. Please try again later.")


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
    utm_source: Optional[str] = Query(None, max_length=200),
    utm_medium: Optional[str] = Query(None, max_length=200),
    utm_campaign: Optional[str] = Query(None, max_length=200),
    utm_term: Optional[str] = Query(None, max_length=200),
    utm_content: Optional[str] = Query(None, max_length=200),
    db: Session = Depends(get_db),
):
    """Get public booking page data.

    Captures UTM query parameters and the Referer header so the frontend can
    pass them back during booking confirmation for attribution tracking.
    """
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
                not_found_error("Booking page not found")

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
                        not_found_error("Booking page not found")

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
                                timezone=DEFAULT_TIMEZONE,
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
                        demo_slug = f"demo-{secrets.token_hex(3)}"
                        existing_demo_link_query = db.query(BookingLink).filter(
                            BookingLink.slug.like("demo%")
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
                                slug=demo_slug,
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
                internal_error("Unable to create booking page")

        if not link:
            not_found_error("Booking page not found")

        # Check if the booking link has expired
        if link.expires_at and link.expires_at < datetime.now(timezone.utc):
            scheduler_error(410, SLOT_UNAVAILABLE, "This booking link has expired. Please request a new one.")

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

        # Build attribution from UTM query params, booking link defaults, and Referer header
        attribution = {}
        referer = request.headers.get("referer") or request.headers.get("Referer")
        if utm_source:
            attribution["utm_source"] = utm_source
        elif link.default_utm_source:
            attribution["utm_source"] = link.default_utm_source
        if utm_medium:
            attribution["utm_medium"] = utm_medium
        elif link.default_utm_medium:
            attribution["utm_medium"] = link.default_utm_medium
        if utm_campaign:
            attribution["utm_campaign"] = utm_campaign
        elif link.default_utm_campaign:
            attribution["utm_campaign"] = link.default_utm_campaign
        if utm_term:
            attribution["utm_term"] = utm_term
        if utm_content:
            attribution["utm_content"] = utm_content
        if referer:
            attribution["referrer"] = referer[:2000]

        return {
            "booking_page": {
                "title": link.custom_title or link.link_name,
                "description": link.custom_description or link.description,
                "logo_url": link.custom_logo_url,
                "color": link.custom_color,
                "appointment_types": appointment_types,
            },
            # The frontend should store this and send it back in the confirm request
            "attribution": attribution if attribution else None,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Unexpected error in public booking page for slug '{slug}': {e}")
        internal_error("Something went wrong. Please try again later.")


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

    FUNC-006: When appointment_type_id is provided, the slot duration is resolved
    from the appointment type's default_duration_minutes rather than relying on the
    caller-supplied query parameter (which defaults to the global 30-minute default).
    This ensures slot generation uses the same step size as the appointment type.
    """
    try:
        if request:
            await _check_rate_limit(request)

        # Resolve date range: prefer start_date/end_date, fall back to single date
        date_range_truncated = False
        if start_date and end_date:
            query_start = start_date
            query_end = end_date
            # Cap range at SLOT_GENERATION_MAX_DAYS for public endpoint
            if (query_end - query_start).days > SLOT_GENERATION_MAX_DAYS:
                query_end = query_start + timedelta(days=SLOT_GENERATION_MAX_DAYS)
                date_range_truncated = True
        elif date:
            query_start = date
            query_end = date
        else:
            validation_error("Please provide a date or date range.")

        BookingLink = get_models()['BookingLink']
        link = db.query(BookingLink).filter(
            BookingLink.slug == slug,
            BookingLink.is_active == True,
            BookingLink.is_public == True
        ).first()

        if not link:
            not_found_error("Booking page not found")

        # Check if the booking link has expired
        if link.expires_at and link.expires_at < datetime.now(timezone.utc):
            scheduler_error(410, SLOT_UNAVAILABLE, "This booking link has expired. Please request a new one.")

        user_ids = link.assigned_users if link.assigned_users else [link.user_id]
        link_org_id = getattr(link, 'organization_id', None)

        # FUNC-006: Resolve duration from appointment type when provided.
        # The appointment_type_id is a required query parameter, so look up its
        # configured default_duration_minutes instead of using the caller-supplied
        # default (which is the global 30-minute fallback).
        effective_duration = duration_minutes
        if appointment_type_id:
            AppointmentType = get_models().get('AppointmentType')
            if AppointmentType:
                appt_type = db.query(AppointmentType).filter(
                    AppointmentType.id == appointment_type_id,
                    AppointmentType.is_active == True,
                ).first()
                if appt_type and getattr(appt_type, 'default_duration_minutes', None):
                    effective_duration = appt_type.default_duration_minutes

        available_slots = _generate_available_slots(
            db=db,
            user_ids=user_ids,
            start_date=query_start,
            end_date=query_end,
            duration_minutes=effective_duration,
            org_id=link_org_id,
            check_cross_source=True,
        )

        # L1: Cap results and communicate truncation to the client
        truncated = date_range_truncated or len(available_slots) > _PUBLIC_SLOT_CAP
        if len(available_slots) > _PUBLIC_SLOT_CAP:
            available_slots = available_slots[:_PUBLIC_SLOT_CAP]

        response = {"available_slots": available_slots}
        if truncated:
            response["truncated"] = True
            response["message"] = f"Results limited to {_PUBLIC_SLOT_CAP} slots. Narrow your date range for complete results."

        return response
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Unexpected error in public slots for slug '{slug}': {e}")
        internal_error("Something went wrong. Please try again later.")


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
                forbidden_error("Bot verification required")
        else:
            is_human = await _verify_turnstile_token(booking_data.cf_turnstile_token)
            if not is_human:
                forbidden_error("Bot verification failed. Please try again.")

        # Extract and sanitize data from request body
        appointment_type_id = booking_data.appointment_type_id
        slot_start = booking_data.start_time
        duration_minutes = booking_data.duration_minutes
        attendee_name = _sanitize_text(booking_data.attendee_name)
        attendee_email = booking_data.attendee_email  # Already validated by EmailStr
        attendee_phone = _validate_phone(booking_data.attendee_phone)
        attendee_phone = _sanitize_text(attendee_phone)
        notes_text = _sanitize_text(booking_data.notes)

        # AGENT-001: Sanitize free-text fields for prompt injection before they
        # flow into AI context (intake_responses, attendee_name used in title)
        safe_attendee_name = _sanitize_for_ai_context(attendee_name)
        safe_notes_text = _sanitize_for_ai_context(notes_text)
        intake_responses = {"notes": safe_notes_text} if safe_notes_text else {}

        # If the booking request includes intake_responses, sanitize each value
        if hasattr(booking_data, 'intake_responses') and booking_data.intake_responses:
            for ir_key, ir_val in booking_data.intake_responses.items():
                if isinstance(ir_val, str):
                    intake_responses[ir_key] = _sanitize_for_ai_context(_sanitize_text(ir_val))
                else:
                    intake_responses[ir_key] = ir_val
        BookingLink = get_models()['BookingLink']
        AppointmentType = get_models()['AppointmentType']
        Appointment = get_models()['Appointment']

        link = db.query(BookingLink).filter(
            BookingLink.slug == slug,
            BookingLink.is_active == True,
            BookingLink.is_public == True
        ).first()

        if not link:
            not_found_error("Booking page not found")

        # H5: Enforce booking link limits
        now_utc = datetime.now(timezone.utc)
        if link.expires_at and link.expires_at < now_utc:
            scheduler_error(410, SLOT_UNAVAILABLE, "This booking link has expired. Please request a new one.")
        if link.available_from and link.available_from > now_utc:
            scheduler_error(410, SLOT_UNAVAILABLE, "This booking link is not yet active")
        if link.available_until and link.available_until < now_utc:
            scheduler_error(410, SLOT_UNAVAILABLE, "This booking link is no longer available")
        if link.max_bookings is not None and (link.booking_count or 0) >= link.max_bookings:
            scheduler_error(410, SLOT_UNAVAILABLE, "This booking link has reached its maximum number of bookings")

        # Derive org_id from the booking link for tenant isolation
        link_org_id = getattr(link, 'organization_id', None)

        if link.max_per_person is not None:
            max_per_query = db.query(Appointment).filter(
                Appointment.attendee_email == booking_data.attendee_email,
                Appointment.status.notin_([AppointmentStatus.CANCELLED, AppointmentStatus.NO_SHOW]),
                Appointment.external_source == 'booking_link'
            )
            if link_org_id:
                max_per_query = max_per_query.filter(Appointment.organization_id == link_org_id)
            existing_count = max_per_query.count()
            if existing_count >= link.max_per_person:
                rate_limit_error("You have reached the maximum number of bookings allowed")

        appt_type_query = db.query(AppointmentType).filter(
            AppointmentType.id == appointment_type_id,
            AppointmentType.is_active == True
        )
        if link_org_id:
            appt_type_query = appt_type_query.filter(AppointmentType.organization_id == link_org_id)
        appt_type = appt_type_query.first()

        if not appt_type:
            validation_error("Invalid booking request")

        # ==================================================================
        # M12: Booking dedup window — idempotent response for double-clicks
        # ==================================================================
        from sqlalchemy import text as _sql_text
        _dedup_row = db.execute(
            _sql_text(
                "SELECT id, scheduled_start, scheduled_end "
                "FROM scheduler_appointments "
                "WHERE LOWER(attendee_email) = :email "
                "AND scheduled_start = :start "
                "AND created_at > NOW() - INTERVAL '60 seconds' "
                "AND status NOT IN ('cancelled', 'rescheduled') "
                "ORDER BY created_at DESC LIMIT 1"
            ),
            {"email": attendee_email.strip().lower(), "start": slot_start},
        ).fetchone()
        if _dedup_row:
            logger.info(f"Dedup hit: returning existing appointment {_dedup_row.id} for {_mask_email(attendee_email)}")
            return {
                "message": "Appointment booked successfully",
                "appointment_id": _dedup_row.id,
                "scheduled_start": _dedup_row.scheduled_start.isoformat() if _dedup_row.scheduled_start else slot_start.isoformat(),
                "scheduled_end": _dedup_row.scheduled_end.isoformat() if _dedup_row.scheduled_end else (slot_start + timedelta(minutes=duration_minutes)).isoformat(),
                "deduplicated": True,
            }

        # ==================================================================
        # M9: Enforce max_per_day / max_per_week capacity limits
        # ==================================================================
        _excluded_statuses = [AppointmentStatus.CANCELLED.value, AppointmentStatus.NO_SHOW.value, AppointmentStatus.RESCHEDULED.value]

        if appt_type.max_per_day is not None:
            _day_start = datetime.combine(slot_start.date(), time.min).replace(tzinfo=slot_start.tzinfo)
            _day_end = _day_start + timedelta(days=1)
            _day_params = {
                "user_id": link.user_id,
                "type_id": appointment_type_id,
                "day_start": _day_start,
                "day_end": _day_end,
                "s1": _excluded_statuses[0],
                "s2": _excluded_statuses[1],
                "s3": _excluded_statuses[2],
            }
            if link_org_id:
                _day_params["org_id"] = link_org_id
            _day_count_row = db.execute(
                _sql_text(
                    "SELECT COUNT(*) AS cnt FROM scheduler_appointments "
                    "WHERE assigned_user_id = :user_id "
                    "AND appointment_type_id = :type_id "
                    "AND scheduled_start >= :day_start AND scheduled_start < :day_end "
                    "AND status NOT IN (:s1, :s2, :s3)"
                    + (" AND organization_id = :org_id" if link_org_id else "")
                ),
                _day_params,
            ).fetchone()
            if _day_count_row and _day_count_row.cnt >= appt_type.max_per_day:
                conflict_error("No more appointments available for this day")

        if appt_type.max_per_week is not None:
            # ISO week: Monday=0 .. Sunday=6
            _slot_date = slot_start.date() if hasattr(slot_start, 'date') else slot_start
            _week_start = datetime.combine(_slot_date - timedelta(days=_slot_date.weekday()), time.min).replace(tzinfo=slot_start.tzinfo)
            _week_end = _week_start + timedelta(days=7)
            _week_params = {
                "user_id": link.user_id,
                "type_id": appointment_type_id,
                "week_start": _week_start,
                "week_end": _week_end,
                "s1": _excluded_statuses[0],
                "s2": _excluded_statuses[1],
                "s3": _excluded_statuses[2],
            }
            if link_org_id:
                _week_params["org_id"] = link_org_id
            _week_count_row = db.execute(
                _sql_text(
                    "SELECT COUNT(*) AS cnt FROM scheduler_appointments "
                    "WHERE assigned_user_id = :user_id "
                    "AND appointment_type_id = :type_id "
                    "AND scheduled_start >= :week_start AND scheduled_start < :week_end "
                    "AND status NOT IN (:s1, :s2, :s3)"
                    + (" AND organization_id = :org_id" if link_org_id else "")
                ),
                _week_params,
            ).fetchone()
            if _week_count_row and _week_count_row.cnt >= appt_type.max_per_week:
                conflict_error("No more appointments available this week")

        # RT1: Determine assigned user via routing strategy
        # COMP-007: Build routing_decision context for RESPA compliance
        _routing_decision_context = None

        if booking_data.team_member_id:
            # NC5 fix: Validate team_member_id belongs to the booking link's org
            from database.models import User as _UserModel
            _team_member = db.query(_UserModel).filter(
                _UserModel.id == booking_data.team_member_id,
                _UserModel.organization_id == link_org_id,
            ).first()
            if not _team_member:
                validation_error("Invalid team member selection")
            assigned_user_id = booking_data.team_member_id
            # COMP-007: Log explicit team member selection (not AI-routed)
            _routing_decision_context = {
                "selected_lo_id": assigned_user_id,
                "routing_method": "explicit_selection",
                "candidates_evaluated": 1,
                "selection_criteria": ["attendee_selected_team_member"],
                "respa_compliance": (
                    "No referral fees or prohibited considerations influenced LO selection"
                ),
                "fallback_used": False,
                "fallback_reason": None,
            }
            logger.info(
                "AI_ROUTING_DECISION: lo=%s method=explicit_selection candidates=1 criteria=%s",
                assigned_user_id, ["attendee_selected_team_member"],
            )
        else:
            try:
                from services.scheduler_routing_service import assign_loan_officer_with_context
                strategy_str = link.routing_strategy.value if hasattr(link.routing_strategy, 'value') else str(link.routing_strategy or "direct")
                _routing_result = assign_loan_officer_with_context(
                    db=db,
                    org_id=link_org_id,
                    strategy=strategy_str,
                    appointment_time=slot_start,
                    booking_link=link,
                )
                assigned_user_id = _routing_result.selected_user_id
                _routing_decision_context = _routing_result.to_ai_booking_context()
                if not assigned_user_id:
                    assigned_user_id = link.user_id  # Final fallback
                    _routing_decision_context["fallback_used"] = True
                    _routing_decision_context["fallback_reason"] = "no_candidate_selected_using_link_owner"
                    _routing_decision_context["selected_lo_id"] = assigned_user_id
                    logger.info(
                        "AI_ROUTING_DECISION: lo=%s method=%s candidates=%d criteria=%s fallback=True",
                        assigned_user_id, strategy_str,
                        _routing_result.candidates_evaluated,
                        _routing_result.selection_criteria,
                    )
                else:
                    logger.info(
                        "Routing strategy '%s' assigned user %s", strategy_str, assigned_user_id,
                    )
            except Exception as routing_err:
                logger.warning(f"Routing service failed, using link owner: {routing_err}")
                assigned_user_id = link.user_id
                _routing_decision_context = {
                    "selected_lo_id": assigned_user_id,
                    "routing_method": "fallback_link_owner",
                    "candidates_evaluated": 0,
                    "selection_criteria": ["routing_service_error_fallback"],
                    "respa_compliance": (
                        "No referral fees or prohibited considerations influenced LO selection"
                    ),
                    "fallback_used": True,
                    "fallback_reason": f"routing_service_error: {str(routing_err)[:200]}",
                }
                logger.info(
                    "AI_ROUTING_DECISION: lo=%s method=fallback_link_owner candidates=0 criteria=%s fallback=True",
                    assigned_user_id, ["routing_service_error_fallback"],
                )

        # COMP-007: Build ai_booking_context with routing rationale
        _ai_booking_ctx = {
            "source": "public_booking",
            "booking_time": datetime.now(timezone.utc).isoformat(),
            "routing_decision": _routing_decision_context,
        }

        # Determine meeting mode from request or default to VIDEO
        meeting_mode_str_raw = "video"
        if booking_data.meeting_mode:
            meeting_mode_str_raw = booking_data.meeting_mode.lower()

        slot_end = slot_start + timedelta(minutes=duration_minutes)

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
            title=f"{appt_type.type_name} with {safe_attendee_name}",
            scheduled_start=slot_start,
            scheduled_end=slot_end,
            duration_minutes=duration_minutes,
            timezone=lo_timezone,
            attendee_name=safe_attendee_name,
            attendee_email=attendee_email,
            attendee_phone=attendee_phone,
            appointment_type_id=appointment_type_id,
            description=appt_type.description,
            meeting_type=getattr(appt_type, 'meeting_type', None) if appt_type else None,
            meeting_mode=meeting_mode_str_raw,
            intake_responses=intake_responses,
            external_source="booking_link",
            ai_booking_context=_ai_booking_ctx,
            check_conflicts=True,
            check_cross_source=True,
            generate_meeting_link=True,
            create_lead_if_missing=True,
        )

        # Translate service failure to HTTP error
        if not result.success:
            conflict_error(result.error)

        # ==================================================================
        # H8: Increment booking count AFTER successful appointment creation
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
        db.flush()

        appointment = result.appointment
        video_link = result.video_link

        # ==================================================================
        # Store UTM / attribution data on the appointment and linked lead
        # ==================================================================
        _attribution = {}
        for _utm_field in ("utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "referrer"):
            _val = getattr(booking_data, _utm_field, None)
            if _val:
                _attribution[_utm_field] = _val[:200] if _utm_field != "referrer" else _val[:2000]
        # Fall back to booking link defaults if the request didn't carry UTM params
        if not _attribution.get("utm_source") and link.default_utm_source:
            _attribution["utm_source"] = link.default_utm_source
        if not _attribution.get("utm_medium") and link.default_utm_medium:
            _attribution["utm_medium"] = link.default_utm_medium
        if not _attribution.get("utm_campaign") and link.default_utm_campaign:
            _attribution["utm_campaign"] = link.default_utm_campaign
        # Capture Referer header as fallback if not in the request body
        if not _attribution.get("referrer"):
            _req_referer = request.headers.get("referer") or request.headers.get("Referer")
            if _req_referer:
                _attribution["referrer"] = _req_referer[:2000]

        if _attribution:
            try:
                appointment.booking_attribution = _attribution
                db.flush()
            except Exception as _attr_err:
                logger.warning(f"Could not store booking attribution: {_attr_err}")

            # Also store attribution on the linked lead (if one was created/linked)
            if result.lead_id:
                try:
                    from database.models.lead_loan import Lead as _LeadModel
                    _lead = db.query(_LeadModel).filter(_LeadModel.id == result.lead_id).first()
                    if _lead:
                        # Enrich the lead source with UTM source when available
                        if _attribution.get("utm_source") and (_lead.source or "scheduler") == "scheduler":
                            _lead.source = f"scheduler:{_attribution['utm_source']}"
                        # Append attribution summary to lead notes for audit trail
                        _attr_summary = ", ".join(f"{k}={v}" for k, v in _attribution.items() if k != "referrer")
                        if _attr_summary:
                            _ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
                            _note = f"[{_ts}] Booking attribution: {_attr_summary}"
                            _lead.notes = f"{_lead.notes}\n{_note}".strip() if _lead.notes else _note
                except Exception as _lead_attr_err:
                    logger.warning(f"Could not store lead attribution for lead {result.lead_id}: {_lead_attr_err}")

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

        # Enterprise audit: structured log + DB record for compliance (public booking path)
        booking_details = {
            "booking_link_slug": slug,
            "booking_link_id": link.id,
            "appointment_type": appt_type.type_name if appt_type else None,
        }
        scheduler_audit.log_appointment_created(
            appointment, user={"id": None},
            request=request,
            booking_source="public_booking",
            booking_path_details=booking_details,
        )
        # Also write to the DB audit table so booking link analytics can query it
        scheduler_audit.write_audit_entry(
            db, appointment.id, "created",
            organization_id=appointment.organization_id,
            booking_source="public_booking",
            details=booking_details,
            request=request,
        )

        logger.info(f"Public booking confirmed: {appointment.id} via link {slug}")

        # C3 / H5: NMLS licensing check — blocks LO assignment on failure
        attendee_state = None
        if intake_responses:
            attendee_state = intake_responses.get("state") or intake_responses.get("property_state")
        licensing_warning = None
        nmls_blocked = False
        try:
            licensing_warning = _check_lo_licensing(
                db, assigned_user_id, attendee_state,
                org_id=link_org_id, appointment_id=appointment.id,
            )
        except NMLSBlockingError as nmls_err:
            # NMLS verification failed or LO has no NMLS — unassign from lead
            nmls_blocked = True
            logger.error(
                f"NMLS_BLOCK: Appointment {appointment.id} — LO assignment blocked: {nmls_err}"
            )
            licensing_warning = str(nmls_err)
            if result.lead_id:
                try:
                    from database.models.lead_loan import Lead
                    lead = db.query(Lead).filter(Lead.id == result.lead_id).first()
                    if lead:
                        lead.owner_id = None  # Unassign LO — leave for manual review
                        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
                        note = (
                            f"[{timestamp}] NMLS BLOCKED: LO assignment removed — "
                            f"{nmls_err}. Lead requires manual assignment to a licensed LO."
                        )
                        prev = lead.notes or ""
                        lead.notes = f"{prev}\n{note}".strip()
                except Exception as e:
                    logger.error(f"Failed to unassign LO from lead {result.lead_id}: {e}")

        if licensing_warning and not nmls_blocked:
            # Advisory warning (non-blocking) — flag the lead for compliance review
            logger.warning(f"Appointment {appointment.id}: {licensing_warning}")
            if result.lead_id:
                try:
                    from database.models.lead_loan import Lead
                    lead = db.query(Lead).filter(Lead.id == result.lead_id).first()
                    if lead:
                        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
                        note = f"[{timestamp}] NMLS verification pending - {licensing_warning}"
                        prev = lead.notes or ""
                        lead.notes = f"{prev}\n{note}".strip()
                except Exception as e:
                    logger.error(f"Failed to flag lead {result.lead_id} with NMLS warning: {e}")

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

        # Sync to external calendars (Google Calendar, Outlook) via provider system
        calendar_event_created = False
        if assigned_user_id:
            try:
                from services.calendar_outbound_sync import push_appointment_created
                User = get_models().get('User')
                assigned_user_obj = db.query(User).filter(User.id == assigned_user_id).first() if User else None
                if assigned_user_obj:
                    await push_appointment_created(db, appointment, assigned_user_obj)
                    calendar_event_created = True
            except Exception as cal_error:
                logger.error(f"Outbound calendar sync failed for public booking {appointment.id}: {cal_error}")

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
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Unexpected error in public booking confirmation for slug '{slug}': {e}")
        internal_error("Something went wrong. Please try again later.")


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

        # Look up calendar assignment for website_demo purpose (tenant-scoped)
        _demo_params = {"purpose": "website_demo"}
        _org_filter = ""
        if getattr(request, 'organization_id', None):
            _org_filter = " AND u.organization_id = :org_id"
            _demo_params["org_id"] = request.organization_id

        assignment_result = db.execute(text(
            "SELECT ca.id, ca.assigned_user_id, ca.calendly_url, ca.booking_link_id,"
            "       u.full_name as user_name, u.email as user_email,"
            "       u.organization_id as user_org_id"
            " FROM calendar_assignments ca"
            " LEFT JOIN users u ON u.id = ca.assigned_user_id"
            " WHERE ca.purpose = :purpose AND ca.is_active = true"
            + _org_filter +
            " LIMIT 1"
        ), _demo_params).fetchone()

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
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Unexpected error in public available-slots: {e}")
        internal_error("Something went wrong. Please try again later.")


async def _generate_slots_for_users(
    db: Session,
    user_ids: List[int],
    start_date: date,
    end_date: date,
    duration_minutes: int = DEFAULT_APPOINTMENT_DURATION_MINUTES,
    org_id: Optional[int] = None
) -> dict:
    """Generate available slots for a list of users. Delegates to unified slot engine.

    H5: Does NOT include internal user IDs or tenant configuration in the
    response -- this is a public/unauthenticated endpoint.

    L1: Caps results at _PUBLIC_SLOT_CAP and communicates truncation to the
    client so the frontend can prompt the user to narrow their date range.
    """
    available_slots = _generate_available_slots(
        db=db,
        user_ids=user_ids,
        start_date=start_date,
        end_date=end_date,
        duration_minutes=duration_minutes,
        org_id=org_id,
        check_cross_source=False,
        include_user_id=False,
        time_key_format="start_time",
    )

    # L1: Cap results and communicate truncation
    truncated = len(available_slots) > _PUBLIC_SLOT_CAP
    if truncated:
        available_slots = available_slots[:_PUBLIC_SLOT_CAP]

    response = {
        "available_slots": available_slots,
        "slot_count": len(available_slots),
    }

    if truncated:
        response["truncated"] = True
        response["message"] = f"Results limited to {_PUBLIC_SLOT_CAP} slots. Narrow your date range for complete results."

    return response


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

        # Look up calendar assignment for website_demo purpose (tenant-scoped)
        _demo_params = {"purpose": "website_demo"}
        _org_filter = ""
        if getattr(request, 'organization_id', None):
            _org_filter = " AND u.organization_id = :org_id"
            _demo_params["org_id"] = request.organization_id

        assignment_result = db.execute(text(
            "SELECT ca.id, ca.assigned_user_id, ca.calendly_url, ca.booking_link_id,"
            "       u.full_name as user_name, u.email as user_email,"
            "       u.organization_id as user_org_id"
            " FROM calendar_assignments ca"
            " LEFT JOIN users u ON u.id = ca.assigned_user_id"
            " WHERE ca.purpose = :purpose AND ca.is_active = true"
            + _org_filter +
            " LIMIT 1"
        ), _demo_params).fetchone()

        if not assignment_result or not assignment_result.assigned_user_id:
            logger.warning("Website demo calendar not configured - no assignment found")
            validation_error("Demo scheduling is not available right now. Please try again later.")

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
            validation_error("Invalid booking request. Please check your information and try again.")

        end_time = start_time + timedelta(minutes=request.duration_minutes)

        # Validate and sanitize user-supplied text
        safe_name = _sanitize_text(request.attendee_name)
        safe_phone = _validate_phone(request.attendee_phone)
        safe_phone = _sanitize_text(safe_phone)
        safe_notes = _sanitize_text(request.notes)

        # AGENT-001: Sanitize free-text fields for prompt injection before they
        # flow into AI context (internal_notes, attendee_name used in title)
        safe_name = _sanitize_for_ai_context(safe_name)
        safe_notes = _sanitize_for_ai_context(safe_notes)

        # Determine meeting mode string for the shared service
        demo_meeting_mode = "video" if request.meeting_mode == "video" else "phone"

        # COMP-007: Build ai_booking_context with routing rationale for demo path
        _demo_routing_ctx = {
            "selected_lo_id": assigned_user_id,
            "routing_method": "calendar_assignment",
            "candidates_evaluated": 1,
            "selection_criteria": ["calendar_assignment_purpose_website_demo"],
            "respa_compliance": (
                "No referral fees or prohibited considerations influenced LO selection"
            ),
            "fallback_used": False,
            "fallback_reason": None,
        }
        _demo_ai_booking_ctx = {
            "source": "website_demo",
            "booking_time": datetime.now(timezone.utc).isoformat(),
            "routing_decision": _demo_routing_ctx,
        }
        logger.info(
            "AI_ROUTING_DECISION: lo=%s method=calendar_assignment candidates=1 criteria=%s",
            assigned_user_id, ["calendar_assignment_purpose_website_demo"],
        )

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
            ai_booking_context=_demo_ai_booking_ctx,
            check_conflicts=True,
            check_cross_source=True,
            generate_meeting_link=(demo_meeting_mode == "video"),
            create_lead_if_missing=True,
        )

        # Translate service failure to HTTP error
        if not result.success:
            conflict_error(result.error)

        new_appointment = result.appointment

        # ==================================================================
        # PUBLIC-SPECIFIC POST-CREATION SIDE EFFECTS
        # (enterprise audit, confirmation email, response shaping)
        # ==================================================================

        # Enterprise audit: structured log + DB record for compliance (demo booking path)
        demo_details = {
            "demo_booking": True,
            "external_source": "website_demo",
        }
        # COMP-013: Pass http_request so audit entries capture IP and user-agent
        scheduler_audit.log_appointment_created(
            new_appointment, user={"id": None},
            request=http_request,
            booking_source="public_booking",
            booking_path_details=demo_details,
        )
        scheduler_audit.write_audit_entry(
            db, new_appointment.id, "created",
            organization_id=new_appointment.organization_id,
            booking_source="public_booking",
            details=demo_details,
            request=http_request,
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

        # Sync to external calendars (Google Calendar, Outlook)
        try:
            from services.calendar_outbound_sync import push_appointment_created
            User = get_models().get('User')
            assigned_user_obj = db.query(User).filter(User.id == assigned_user_id).first() if User else None
            if assigned_user_obj:
                await push_appointment_created(db, new_appointment, assigned_user_obj)
        except Exception as cal_error:
            logger.error(f"Outbound calendar sync failed for demo booking {new_appointment.id}: {cal_error}")

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
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Unexpected error in website demo booking: {e}")
        internal_error("Something went wrong. Please try again later.")
