"""
Scheduler availability engine — unified slot generation, cross-source conflict
detection, and timezone helpers.
"""

from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import or_
from datetime import datetime, timedelta, date, time, timezone
from typing import List, Optional
from collections import defaultdict
import pytz
import logging
import time as time_mod

from smart_scheduler_models import (
    AppointmentStatus, DayOfWeek, SlotPriority, DEFAULT_WORKING_HOURS,
)
from routes.scheduler.constants import (
    DEFAULT_APPOINTMENT_DURATION_MINUTES,
    DEFAULT_BUFFER_BEFORE_MINUTES,
    DEFAULT_BUFFER_AFTER_MINUTES,
    DEFAULT_MIN_NOTICE_HOURS,
)
from routes.scheduler._core import get_models

logger = logging.getLogger(__name__)


# ============================================================================
# PERF-008: TTL CACHE FOR SCHEDULER CONFIG LOOKUPS
# ============================================================================
# SchedulerConfig rarely changes (LO updates settings once then forgets).
# Caching for 5 minutes avoids a DB query per slot-request / timezone lookup.

_CONFIG_TTL = 300  # 5 minutes

# Cache structure: {f"{org_id}:{user_id}": {"config": <SchedulerConfig|None>, "ts": float}}
_scheduler_config_cache: dict = {}


def get_cached_scheduler_config(db: Session, user_id: int, org_id: int):
    """
    Get SchedulerConfig with a simple TTL cache.

    Returns the cached SchedulerConfig ORM object (or None) if the cache
    entry is fresh. Otherwise queries the DB, caches the result, and returns it.

    PERF-008: Eliminates redundant DB queries when multiple endpoints
    (timezone lookup, slot generation, public booking) need the same config
    within a short window.
    """
    cache_key = f"{org_id}:{user_id}"
    cached = _scheduler_config_cache.get(cache_key)
    if cached and time_mod.time() - cached["ts"] < _CONFIG_TTL:
        return cached["config"]

    _models = get_models()
    SchedulerConfig = _models.get('SchedulerConfig') if _models else None
    config = None
    if SchedulerConfig and user_id:
        config = db.query(SchedulerConfig).filter(
            SchedulerConfig.user_id == user_id,
            SchedulerConfig.organization_id == org_id,
        ).first()

    _scheduler_config_cache[cache_key] = {"config": config, "ts": time_mod.time()}
    return config


def invalidate_scheduler_config_cache(user_id: int = None, org_id: int = None):
    """Invalidate cached SchedulerConfig entries.

    Called when settings are updated to ensure fresh data on next read.
    If both user_id and org_id are provided, only that specific entry is cleared.
    If neither is provided, the entire cache is cleared.
    """
    if user_id is not None and org_id is not None:
        _scheduler_config_cache.pop(f"{org_id}:{user_id}", None)
    else:
        _scheduler_config_cache.clear()


# ============================================================================
# CIRCUIT BREAKER FOR EXTERNAL CALENDAR SOURCES
# ============================================================================
# Simple circuit breaker: after CIRCUIT_BREAKER_THRESHOLD consecutive failures
# for a provider, skip checks for CIRCUIT_BREAKER_TIMEOUT_SECONDS.
# When the timeout expires, allow one probe request through.

CIRCUIT_BREAKER_THRESHOLD = 5
CIRCUIT_BREAKER_TIMEOUT_SECONDS = 60

# Module-level state: provider -> {"failure_count": int, "open_until": datetime|None}
_circuit_breaker_state: dict = {}


def _cb_record_success(provider: str):
    """Record a successful call — resets the circuit breaker for this provider."""
    state = _circuit_breaker_state.get(provider)
    if state and (state["failure_count"] > 0 or state["open_until"] is not None):
        logger.info(f"Circuit breaker CLOSED for {provider} after successful call")
    _circuit_breaker_state[provider] = {"failure_count": 0, "open_until": None}


def _cb_record_failure(provider: str):
    """Record a failed call — may open the circuit breaker."""
    if provider not in _circuit_breaker_state:
        _circuit_breaker_state[provider] = {"failure_count": 0, "open_until": None}
    state = _circuit_breaker_state[provider]
    state["failure_count"] += 1
    if state["failure_count"] >= CIRCUIT_BREAKER_THRESHOLD:
        open_until = datetime.now(timezone.utc) + timedelta(seconds=CIRCUIT_BREAKER_TIMEOUT_SECONDS)
        state["open_until"] = open_until
        logger.warning(
            f"Circuit breaker OPEN for {provider} after {state['failure_count']} consecutive failures. "
            f"Skipping checks until {open_until.isoformat()}"
        )


def _cb_should_skip(provider: str) -> bool:
    """Check if the circuit breaker is open and the call should be skipped.

    Returns True if the provider should be skipped (circuit open and timeout
    not yet expired). When the timeout has expired, allows one probe request
    through (returns False) and resets the failure count so the next failure
    will re-open the circuit quickly.
    """
    state = _circuit_breaker_state.get(provider)
    if not state or state["open_until"] is None:
        return False
    now = datetime.now(timezone.utc)
    if now >= state["open_until"]:
        # Timeout expired — allow a probe request through
        logger.info(f"Circuit breaker for {provider} timeout expired, allowing probe request")
        state["failure_count"] = CIRCUIT_BREAKER_THRESHOLD - 1  # one more failure re-opens
        state["open_until"] = None
        return False
    return True


# ============================================================================
# TIMEZONE HELPERS
# ============================================================================

def _get_user_timezone(db, user_id: int, org_id: int = None) -> str:
    """Get user's configured timezone from SchedulerConfig, defaulting to America/Chicago.
    Scoped by org_id to prevent cross-tenant config exposure.

    PERF-008: Uses TTL-cached SchedulerConfig lookup to avoid a DB query
    on every call (timezone is checked per-slot in some code paths).
    """
    if user_id and org_id is not None:
        config = get_cached_scheduler_config(db, user_id, org_id)
        if config and getattr(config, 'timezone', None):
            return config.timezone
    return 'America/Chicago'


def _convert_utc_to_user_tz(
    utc_datetime: datetime,
    user_id: int,
    db,
    org_id: int = None,
) -> datetime:
    """Convert a UTC datetime to the user's configured timezone.

    Centralizes timezone conversion logic to prevent DST edge-case bugs
    from divergent implementations across endpoints.
    """
    user_tz_name = _get_user_timezone(db, user_id, org_id)
    tz = pytz.timezone(user_tz_name)
    if utc_datetime.tzinfo is None:
        utc_datetime = utc_datetime.replace(tzinfo=pytz.UTC)
    return utc_datetime.astimezone(tz)


# ============================================================================
# CROSS-SOURCE CONFLICT DETECTION
# ============================================================================

def _get_cross_source_conflicts(db, target_user_id: int, start_dt, end_dt, org_id: int = None):
    """
    Gather all busy time blocks from all 3 calendar sources for a user.
    Returns a tuple of (conflicts, degraded_sources) where:
      - conflicts is a list of (start, end) tuples representing occupied time
      - degraded_sources is a list of source names that failed to query

    When a source query fails, we fail CLOSED: the entire requested time range
    is added as a conflict for that source, so no slots can be booked during
    a period where we cannot verify availability.

    org_id filtering is ALWAYS applied for tenant isolation.
    """
    if org_id is None:
        raise ValueError("org_id is required")
    _models = get_models()
    conflicts = []
    degraded_sources = []

    # Source 1: v2 Appointment (scheduler_appointments) -- canonical table
    if _models and _models.get('Appointment'):
        try:
            V2Appt = _models['Appointment']
            v2_query = db.query(V2Appt).filter(
                V2Appt.assigned_user_id == target_user_id,
                V2Appt.status.in_([AppointmentStatus.BOOKED, AppointmentStatus.TENTATIVE]),
                V2Appt.scheduled_start >= start_dt,
                V2Appt.scheduled_start <= end_dt
            )
            v2_query = v2_query.filter(V2Appt.organization_id == org_id)
            v2_appts = v2_query.all()
            for a in v2_appts:
                if a.scheduled_start and a.scheduled_end:
                    conflicts.append((a.scheduled_start, a.scheduled_end))
        except Exception as e:
            logger.error(f"v2 Appointment cross-source check FAILED for user {target_user_id} — failing closed: {e}")
            degraded_sources.append("v2_appointment")
            conflicts.append((start_dt, end_dt))

    # Source 1b: Legacy ScheduledAppointment (scheduled_appointments) -- deprecated, kept for backward compat
    try:
        from services.smart_scheduler_service import ScheduledAppointment as SAModel
        sa_query = db.query(SAModel).filter(
            SAModel.loan_officer_id == target_user_id,
            SAModel.status.in_(["scheduled", "confirmed"]),
            SAModel.start_time >= start_dt,
            SAModel.start_time <= end_dt
        )
        sa_query = sa_query.filter(SAModel.organization_id == org_id)
        sa_appts = sa_query.all()
        for a in sa_appts:
            if a.start_time and a.end_time:
                conflicts.append((a.start_time, a.end_time))
    except Exception as e:
        # Legacy source — import failures are expected if table doesn't exist;
        # only fail closed on actual query errors (not ImportError)
        if isinstance(e, ImportError):
            logger.warning(f"Legacy ScheduledAppointment cross-source check skipped (not installed): {e}")
        else:
            logger.error(f"Legacy ScheduledAppointment cross-source check FAILED for user {target_user_id} — failing closed: {e}")
            degraded_sources.append("legacy_appointment")
            conflicts.append((start_dt, end_dt))

    # Source 2: CalendarEvent (manual calendar entries)
    if _cb_should_skip("calendar_event"):
        logger.debug(f"CalendarEvent check skipped for user {target_user_id} — circuit breaker open")
        degraded_sources.append("calendar_event")
    else:
        try:
            from database.models.communication import CalendarEvent
            cal_query = db.query(CalendarEvent).filter(
                CalendarEvent.user_id == target_user_id,
                CalendarEvent.status != "cancelled",
                CalendarEvent.start_time >= start_dt,
                CalendarEvent.start_time <= end_dt
            )
            cal_query = cal_query.filter(CalendarEvent.organization_id == org_id)
            cal_events = cal_query.all()
            for e in cal_events:
                if e.start_time and e.end_time:
                    conflicts.append((e.start_time, e.end_time))
            _cb_record_success("calendar_event")
        except Exception as ex:
            if isinstance(ex, ImportError):
                logger.warning(f"CalendarEvent cross-source check skipped (not installed): {ex}")
            else:
                logger.error(f"CalendarEvent cross-source check FAILED for user {target_user_id} — failing closed: {ex}")
                _cb_record_failure("calendar_event")
                degraded_sources.append("calendar_event")
                conflicts.append((start_dt, end_dt))

    # Source 3: CRMCalendarEvent (Salesforce-synced events)
    if _cb_should_skip("crm_calendar_event"):
        logger.debug(f"CRMCalendarEvent check skipped for user {target_user_id} — circuit breaker open")
        degraded_sources.append("crm_calendar_event")
    else:
        try:
            from models.calendar_sync_models import CRMCalendarEvent
            crm_query = db.query(CRMCalendarEvent).filter(
                CRMCalendarEvent.owner_user_id == target_user_id,
                CRMCalendarEvent.status != "canceled",
                CRMCalendarEvent.start_at >= start_dt,
                CRMCalendarEvent.start_at <= end_dt
            )
            crm_query = crm_query.filter(CRMCalendarEvent.organization_id == org_id)
            crm_events = crm_query.all()
            for e in crm_events:
                if e.start_at and e.end_at:
                    conflicts.append((e.start_at, e.end_at))
            _cb_record_success("crm_calendar_event")
        except Exception as ex:
            if isinstance(ex, ImportError):
                logger.warning(f"CRMCalendarEvent cross-source check skipped (not installed): {ex}")
            else:
                logger.error(f"CRMCalendarEvent cross-source check FAILED for user {target_user_id} — failing closed: {ex}")
                _cb_record_failure("crm_calendar_event")
                degraded_sources.append("crm_calendar_event")
                conflicts.append((start_dt, end_dt))

    return conflicts, degraded_sources


def _has_cross_source_conflict(conflicts, slot_start, slot_end, buffer_before=0, buffer_after=0):
    """Check if a proposed slot conflicts with any cross-source busy time."""
    for busy_start, busy_end in conflicts:
        buffered_start = busy_start - timedelta(minutes=buffer_before)
        buffered_end = busy_end + timedelta(minutes=buffer_after)
        if slot_start < buffered_end and slot_end > buffered_start:
            return True
    return False


def _get_cross_source_conflicts_batch(db, user_ids: list, start_dt, end_dt, org_id: int = None):
    """
    Batch-load cross-source conflicts for ALL users at once.

    Returns a tuple of (conflicts_by_user, degraded_sources) where:
      - conflicts_by_user is a dict mapping user_id -> list of (start, end) tuples
      - degraded_sources is a list of source names that failed to query

    When a source query fails, we fail CLOSED: the entire requested time range
    is added as a conflict for ALL users in the batch, so no slots can be
    booked during a period where we cannot verify availability.

    This replaces N calls to _get_cross_source_conflicts() with a fixed
    number of queries regardless of user count.
    org_id filtering is ALWAYS applied for tenant isolation.
    """
    _models = get_models()
    conflicts_by_user = defaultdict(list)
    degraded_sources = []

    def _fail_closed_all_users(source_name):
        """Mark the entire time range as conflicted for all users."""
        degraded_sources.append(source_name)
        for uid in user_ids:
            conflicts_by_user[uid].append((start_dt, end_dt))

    # Source 1: v2 Appointment (scheduler_appointments) -- canonical table
    if _models and _models.get('Appointment'):
        try:
            V2Appt = _models['Appointment']
            v2_query = db.query(V2Appt).filter(
                V2Appt.assigned_user_id.in_(user_ids),
                V2Appt.status.in_([AppointmentStatus.BOOKED, AppointmentStatus.TENTATIVE]),
                V2Appt.scheduled_start >= start_dt,
                V2Appt.scheduled_start <= end_dt
            )
            v2_query = v2_query.filter(V2Appt.organization_id == org_id)
            for a in v2_query.all():
                if a.scheduled_start and a.scheduled_end:
                    conflicts_by_user[a.assigned_user_id].append(
                        (a.scheduled_start, a.scheduled_end)
                    )
        except Exception as e:
            logger.error(f"v2 Appointment batch cross-source check FAILED — failing closed for all users: {e}")
            _fail_closed_all_users("v2_appointment")

    # Source 1b: Legacy ScheduledAppointment (scheduled_appointments) -- deprecated
    try:
        from services.smart_scheduler_service import ScheduledAppointment as SAModel
        sa_query = db.query(SAModel).filter(
            SAModel.loan_officer_id.in_(user_ids),
            SAModel.status.in_(["scheduled", "confirmed"]),
            SAModel.start_time >= start_dt,
            SAModel.start_time <= end_dt
        )
        sa_query = sa_query.filter(SAModel.organization_id == org_id)
        for a in sa_query.all():
            if a.start_time and a.end_time:
                conflicts_by_user[a.loan_officer_id].append(
                    (a.start_time, a.end_time)
                )
    except Exception as e:
        if isinstance(e, ImportError):
            logger.warning(f"Legacy ScheduledAppointment batch cross-source check skipped (not installed): {e}")
        else:
            logger.error(f"Legacy ScheduledAppointment batch cross-source check FAILED — failing closed for all users: {e}")
            _fail_closed_all_users("legacy_appointment")

    # Source 2: CalendarEvent (manual calendar entries)
    if _cb_should_skip("calendar_event"):
        logger.debug("CalendarEvent batch check skipped — circuit breaker open")
        degraded_sources.append("calendar_event")
    else:
        try:
            from database.models.communication import CalendarEvent
            cal_query = db.query(CalendarEvent).filter(
                CalendarEvent.user_id.in_(user_ids),
                CalendarEvent.status != "cancelled",
                CalendarEvent.start_time >= start_dt,
                CalendarEvent.start_time <= end_dt
            )
            cal_query = cal_query.filter(CalendarEvent.organization_id == org_id)
            for e in cal_query.all():
                if e.start_time and e.end_time:
                    conflicts_by_user[e.user_id].append(
                        (e.start_time, e.end_time)
                    )
            _cb_record_success("calendar_event")
        except Exception as ex:
            if isinstance(ex, ImportError):
                logger.warning(f"CalendarEvent batch cross-source check skipped (not installed): {ex}")
            else:
                logger.error(f"CalendarEvent batch cross-source check FAILED — failing closed for all users: {ex}")
                _cb_record_failure("calendar_event")
                _fail_closed_all_users("calendar_event")

    # Source 3: CRMCalendarEvent (Salesforce-synced events)
    if _cb_should_skip("crm_calendar_event"):
        logger.debug("CRMCalendarEvent batch check skipped — circuit breaker open")
        degraded_sources.append("crm_calendar_event")
    else:
        try:
            from models.calendar_sync_models import CRMCalendarEvent
            crm_query = db.query(CRMCalendarEvent).filter(
                CRMCalendarEvent.owner_user_id.in_(user_ids),
                CRMCalendarEvent.status != "canceled",
                CRMCalendarEvent.start_at >= start_dt,
                CRMCalendarEvent.start_at <= end_dt
            )
            crm_query = crm_query.filter(CRMCalendarEvent.organization_id == org_id)
            for e in crm_query.all():
                if e.start_at and e.end_at:
                    conflicts_by_user[e.owner_user_id].append(
                        (e.start_at, e.end_at)
                    )
            _cb_record_success("crm_calendar_event")
        except Exception as ex:
            if isinstance(ex, ImportError):
                logger.warning(f"CRMCalendarEvent batch cross-source check skipped (not installed): {ex}")
            else:
                logger.error(f"CRMCalendarEvent batch cross-source check FAILED — failing closed for all users: {ex}")
                _cb_record_failure("crm_calendar_event")
                _fail_closed_all_users("crm_calendar_event")

    return conflicts_by_user, degraded_sources


# ============================================================================
# UNIFIED SLOT GENERATION ENGINE
# ============================================================================

def _generate_available_slots(
    db: Session,
    user_ids: list,
    start_date: date,
    end_date: date,
    duration_minutes: int = DEFAULT_APPOINTMENT_DURATION_MINUTES,
    org_id: int = None,
    max_per_day: int = None,
    check_cross_source: bool = True,
    include_user_id: bool = False,
    include_day_name: bool = False,
    time_key_format: str = "start",  # "start"->{start,end} or "start_time"->{start_time,end_time}
    exclude_appointment_id: int = None,  # Exclude from conflict check (for rescheduling)
) -> list:
    """
    Unified slot generator used by all availability endpoints.

    This is a synchronous function. It is safe to call from async FastAPI
    endpoints because the DB session is obtained via ``Depends(get_db)``
    which runs in a threadpool, and FastAPI transparently awaits sync
    ``def`` dependencies when they are injected into ``async def`` route
    handlers.  No manual ``run_in_executor`` wrapping is needed.

    Computes available time slots for one or more users by checking:
    - Working hours from SchedulerConfig
    - Blocked times
    - Existing appointments (with buffers)
    - Cross-source calendar conflicts (if enabled)
    - Lunch break (if configured)
    - Minimum notice period
    - Max meetings per day (if set)

    Returns a sorted list of slot dicts. Key names controlled by params:
      time_key_format="start"      -> {"start": ..., "end": ...}
      time_key_format="start_time" -> {"start_time": ...Z, "end_time": ...Z}

    NOTE: Availability Source of Truth
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    This function implements a two-tier availability lookup with precedence:

    1. **RecurringAvailability tables** (preferred): If a user has ANY active rows
       in the `recurring_availability` table, those structured patterns are used
       as the availability source. The RecurringAvailabilityService.get_effective_schedule()
       method merges weekly patterns with AvailabilityException overrides for each date.
       Lunch breaks are handled natively via gaps between blocks (no separate enforcement).

    2. **SchedulerConfig.working_hours JSON** (fallback): If no RecurringAvailability
       rows exist for the user, the function falls back to the `working_hours` JSON
       blob on SchedulerConfig. In this mode, lunch break enforcement uses the
       separate lunch_break_start/lunch_break_end columns on SchedulerConfig.

    IMPORTANT: These two systems can contain DIFFERENT data simultaneously. There is
    currently no automatic sync between them:
    - PUT /settings/availability updates SchedulerConfig.working_hours JSON only.
    - PUT /recurring-availability/schedule updates RecurringAvailability tables only.

    Once a user has RecurringAvailability rows, the JSON blob is effectively ignored
    by this slot generator, but the settings UI may still display/edit the JSON blob
    without the user realizing it has no effect on slot generation.
    """
    # Lightweight cleanup: expire any stale active SlotHold records so they
    # don't phantom-block slots.  This is a single UPDATE on an indexed column
    # and adds negligible latency.  See H9 in challenge audit.
    try:
        from routes.scheduler.maintenance import auto_cleanup_expired_holds
        auto_cleanup_expired_holds(db)
    except Exception:
        # Never let cleanup failure block availability queries
        logger.debug("SlotHold auto-cleanup skipped (non-critical)", exc_info=True)

    _models = get_models()
    SchedulerConfig = _models.get('SchedulerConfig') if _models else None
    BlockedTime = _models.get('BlockedTime') if _models else None
    Appointment = _models.get('Appointment') if _models else None

    if not SchedulerConfig or not BlockedTime or not Appointment:
        logger.error("Scheduler models not available for slot generation")
        return []

    # Validate date range
    if start_date > end_date:
        raise HTTPException(status_code=400, detail="start_date must be before or equal to end_date")
    if (end_date - start_date).days > 90:
        raise HTTPException(status_code=400, detail="Date range cannot exceed 90 days")

    now = datetime.now(timezone.utc).replace(tzinfo=None)  # naive UTC -- consistent with datetime.combine() outputs
    start_dt = datetime.combine(start_date, time.min)
    end_dt = datetime.combine(end_date, time.max)
    all_slots = []

    # ---------------------------------------------------------------
    # BATCH LOAD: Fetch data for ALL users upfront to avoid N+1 queries.
    # With 5 users over 30 days, this reduces ~175 queries to ~5-10.
    # ---------------------------------------------------------------

    # Batch 1: SchedulerConfig for all users
    config_query = db.query(SchedulerConfig).filter(
        SchedulerConfig.user_id.in_(user_ids)
    )
    config_query = config_query.filter(SchedulerConfig.organization_id == org_id)
    all_configs = config_query.all()
    config_by_user = {c.user_id: c for c in all_configs}

    # Batch 2: BlockedTime for all users in the date range
    # Include both user-specific blocks AND applies_to_all_users blocks
    blocked_query = db.query(BlockedTime).filter(
        BlockedTime.is_active == True,
        or_(
            BlockedTime.user_id.in_(user_ids),
            BlockedTime.applies_to_all_users == True
        ),
        BlockedTime.start_datetime <= end_dt,
        BlockedTime.end_datetime >= start_dt
    )
    blocked_query = blocked_query.filter(BlockedTime.organization_id == org_id)
    all_blocked = blocked_query.all()
    # Build per-user blocked times: user-specific + applies_to_all
    global_blocks = [bt for bt in all_blocked if getattr(bt, 'applies_to_all_users', False)]
    user_specific_blocks = defaultdict(list)
    for bt in all_blocked:
        if not getattr(bt, 'applies_to_all_users', False) and bt.user_id is not None:
            user_specific_blocks[bt.user_id].append(bt)
    # Merge: each user gets their own blocks + global blocks
    blocked_by_user = {}
    for uid in user_ids:
        blocked_by_user[uid] = user_specific_blocks.get(uid, []) + global_blocks

    # Batch 3: Existing appointments for all users in the date range
    appt_query = db.query(Appointment).filter(
        Appointment.assigned_user_id.in_(user_ids),
        Appointment.status.in_([
            AppointmentStatus.BOOKED, AppointmentStatus.TENTATIVE,
            AppointmentStatus.CONFIRMED, AppointmentStatus.REMINDED,
            AppointmentStatus.CHECKED_IN,
        ]),
        Appointment.scheduled_start >= start_dt,
        Appointment.scheduled_start <= end_dt
    )
    appt_query = appt_query.filter(Appointment.organization_id == org_id)
    if exclude_appointment_id:
        appt_query = appt_query.filter(Appointment.id != exclude_appointment_id)
    all_appts = appt_query.all()
    appts_by_user = defaultdict(list)
    for appt in all_appts:
        appts_by_user[appt.assigned_user_id].append(appt)

    # Batch 4: Cross-source conflicts for all users
    # _get_cross_source_conflicts_batch returns (conflicts_by_user, degraded_sources).
    # If any source fails, it fails CLOSED: the entire time range is marked as
    # conflicted for all affected users, preventing double-bookings.
    if check_cross_source:
        cross_source_by_user, degraded_sources = _get_cross_source_conflicts_batch(
            db, user_ids, start_dt, end_dt, org_id=org_id
        )
        if degraded_sources:
            logger.error(
                f"Cross-source availability DEGRADED — failed sources: {degraded_sources}. "
                f"Slots overlapping the failed sources' time range will be marked unavailable "
                f"(fail-closed). Users affected: {user_ids}"
            )
    else:
        cross_source_by_user = {}
        degraded_sources = []

    # Batch 5: Check recurring availability for all users (one query via service)
    # PERF-009: Single batched query replaces N per-user queries
    _ra_service = None
    _users_with_recurring = set()
    try:
        from services.recurring_availability_service import RecurringAvailabilityService
        _ra_service = RecurringAvailabilityService(db)
        _recurring_by_user = _ra_service.get_weekly_schedule_batch(user_ids, org_id)
        for uid, _ra_check in _recurring_by_user.items():
            if _ra_check:
                _users_with_recurring.add(uid)
                # C4 fix: Log when both availability sources have data
                uid_config = config_by_user.get(uid)
                if uid_config and getattr(uid_config, 'working_hours', None):
                    json_wh = uid_config.working_hours
                    has_json_data = any(
                        v.get("enabled", False) for v in json_wh.values()
                        if isinstance(v, dict)
                    ) if isinstance(json_wh, dict) else False
                    if has_json_data:
                        logger.warning(
                            "DUAL_AVAILABILITY_SOURCE: user %s has both RecurringAvailability "
                            "rows (%d) and SchedulerConfig.working_hours JSON. Using "
                            "RecurringAvailability as primary source.",
                            uid, len(_ra_check)
                        )
    except Exception as e:
        logger.debug(f"RecurringAvailability not available, using JSON working_hours: {e}")
        _ra_service = None

    # C4 fix: Track which availability source is active per user
    availability_source_by_user = {}
    for uid in user_ids:
        if uid in _users_with_recurring:
            availability_source_by_user[uid] = "recurring_availability"
        else:
            availability_source_by_user[uid] = "scheduler_config_json"

    # H7 fix: Batch-load all AvailabilityException rows for users with recurring
    # availability, covering the entire date range. This replaces the per-date
    # query inside get_effective_schedule() (N+1 -> 1 query).
    _exceptions_by_user_date = {}  # (user_id, date) -> [exception, ...]
    if _ra_service and _users_with_recurring:
        try:
            from database.models.recurring_availability import AvailabilityException
            exc_query = db.query(AvailabilityException).filter(
                AvailabilityException.user_id.in_(list(_users_with_recurring)),
                AvailabilityException.organization_id == org_id,
                AvailabilityException.date >= start_date,
                AvailabilityException.date <= end_date,
            )
            for exc in exc_query.all():
                key = (exc.user_id, exc.date)
                if key not in _exceptions_by_user_date:
                    _exceptions_by_user_date[key] = []
                _exceptions_by_user_date[key].append(exc)
        except Exception as e:
            logger.debug(f"Failed to batch-load AvailabilityExceptions, falling back to per-date queries: {e}")
            _exceptions_by_user_date = None  # Signal to skip preloading

    # ---------------------------------------------------------------
    # PER-USER LOOP: Use pre-loaded data instead of individual queries
    # ---------------------------------------------------------------

    for user_id in user_ids:
        # Use pre-loaded config
        config = config_by_user.get(user_id)

        working_hours = config.working_hours if config else DEFAULT_WORKING_HOURS
        buffer_before = config.buffer_before_minutes if config else DEFAULT_BUFFER_BEFORE_MINUTES
        buffer_after = config.buffer_after_minutes if config else DEFAULT_BUFFER_AFTER_MINUTES
        min_notice = config.min_notice_hours if config else DEFAULT_MIN_NOTICE_HOURS
        user_max_per_day = max_per_day or (config.max_meetings_per_day if config else None)
        enforce_lunch = getattr(config, 'enforce_lunch_break', True) if config else True
        lunch_start_time = getattr(config, 'lunch_break_start', time(12, 0)) if config else time(12, 0)
        lunch_end_time = getattr(config, 'lunch_break_end', time(13, 0)) if config else time(13, 0)

        min_booking_time = now + timedelta(hours=min_notice)

        # Use pre-loaded data
        blocked_times = blocked_by_user.get(user_id, [])
        existing_appts = appts_by_user.get(user_id, [])
        cross_source_busy = cross_source_by_user.get(user_id, [])

        # Determine if user has recurring availability (takes precedence over JSON working_hours)
        _recurring_schedule = _ra_service if user_id in _users_with_recurring else None

        # Generate slots day by day
        current_date = start_date
        while current_date <= end_date:
            day_name = current_date.strftime("%A").lower()

            # If recurring availability is configured, use it instead of JSON working_hours
            if _recurring_schedule:
                # H7 fix: Pass preloaded exceptions to avoid per-date DB query
                _preloaded = None
                if _exceptions_by_user_date is not None:
                    _preloaded = _exceptions_by_user_date.get((user_id, current_date), [])
                effective_blocks = _recurring_schedule.get_effective_schedule(
                    user_id, org_id, current_date, preloaded_exceptions=_preloaded
                )
                if not effective_blocks:
                    current_date += timedelta(days=1)
                    continue
                # Use the first and last block to define the working window
                # (individual blocks are respected in the slot generation below)
                day_hours = {"enabled": True, "start": effective_blocks[0]["start"], "end": effective_blocks[-1]["end"]}
            else:
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
                    slot_start += timedelta(minutes=duration_minutes)
                    continue

                # Skip lunch break (only for JSON working_hours fallback;
                # recurring availability handles lunch via gaps between blocks natively)
                if not _recurring_schedule and lunch_start and lunch_end and slot_start < lunch_end and slot_end > lunch_start:
                    slot_start += timedelta(minutes=duration_minutes)
                    continue

                # When recurring availability is active, verify slot falls within an effective block
                if _recurring_schedule and effective_blocks:
                    in_block = False
                    for blk in effective_blocks:
                        blk_start = datetime.combine(current_date, datetime.strptime(blk["start"], "%H:%M").time())
                        blk_end = datetime.combine(current_date, datetime.strptime(blk["end"], "%H:%M").time())
                        if slot_start >= blk_start and slot_end <= blk_end:
                            in_block = True
                            break
                    if not in_block:
                        slot_start += timedelta(minutes=duration_minutes)
                        continue

                # Check blocked times
                is_blocked = any(
                    slot_start < bt.end_datetime and slot_end > bt.start_datetime
                    for bt in blocked_times
                )
                if is_blocked:
                    slot_start += timedelta(minutes=duration_minutes)
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
                    # C4 fix: Include which availability source produced this slot
                    slot["availability_source"] = availability_source_by_user.get(user_id, "scheduler_config_json")
                    if include_user_id:
                        slot["user_id"] = user_id
                    if include_day_name:
                        slot["day"] = day_name
                    all_slots.append(slot)

                slot_start += timedelta(minutes=duration_minutes)

            current_date += timedelta(days=1)

    # Deduplicate and sort
    # NC1 fix: Use composite key (time, user_id) when include_user_id is set,
    # so slots for different users at the same time are preserved.
    sort_key = "start_time" if time_key_format == "start_time" else "start"
    if include_user_id:
        unique_slots = list({(s[sort_key], s.get("user_id")): s for s in all_slots}.values())
    else:
        unique_slots = list({s[sort_key]: s for s in all_slots}.values())
    unique_slots.sort(key=lambda x: x[sort_key])
    return unique_slots
