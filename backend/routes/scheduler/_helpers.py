"""
Scheduler shared helpers - common utilities used across all scheduler sub-modules.

Contains:
  - Dependency injection storage and wiring
  - Auth helpers (get_current_user, _get_org_id, _is_scheduler_admin)
  - Rate limiting (Redis with in-memory fallback)
  - Input sanitization (_sanitize_text, _mask_email, _validate_url, _sanitize_public_error)
  - Cloudflare Turnstile verification
  - Audit logging
  - Cross-source conflict detection (all 3 calendar sources)
  - Appointment conflict checking (SELECT FOR UPDATE)
  - Duplicate booking detection
  - CRM integration helpers (lead creation, activity logging, task creation, LO licensing)
  - Unified slot generation engine
  - User timezone lookup
"""

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from datetime import datetime, timedelta, date, time, timezone
from typing import List, Optional
import pytz
from collections import OrderedDict, defaultdict, deque
import asyncio
import html
import ipaddress
import logging
import os
import time as _time

try:
    import nh3
except ImportError:
    nh3 = None

from smart_scheduler_models import (
    AppointmentStatus, DayOfWeek, SlotPriority, DEFAULT_WORKING_HOURS,
)
from routes.scheduler.constants import (
    DEFAULT_APPOINTMENT_DURATION_MINUTES,
    DEFAULT_BUFFER_BEFORE_MINUTES,
    DEFAULT_BUFFER_AFTER_MINUTES,
    DEFAULT_MIN_NOTICE_HOURS,
)

logger = logging.getLogger(__name__)


# ============================================================================
# DEPENDENCY INJECTION STORAGE
# ============================================================================

_get_db = None
_get_current_user_func = None
_models = None
_enhanced_models = None


def set_dependencies(get_db_func, get_current_user_func, models_dict):
    """Set core dependencies from parent module."""
    global _get_db, _get_current_user_func, _models
    _get_db = get_db_func
    _get_current_user_func = get_current_user_func
    _models = models_dict


def set_enhanced_dependencies(get_db_func, get_current_user_func, models_dict, enhanced_models_dict):
    """Set dependencies for enhanced scheduler features (resources, soft holds, SLA, etc.)."""
    global _get_db, _get_current_user_func, _models, _enhanced_models
    _get_db = get_db_func
    _get_current_user_func = get_current_user_func
    _models = models_dict
    _enhanced_models = enhanced_models_dict


def get_models():
    """Get models dict (for use by sub-modules)."""
    return _models


def get_enhanced_models():
    """Get enhanced models dict."""
    return _enhanced_models


# ============================================================================
# AUTH HELPERS
# ============================================================================

from db import get_db


async def get_current_user(request: Request, db: Session = Depends(get_db)):
    """Authenticate the current user from the Authorization header."""
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
    Only true security roles qualify -- 'leadership' and 'management' are display titles, not admin grants.
    """
    role = getattr(user, 'permission_role', '') or getattr(user, 'role', '') or ''
    return role.lower() in ('admin', 'site_admin', 'platform_admin')


def _get_user_timezone(db, user_id: int, org_id: int = None) -> str:
    """Get user's configured timezone from SchedulerConfig, defaulting to America/Chicago.
    Scoped by org_id to prevent cross-tenant config exposure."""
    SchedulerConfig = _models.get('SchedulerConfig') if _models else None
    if SchedulerConfig and user_id:
        tz_query = db.query(SchedulerConfig).filter(SchedulerConfig.user_id == user_id)
        if org_id:
            tz_query = tz_query.filter(SchedulerConfig.organization_id == org_id)
        config = tz_query.first()
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
# RATE LIMITING (Redis-backed, multi-process safe)
# ============================================================================

_PRIVATE_NETWORKS = (
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
)


def _is_private_ip(ip_str: str) -> bool:
    """Check if an IP address is in a private/internal range (RFC 1918, loopback, ULA)."""
    try:
        addr = ipaddress.ip_address(ip_str)
        return any(addr in net for net in _PRIVATE_NETWORKS)
    except ValueError:
        return False


def _parse_trusted_proxy_cidrs() -> list:
    """Parse TRUSTED_PROXY_CIDRS env var into a list of ipaddress networks.
    Defaults include RFC 1918/loopback ranges (covers Railway, Docker, local dev)
    and Cloudflare's primary IPv4 ranges."""
    default_cidrs = (
        "10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,127.0.0.0/8,"
        "::1/128,fc00::/7,"
        # Cloudflare IPv4 ranges (subset — covers most deployments)
        "173.245.48.0/20,103.21.244.0/22,103.22.200.0/22,103.31.4.0/22,"
        "141.101.64.0/18,108.162.192.0/18,190.93.240.0/20,188.114.96.0/20,"
        "197.234.240.0/22,198.41.128.0/17,162.158.0.0/15,104.16.0.0/13,"
        "104.24.0.0/14,172.64.0.0/13,131.0.72.0/22"
    )
    raw = os.getenv("TRUSTED_PROXY_CIDRS", default_cidrs)
    networks = []
    for cidr in raw.split(","):
        cidr = cidr.strip()
        if not cidr:
            continue
        try:
            networks.append(ipaddress.ip_network(cidr, strict=False))
        except ValueError:
            logger.warning(f"Invalid CIDR in TRUSTED_PROXY_CIDRS, skipping: {cidr}")
    return networks


_TRUSTED_PROXY_CIDRS = _parse_trusted_proxy_cidrs()


def _is_trusted_proxy(ip_str: str) -> bool:
    """Check if an IP address belongs to a trusted proxy network."""
    try:
        addr = ipaddress.ip_address(ip_str)
        return any(addr in net for net in _TRUSTED_PROXY_CIDRS)
    except ValueError:
        return False


def _get_client_ip(request: Request) -> str:
    """
    Extract the real client IP from a request.

    Only trusts X-Forwarded-For when the direct connecting IP (request.client.host)
    belongs to a trusted proxy network (Railway, Cloudflare, or private/internal).
    Uses the rightmost (last) IP in X-Forwarded-For, which is the one appended by
    the closest trusted proxy and is hardest to spoof.
    Falls back to the direct connection IP if the header can't be trusted.
    """
    direct_ip = request.client.host if request.client else "unknown"

    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded and _is_trusted_proxy(direct_ip):
        # Request came through a trusted proxy; use the rightmost (last) IP
        # which was appended by the closest trusted reverse proxy
        ips = [ip.strip() for ip in forwarded.split(",") if ip.strip()]
        if ips:
            return ips[-1]

    return direct_ip


# Rate limit configuration — all tuneable via env vars
_RATE_LIMIT_WINDOW = int(os.getenv("SCHEDULER_RATE_LIMIT_WINDOW", os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60")))
_RATE_LIMIT_MAX_PUBLIC = int(os.getenv("SCHEDULER_RATE_LIMIT_MAX", os.getenv("RATE_LIMIT_MAX_PUBLIC", "10")))
_RATE_LIMIT_MAX_AUTHENTICATED = int(os.getenv("SCHEDULER_RATE_LIMIT_MAX_AUTH", "60"))

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


# In-memory rate limiter fallback when Redis is unavailable
# Uses OrderedDict for LRU-style eviction to bound memory usage.
_memory_rate_limits: OrderedDict = OrderedDict()  # key -> deque of timestamps
_memory_rate_lock = asyncio.Lock()  # asyncio.Lock for async FastAPI context (threading.Lock can deadlock)
_memory_rate_check_count = 0  # Counter for periodic cleanup
_MAX_RATE_LIMIT_KEYS = int(os.getenv("SCHEDULER_RATE_LIMIT_MAX_KEYS", "10000"))
_MEMORY_CLEANUP_INTERVAL = int(os.getenv("SCHEDULER_RATE_LIMIT_CLEANUP_INTERVAL",
                                          os.getenv("RATE_LIMIT_CLEANUP_INTERVAL", "500")))


class _RateLimitCapacityExhausted(Exception):
    """Raised when the in-memory rate limiter has no capacity for new keys."""
    pass


async def _check_memory_rate_limit(key: str, max_requests: int, window_seconds: int = _RATE_LIMIT_WINDOW) -> bool:
    """
    In-memory sliding window rate limit. Returns True if allowed, False if over limit.
    Raises _RateLimitCapacityExhausted if the in-memory store is full and the key is
    not already tracked (cannot safely admit new clients).

    Uses asyncio.Lock for safe use in async FastAPI handlers. Not multi-process safe
    (per-worker protection only).

    Uses an OrderedDict with LRU ordering: accessed keys are moved to the end.
    Periodically purges keys whose timestamp deques are empty. When the store is at
    capacity and a genuinely new key arrives, we raise instead of silently evicting
    -- evicting would destroy rate-limit state for existing clients, effectively
    bypassing protection for rotated IPs.
    """
    global _memory_rate_check_count
    now = _time.time()
    async with _memory_rate_lock:
        # Periodic cleanup first: remove keys with empty deques to free capacity
        _memory_rate_check_count += 1
        if _memory_rate_check_count >= _MEMORY_CLEANUP_INTERVAL:
            _memory_rate_check_count = 0
            empty_keys = [k for k, v in _memory_rate_limits.items() if not v]
            for k in empty_keys:
                del _memory_rate_limits[k]
            if empty_keys:
                logger.debug(f"Rate limiter cleanup: evicted {len(empty_keys)} expired keys")

        if key in _memory_rate_limits:
            timestamps = _memory_rate_limits[key]
            # Move to end (most recently accessed) for LRU ordering
            _memory_rate_limits.move_to_end(key)
        else:
            # New key -- check capacity before inserting.
            # SECURITY: Do NOT silently evict old entries to make room. Evicting
            # destroys rate-limit state for those clients, which means an attacker
            # rotating source IPs could flush legitimate tracking entries and never
            # be rate-limited. Instead, refuse new keys when at capacity.
            if len(_memory_rate_limits) >= _MAX_RATE_LIMIT_KEYS:
                raise _RateLimitCapacityExhausted(
                    f"In-memory rate limiter at capacity ({_MAX_RATE_LIMIT_KEYS} keys). "
                    "Cannot track new clients safely."
                )
            timestamps = deque()
            _memory_rate_limits[key] = timestamps

        # Evict expired timestamps from this key's deque
        while timestamps and timestamps[0] < now - window_seconds:
            timestamps.popleft()
        if len(timestamps) >= max_requests:
            return False
        timestamps.append(now)

        return True


async def _check_rate_limit(request: Request, max_requests: int = _RATE_LIMIT_MAX_PUBLIC, custom_key: str = None):
    """
    Redis-backed rate limiter keyed by client IP + path.
    Falls back to async in-memory rate limiting if Redis is unavailable.

    Args:
        request: The incoming HTTP request (used for IP and path extraction).
        max_requests: Maximum requests allowed in the rate-limit window.
        custom_key: Optional override for the rate-limit key. When provided,
                    this replaces the default ``sched_rl:{path}:{ip}`` key,
                    allowing callers to rate-limit by a different dimension
                    (e.g., per-email or per-action).

    SECURITY RATIONALE: Public booking endpoints (no auth required) are the primary
    consumers of this function. If rate limiting is completely bypassed, these
    endpoints are vulnerable to:
      - Brute-force appointment enumeration and scraping
      - Denial-of-service via booking slot exhaustion
      - Spam booking / resource exhaustion attacks
    Therefore, when Redis is unavailable, we use an in-memory fallback with bounded
    capacity. If the fallback is also exhausted (too many distinct client keys), we
    return HTTP 503 rather than silently allowing unlimited requests. Availability
    is less important than allowing unbounded abuse of public endpoints.
    """
    client_ip = _get_client_ip(request)

    key = custom_key or f"sched_rl:{request.url.path}:{client_ip}"

    r = _get_rate_limit_redis()
    if r is None:
        # Fallback: in-memory rate limiting (per-worker only -- degraded protection).
        # The effective limit is multiplied by worker count since each process has
        # its own in-memory store.
        logger.warning("Rate limiter: Redis unavailable, using per-worker memory fallback. "
                        "Effective limit is multiplied by worker count. Restore Redis ASAP.")
        try:
            if not await _check_memory_rate_limit(key, max_requests):
                raise HTTPException(
                    status_code=429,
                    detail="Too many requests. Please try again later.",
                    headers={"Retry-After": str(_RATE_LIMIT_WINDOW)}
                )
        except _RateLimitCapacityExhausted:
            # SECURITY: In-memory fallback is full and cannot track this new client.
            # Refusing the request (503) is safer than allowing it through unmetered.
            # This scenario indicates Redis has been down long enough for the fallback
            # to accumulate _MAX_RATE_LIMIT_KEYS distinct clients -- an operational
            # emergency that needs immediate attention.
            logger.error(
                "Rate limiter: in-memory fallback capacity exhausted "
                f"({_MAX_RATE_LIMIT_KEYS} keys). Rejecting request with 503. "
                "Restore Redis immediately to resume normal operation."
            )
            raise HTTPException(
                status_code=503,
                detail="Service temporarily unavailable. Please try again later.",
                headers={"Retry-After": "30"}
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
        # Redis command error mid-request -- fall back to in-memory
        logger.warning(f"Rate limit Redis error, using memory fallback: {e}")
        try:
            if not await _check_memory_rate_limit(key, max_requests):
                raise HTTPException(
                    status_code=429,
                    detail="Too many requests. Please try again later.",
                    headers={"Retry-After": str(_RATE_LIMIT_WINDOW)}
                )
        except _RateLimitCapacityExhausted:
            logger.error(
                "Rate limiter: in-memory fallback capacity exhausted "
                f"({_MAX_RATE_LIMIT_KEYS} keys). Rejecting request with 503. "
                "Restore Redis immediately to resume normal operation."
            )
            raise HTTPException(
                status_code=503,
                detail="Service temporarily unavailable. Please try again later.",
                headers={"Retry-After": "30"}
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


def _validate_phone(phone: Optional[str]) -> Optional[str]:
    """
    Validate and normalize phone numbers for public booking.
    Accepts E.164 (+1XXXXXXXXXX) or common US formats (XXX-XXX-XXXX, (XXX) XXX-XXXX, etc.).
    Returns the cleaned phone string, or raises HTTPException for invalid formats.
    """
    import re
    if phone is None or phone.strip() == "":
        return None
    # Strip whitespace and common formatting chars for digit counting
    digits_only = re.sub(r'[^\d]', '', phone.strip())
    # Accept 10-digit US numbers or 11-digit with leading 1, or E.164 with +
    if phone.strip().startswith('+'):
        # E.164: must be + followed by 10-15 digits
        if not re.match(r'^\+\d{10,15}$', phone.strip()):
            raise HTTPException(
                status_code=400,
                detail="Invalid phone number format. Please use a valid phone number."
            )
    elif len(digits_only) == 10:
        pass  # Standard US 10-digit
    elif len(digits_only) == 11 and digits_only.startswith('1'):
        pass  # US with leading country code
    else:
        raise HTTPException(
            status_code=400,
            detail="Invalid phone number format. Please use a valid phone number."
        )
    return phone.strip()


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


# Cloudflare Turnstile secret key
_TURNSTILE_SECRET_KEY = os.getenv("TURNSTILE_SECRET_KEY")
_RAILWAY_ENVIRONMENT = os.getenv("RAILWAY_ENVIRONMENT", "")
_IS_PRODUCTION = _RAILWAY_ENVIRONMENT.lower() == "production"

if _IS_PRODUCTION and not _TURNSTILE_SECRET_KEY:
    logger.critical(
        "TURNSTILE_SECRET_KEY is not set in production! "
        "Public booking endpoints will REJECT all requests until this is configured. "
        "Set the TURNSTILE_SECRET_KEY environment variable with your Cloudflare Turnstile secret."
    )


async def _verify_turnstile_token(token: str) -> bool:
    """
    Verify a Cloudflare Turnstile token by POSTing to Cloudflare's siteverify endpoint.
    Returns True if the token is valid, False otherwise.

    Production safety: if TURNSTILE_SECRET_KEY is not set, returns False in production
    (rejecting the request) and True in dev/test (allowing bypass for local development).
    """
    if not _TURNSTILE_SECRET_KEY:
        if _IS_PRODUCTION:
            logger.error("Turnstile verification rejected: TURNSTILE_SECRET_KEY not configured in production")
            return False
        else:
            logger.debug("Turnstile verification skipped: TURNSTILE_SECRET_KEY not set (dev mode)")
            return True

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
# AUDIT LOGGING
# ============================================================================

def _audit_log(db, org_id: int, user_id: int, action: str, entity_type: str,
               entity_id: int = None, changes: dict = None, request: Request = None,
               booking_source: str = None):
    """Record an audit log entry for scheduler operations.

    Args:
        booking_source: "authenticated", "public_booking", or "ai_pipeline".
    """
    AuditLog = _models.get('SchedulerAuditLog') if _models else None
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
            booking_source=booking_source,
            ip_address=request.client.host if request and request.client else None,
            user_agent=str(request.headers.get('user-agent', ''))[:255] if request else None,
        )
        db.add(entry)
        # Don't commit here -- let the caller's commit include this
    except Exception as e:
        logger.warning(f"Failed to write audit log: {e}")


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
            if org_id:
                v2_query = v2_query.filter(V2Appt.organization_id == org_id)
            v2_appts = v2_query.all()
            for a in v2_appts:
                if a.scheduled_start and a.scheduled_end:
                    conflicts.append((a.scheduled_start, a.scheduled_end))
        except Exception as e:
            logger.warning(f"v2 Appointment cross-source check unavailable: {e}")

    # Source 1b: Legacy ScheduledAppointment (scheduled_appointments) -- deprecated, kept for backward compat
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


def _get_cross_source_conflicts_batch(db, user_ids: list, start_dt, end_dt, org_id: int = None):
    """
    Batch-load cross-source conflicts for ALL users at once.

    Returns a dict mapping user_id -> list of (start, end) tuples.
    This replaces N calls to _get_cross_source_conflicts() with a fixed
    number of queries regardless of user count.
    """
    conflicts_by_user = defaultdict(list)

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
            if org_id:
                v2_query = v2_query.filter(V2Appt.organization_id == org_id)
            for a in v2_query.all():
                if a.scheduled_start and a.scheduled_end:
                    conflicts_by_user[a.assigned_user_id].append(
                        (a.scheduled_start, a.scheduled_end)
                    )
        except Exception as e:
            logger.warning(f"v2 Appointment batch cross-source check unavailable: {e}")

    # Source 1b: Legacy ScheduledAppointment (scheduled_appointments) -- deprecated
    try:
        from services.smart_scheduler_service import ScheduledAppointment as SAModel
        sa_query = db.query(SAModel).filter(
            SAModel.loan_officer_id.in_(user_ids),
            SAModel.status.in_(["scheduled", "confirmed"]),
            SAModel.start_time >= start_dt,
            SAModel.start_time <= end_dt
        )
        if org_id:
            sa_query = sa_query.filter(SAModel.organization_id == org_id)
        for a in sa_query.all():
            if a.start_time and a.end_time:
                conflicts_by_user[a.loan_officer_id].append(
                    (a.start_time, a.end_time)
                )
    except Exception as e:
        logger.debug(f"Legacy ScheduledAppointment batch cross-source check skipped: {e}")

    # Source 2: CalendarEvent (manual calendar entries)
    try:
        from database.models.communication import CalendarEvent
        cal_query = db.query(CalendarEvent).filter(
            CalendarEvent.user_id.in_(user_ids),
            CalendarEvent.status != "cancelled",
            CalendarEvent.start_time >= start_dt,
            CalendarEvent.start_time <= end_dt
        )
        if org_id:
            cal_query = cal_query.filter(CalendarEvent.organization_id == org_id)
        for e in cal_query.all():
            if e.start_time and e.end_time:
                conflicts_by_user[e.user_id].append(
                    (e.start_time, e.end_time)
                )
    except Exception as ex:
        logger.warning(f"CalendarEvent batch cross-source check unavailable: {ex}")

    # Source 3: CRMCalendarEvent (Salesforce-synced events)
    try:
        from models.calendar_sync_models import CRMCalendarEvent
        crm_query = db.query(CRMCalendarEvent).filter(
            CRMCalendarEvent.owner_user_id.in_(user_ids),
            CRMCalendarEvent.status != "canceled",
            CRMCalendarEvent.start_at >= start_dt,
            CRMCalendarEvent.start_at <= end_dt
        )
        if org_id:
            crm_query = crm_query.filter(CRMCalendarEvent.organization_id == org_id)
        for e in crm_query.all():
            if e.start_at and e.end_at:
                conflicts_by_user[e.owner_user_id].append(
                    (e.start_at, e.end_at)
                )
    except Exception as ex:
        logger.warning(f"CRMCalendarEvent batch cross-source check unavailable: {ex}")

    return conflicts_by_user


# ============================================================================
# APPOINTMENT CONFLICT & DUPLICATE DETECTION
# ============================================================================

def _check_appointment_conflict(db, assigned_user_id: int, start_time, end_time,
                                 org_id: int = None, exclude_appointment_id=None):
    """
    Check for overlapping appointments using advisory lock + SELECT FOR UPDATE.
    Raises HTTPException 409 if a conflict is found or rows are locked by another transaction.
    exclude_appointment_id: skip this appointment (used when rescheduling to avoid self-conflict).
    org_id: ALWAYS applied when provided for tenant isolation.

    The advisory lock serializes concurrent booking attempts for the same
    LO + time slot, closing the race window where SELECT FOR UPDATE finds
    no rows to lock (empty slot) and two transactions both INSERT.
    """
    from sqlalchemy.exc import OperationalError
    from sqlalchemy import text as sa_text

    # Acquire a transaction-scoped advisory lock keyed on (user_id, time_slot).
    # This serializes concurrent booking attempts for the same LO + time window.
    # The lock is released automatically when the transaction commits/rollbacks.
    try:
        start_epoch = int(start_time.timestamp()) if hasattr(start_time, 'timestamp') else 0
        lock_key = (assigned_user_id * 1_000_000 + (start_epoch % 1_000_000)) & 0x7FFFFFFFFFFFFFFF
        db.execute(sa_text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_key})
    except Exception as e:
        logger.debug("Advisory lock failed (non-blocking): %s", e)

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
        # Row is locked by another transaction -- treat as conflict
        raise HTTPException(
            status_code=409,
            detail="This time slot is being booked by another user. Please select a different time."
        )
    if conflict:
        raise HTTPException(
            status_code=409,
            detail="This time slot is no longer available. Please select a different time."
        )


def _check_duplicate_booking(db, attendee_email: str, assigned_user_id: int,
                              start_time, org_id: int = None, window_minutes=DEFAULT_APPOINTMENT_DURATION_MINUTES):
    """
    Check for an existing booking with the same attendee_email + same LO
    within +/-window_minutes of the proposed start_time.
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
# CRM INTEGRATION HELPERS
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
    Note: Does NOT commit -- caller owns the transaction boundary."""
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
    C3: Soft check -- verify LO has NMLS number on file.
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

    Migration plan:
    1. Add a sync hook in settings.py _apply_availability() to also write
       RecurringAvailability rows when working_hours JSON is updated.
    2. Add a sync hook in recurring_availability.py update_weekly_schedule() to
       also update SchedulerConfig.working_hours JSON for backward compatibility.
    3. Once all users have RecurringAvailability rows, deprecate the JSON fallback
       path and remove SchedulerConfig.working_hours column.
    4. Update the settings UI to read/write RecurringAvailability directly.
    """
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
    if org_id:
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
    if org_id:
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
        Appointment.status.in_([AppointmentStatus.BOOKED, AppointmentStatus.TENTATIVE]),
        Appointment.scheduled_start >= start_dt,
        Appointment.scheduled_start <= end_dt
    )
    if org_id:
        appt_query = appt_query.filter(Appointment.organization_id == org_id)
    all_appts = appt_query.all()
    appts_by_user = defaultdict(list)
    for appt in all_appts:
        appts_by_user[appt.assigned_user_id].append(appt)

    # Batch 4: Cross-source conflicts for all users
    cross_source_by_user = (
        _get_cross_source_conflicts_batch(db, user_ids, start_dt, end_dt, org_id=org_id)
        if check_cross_source else {}
    )

    # Batch 5: Check recurring availability for all users (one query via service)
    _ra_service = None
    _users_with_recurring = set()
    try:
        from services.recurring_availability_service import RecurringAvailabilityService
        _ra_service = RecurringAvailabilityService(db)
        if org_id:
            for uid in user_ids:
                _ra_check = _ra_service.get_weekly_schedule(uid, org_id)
                if _ra_check:
                    _users_with_recurring.add(uid)
    except Exception as e:
        logger.debug(f"RecurringAvailability not available, using JSON working_hours: {e}")
        _ra_service = None

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
                effective_blocks = _recurring_schedule.get_effective_schedule(user_id, org_id, current_date)
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
                    slot_start += timedelta(minutes=DEFAULT_APPOINTMENT_DURATION_MINUTES)
                    continue

                # Skip lunch break (only when not using recurring availability, which handles gaps natively)
                if not _recurring_schedule and lunch_start and lunch_end and slot_start < lunch_end and slot_end > lunch_start:
                    slot_start += timedelta(minutes=DEFAULT_APPOINTMENT_DURATION_MINUTES)
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
                        slot_start += timedelta(minutes=DEFAULT_APPOINTMENT_DURATION_MINUTES)
                        continue

                # Check blocked times
                is_blocked = any(
                    slot_start < bt.end_datetime and slot_end > bt.start_datetime
                    for bt in blocked_times
                )
                if is_blocked:
                    slot_start += timedelta(minutes=DEFAULT_APPOINTMENT_DURATION_MINUTES)
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

                slot_start += timedelta(minutes=DEFAULT_APPOINTMENT_DURATION_MINUTES)

            current_date += timedelta(days=1)

    # Deduplicate and sort
    sort_key = "start_time" if time_key_format == "start_time" else "start"
    unique_slots = list({s[sort_key]: s for s in all_slots}.values())
    unique_slots.sort(key=lambda x: x[sort_key])
    return unique_slots


# ============================================================================
# HELPERS DICT (for backward-compatible injection into sub-modules)
# ============================================================================

def get_shared_helpers() -> dict:
    """Return a dict of all shared helper functions for sub-module injection."""
    return {
        '_check_appointment_conflict': _check_appointment_conflict,
        '_check_duplicate_booking': _check_duplicate_booking,
        '_log_appointment_activity': _log_appointment_activity,
        '_ensure_lead_for_booking': _ensure_lead_for_booking,
        '_create_followup_task': _create_followup_task,
        '_check_lo_licensing': _check_lo_licensing,
        '_get_user_timezone': _get_user_timezone,
        '_convert_utc_to_user_tz': _convert_utc_to_user_tz,
        '_generate_available_slots': _generate_available_slots,
        '_audit_log': _audit_log,
        '_validate_url': _validate_url,
        '_validate_phone': _validate_phone,
        '_mask_email': _mask_email,
        '_sanitize_text': _sanitize_text,
        '_sanitize_public_error': _sanitize_public_error,
        '_create_comm_failure_task': _create_comm_failure_task,
    }
