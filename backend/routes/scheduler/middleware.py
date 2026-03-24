"""
Scheduler middleware, exception classes, and standard response models.

Contains:
  - Request timing middleware (logs slow scheduler requests with correlation IDs)
  - API version middleware (reads/writes X-API-Version header)
  - Deprecation decorator (adds Deprecation, Sunset, Link headers per RFC 8594)
  - Endpoint version registry
  - Correlated logger factory for scheduler modules
  - Standard error/success response models for consistent API responses
  - Scheduler-specific exception hierarchy (inherits from PerenniaError)
  - Exception handler to convert SchedulerExceptions to HTTP responses
"""

import time
import logging
import functools
from datetime import datetime, timezone
from email.utils import format_datetime
from typing import Optional, List, Dict

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as StarletteRequest
from starlette.responses import Response

from exceptions import PerenniaError

# Re-export correlation ID accessors from the platform-wide request context
# middleware.  The RequestContextMiddleware (outermost middleware) sets these
# contextvars on every request; scheduler code can import them from here
# instead of reaching into middleware.request_context directly.
from middleware.request_context import (
    get_request_id,
    get_user_id as _get_ctx_user_id,
    get_org_id as _get_ctx_org_id,
)

logger = logging.getLogger("scheduler.performance")
deprecation_logger = logging.getLogger("scheduler.deprecation")


# ============================================================================
# CORRELATED LOGGER
# ============================================================================

class _CorrelatedLoggerAdapter(logging.LoggerAdapter):
    """LoggerAdapter that injects the current request_id into every log record.

    Reads the correlation ID from the platform-wide contextvar set by
    ``RequestContextMiddleware``.  The request_id appears both in the
    ``extra`` dict (for structured logging / JSON formatters) and is
    prepended to the message string (for plain-text formatters).

    Usage::

        from routes.scheduler.middleware import get_correlated_logger
        logger = get_correlated_logger(__name__)
        logger.info("Booking created for %s", borrower_email)
        # => "[req=a1b2c3d4] Booking created for jane@example.com"
    """

    def process(self, msg, kwargs):
        request_id = get_request_id() or "no-request-id"
        extra = kwargs.get("extra", {})
        extra["request_id"] = request_id
        kwargs["extra"] = extra
        return f"[req={request_id[:12]}] {msg}", kwargs


def get_correlated_logger(name: str) -> _CorrelatedLoggerAdapter:
    """Create a logger that automatically includes the request correlation ID.

    This is the recommended way for scheduler modules to create loggers::

        from routes.scheduler.middleware import get_correlated_logger
        logger = get_correlated_logger(__name__)

    The returned adapter wraps a standard ``logging.Logger`` so all normal
    methods (info, warning, error, exception, debug) work as expected.  The
    request_id is injected at call time from the contextvar, so it is always
    correct even under concurrent async requests.
    """
    return _CorrelatedLoggerAdapter(logging.getLogger(name), {})


# ============================================================================
# REQUEST TIMING MIDDLEWARE
# ============================================================================

_SLOW_REQUEST_THRESHOLD_MS = 1000


class SchedulerTimingMiddleware(BaseHTTPMiddleware):
    """Middleware that measures and logs request duration for scheduler endpoints.

    Adds an X-Scheduler-Duration-Ms header to every response.
    Logs a warning for requests exceeding the slow threshold (default 1000ms).

    Includes the platform-wide correlation ID (request_id) plus user_id and
    organization_id (when available from auth middleware) in all log entries
    for cross-referencing with the request context logs.
    """

    async def dispatch(self, request: StarletteRequest, call_next) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000

        if duration_ms > _SLOW_REQUEST_THRESHOLD_MS:
            # Pull tracing context from the platform-wide contextvars
            request_id = get_request_id() or "unknown"
            user_id = _get_ctx_user_id()
            org_id = _get_ctx_org_id()

            logger.warning(
                "Slow scheduler request: %s %s took %.0fms "
                "request_id=%s user_id=%s org_id=%s",
                request.method,
                request.url.path,
                duration_ms,
                request_id,
                user_id or "-",
                org_id or "-",
            )

        response.headers["X-Scheduler-Duration-Ms"] = f"{duration_ms:.0f}"
        return response


async def scheduler_timing_middleware(request: Request, call_next):
    """Functional middleware variant for use with app.middleware("http").

    Logs request duration for scheduler endpoints and sets a response header.
    Includes correlation ID (request_id), user_id, and organization_id in
    slow-request warnings.
    """
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000

    if duration_ms > _SLOW_REQUEST_THRESHOLD_MS:
        request_id = get_request_id() or "unknown"
        user_id = _get_ctx_user_id()
        org_id = _get_ctx_org_id()

        logger.warning(
            "Slow scheduler request: %s %s took %.0fms "
            "request_id=%s user_id=%s org_id=%s",
            request.method,
            request.url.path,
            duration_ms,
            request_id,
            user_id or "-",
            org_id or "-",
        )

    response.headers["X-Scheduler-Duration-Ms"] = f"{duration_ms:.0f}"
    return response


# ============================================================================
# API VERSION CONSTANTS
# ============================================================================

# Current API version -- updated with each release cycle
CURRENT_API_VERSION = "2026-03"

# Supported versions (oldest to newest).  Requests with versions older than
# the earliest entry are still served but receive a warning header.
SUPPORTED_API_VERSIONS = ["2025-06", "2025-12", "2026-03"]


# ============================================================================
# ENDPOINT VERSION REGISTRY
# ============================================================================

ENDPOINT_VERSIONS: Dict[str, Dict[str, str]] = {
    # Appointments
    "/api/v1/scheduler/appointments": {"introduced": "2025-06", "current": "2026-03"},
    "/api/v1/scheduler/appointments/{appointment_id}": {"introduced": "2025-06", "current": "2026-03"},
    "/api/v1/scheduler/appointments/{appointment_id}/cancel": {"introduced": "2025-06", "current": "2026-03"},
    "/api/v1/scheduler/appointments/{appointment_id}/timeline": {"introduced": "2025-06", "current": "2026-03"},
    # Availability
    "/api/v1/scheduler/available-slots": {"introduced": "2025-06", "current": "2026-03"},
    "/api/v1/scheduler/availability/schedule": {"introduced": "2026-03", "current": "2026-03"},
    "/api/v1/scheduler/availability/effective": {"introduced": "2026-03", "current": "2026-03"},
    # Booking links
    "/api/v1/scheduler/booking-links": {"introduced": "2025-06", "current": "2026-03"},
    "/api/v1/scheduler/booking-links/all": {"introduced": "2025-06", "current": "2026-03"},
    # Blocked times
    "/api/v1/scheduler/blocked-times": {"introduced": "2025-06", "current": "2026-03"},
    # AI scheduling
    "/api/v1/scheduler/ai-recommend-slots": {"introduced": "2025-12", "current": "2026-03"},
    "/api/v1/scheduler/analytics/no-show-risks": {"introduced": "2025-12", "current": "2026-03"},
    # Public booking
    "/api/v1/scheduler/public/available-slots": {"introduced": "2025-06", "current": "2026-03"},
    "/api/v1/scheduler/public/book/{slug}/confirm": {"introduced": "2025-06", "current": "2026-03"},
    # Search
    "/api/v1/scheduler/search": {"introduced": "2025-12", "current": "2026-03"},
    "/api/v1/scheduler/search/suggestions": {"introduced": "2025-12", "current": "2026-03"},
    # Analytics
    "/api/v1/scheduler/analytics/overview": {"introduced": "2026-03", "current": "2026-03"},
    "/api/v1/scheduler/analytics/trends": {"introduced": "2026-03", "current": "2026-03"},
    "/api/v1/scheduler/analytics/by-type": {"introduced": "2026-03", "current": "2026-03"},
    "/api/v1/scheduler/analytics/by-lo": {"introduced": "2026-03", "current": "2026-03"},
    # Settings
    "/api/v1/scheduler/settings/all": {"introduced": "2025-06", "current": "2026-03"},
    # Today summary
    "/api/v1/scheduler/today-summary": {"introduced": "2026-03", "current": "2026-03"},
    # Waitlist
    "/api/v1/scheduler/waitlist": {"introduced": "2026-03", "current": "2026-03"},
    # Calendar feed
    "/api/v1/scheduler/feed/subscribe": {"introduced": "2026-03", "current": "2026-03"},
    # Surveys
    "/api/v1/scheduler/surveys": {"introduced": "2026-03", "current": "2026-03"},
    # Labels
    "/api/v1/scheduler/labels": {"introduced": "2026-03", "current": "2026-03"},
    # Reschedule
    "/api/v1/scheduler/reschedule/{appointment_id}": {"introduced": "2026-03", "current": "2026-03"},
    # Notifications
    "/api/v1/scheduler/notifications": {"introduced": "2026-03", "current": "2026-03"},
    # Locations
    "/api/v1/scheduler/locations": {"introduced": "2026-03", "current": "2026-03"},
    # Conflicts
    "/api/v1/scheduler/conflicts": {"introduced": "2026-03", "current": "2026-03"},
    # A/B testing
    "/api/v1/scheduler/ab-tests": {"introduced": "2026-03", "current": "2026-03"},
    # Cancellation policy
    "/api/v1/scheduler/cancellation-policy": {"introduced": "2026-03", "current": "2026-03"},
    # Meetings
    "/api/v1/scheduler/meetings/settings": {"introduced": "2026-03", "current": "2026-03"},
    # Reminders
    "/api/v1/scheduler/reminders/templates": {"introduced": "2026-03", "current": "2026-03"},
    # Templates
    "/api/v1/scheduler/templates": {"introduced": "2026-03", "current": "2026-03"},
    # Version introspection
    "/api/v1/scheduler/api-versions": {"introduced": "2026-03", "current": "2026-03"},
}


# ============================================================================
# API VERSION MIDDLEWARE
# ============================================================================

class SchedulerAPIVersionMiddleware(BaseHTTPMiddleware):
    """Reads the requested API version from headers, defaults to current.

    Reads from ``X-API-Version`` or ``Accept-Version`` (X-API-Version takes
    precedence).  Sets ``X-API-Version`` on the response so clients can
    confirm which version was used.

    The resolved version string is stashed in ``request.state.api_version``
    for downstream route handlers to inspect if needed.
    """

    async def dispatch(self, request: StarletteRequest, call_next) -> Response:
        # Read requested version -- prefer X-API-Version, fall back to Accept-Version
        api_version = (
            request.headers.get("X-API-Version")
            or request.headers.get("Accept-Version")
            or CURRENT_API_VERSION
        )

        # Stash on request.state for route handlers
        request.state.api_version = api_version

        response = await call_next(request)

        # Always echo the resolved version back
        response.headers["X-API-Version"] = api_version

        return response


async def scheduler_api_version_middleware(request: Request, call_next):
    """Functional middleware variant for use with app.middleware("http").

    Reads X-API-Version / Accept-Version, defaults to current, and sets
    X-API-Version on the response.
    """
    api_version = (
        request.headers.get("X-API-Version")
        or request.headers.get("Accept-Version")
        or CURRENT_API_VERSION
    )
    request.state.api_version = api_version

    response = await call_next(request)
    response.headers["X-API-Version"] = api_version
    return response


# ============================================================================
# DEPRECATION DECORATOR
# ============================================================================

def _format_sunset_date(date_str: str) -> str:
    """Convert an ISO date string (e.g. '2026-09-01') to an RFC 7231 HTTP-date.

    Example output: ``Sat, 01 Sep 2026 00:00:00 GMT``
    """
    dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return format_datetime(dt, usegmt=True)


def deprecated_endpoint(
    sunset_date: str,
    replacement: Optional[str] = None,
):
    """Decorator that marks a route handler as deprecated.

    Adds the following response headers per RFC 8594:
      - ``Deprecation: true``
      - ``Sunset: <RFC 7231 date>``       (when the endpoint will be removed)
      - ``Link: <replacement>; rel="successor-version"``  (if a replacement is given)

    Also logs a warning on every invocation so usage can be tracked.

    Usage::

        @router.get("/old-endpoint")
        @deprecated_endpoint(sunset_date="2026-09-01", replacement="/api/v1/scheduler/new-endpoint")
        async def old_endpoint(...):
            ...
    """
    sunset_http_date = _format_sunset_date(sunset_date)

    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract request from args/kwargs so we can log the caller
            request: Optional[Request] = kwargs.get("request")
            if request is None:
                for arg in args:
                    if isinstance(arg, (Request, StarletteRequest)):
                        request = arg
                        break

            user_id = "anonymous"
            if request is not None:
                user = getattr(request.state, "user", None)
                if user is not None:
                    user_id = getattr(user, "id", "unknown")

                path = request.url.path
            else:
                path = getattr(func, "__name__", "unknown")

            deprecation_logger.warning(
                "Deprecated endpoint %s called by user %s",
                path,
                user_id,
            )

            # Call the original handler
            response = await func(*args, **kwargs)

            # If the handler returned a Response, inject headers directly
            if isinstance(response, Response):
                response.headers["Deprecation"] = "true"
                response.headers["Sunset"] = sunset_http_date
                if replacement:
                    response.headers["Link"] = f'<{replacement}>; rel="successor-version"'
                return response

            # If the handler returned a dict/model (auto-serialized by FastAPI),
            # we cannot add headers here -- FastAPI wraps it into a JSONResponse
            # after the handler returns.  To handle this, wrap it in a JSONResponse
            # with the headers set.
            from fastapi.encoders import jsonable_encoder

            content = jsonable_encoder(response)
            json_response = JSONResponse(content=content)
            json_response.headers["Deprecation"] = "true"
            json_response.headers["Sunset"] = sunset_http_date
            if replacement:
                json_response.headers["Link"] = f'<{replacement}>; rel="successor-version"'
            return json_response

        # Preserve OpenAPI metadata so FastAPI docs show a deprecation note
        wrapper.__deprecated__ = True

        return wrapper
    return decorator


# ============================================================================
# STANDARD RESPONSE MODELS
# ============================================================================

class SchedulerErrorDetail(BaseModel):
    """Detail about a specific field-level or validation error."""

    field: Optional[str] = None
    message: str
    code: str


class SchedulerErrorResponse(BaseModel):
    """Standard error response for all scheduler endpoints."""

    error: str
    code: str
    details: Optional[List[SchedulerErrorDetail]] = None
    request_id: Optional[str] = None


class SchedulerSuccessResponse(BaseModel):
    """Standard success wrapper for scheduler endpoints."""

    success: bool = True
    message: Optional[str] = None
    data: Optional[dict] = None


# ============================================================================
# SCHEDULER EXCEPTION HIERARCHY
# ============================================================================

class SchedulerException(PerenniaError):
    """Base exception for the scheduler module.

    Inherits from PerenniaError so that the global exception handler in
    error_handling.py can catch it alongside other domain exceptions.
    Each subclass specifies a default HTTP status code for the exception
    handler below.
    """

    def __init__(
        self,
        message: str,
        code: str = "SCHEDULER_ERROR",
        status_code: int = 400,
    ):
        self.status_code = status_code
        super().__init__(message, code=code)


class SlotUnavailableError(SchedulerException):
    """Raised when a requested time slot is no longer available (booked by another user)."""

    def __init__(self, message: str = "The requested time slot is no longer available"):
        super().__init__(message, code="SLOT_UNAVAILABLE", status_code=409)


class BookingRateLimitError(SchedulerException):
    """Raised when a client exceeds the booking attempt rate limit."""

    def __init__(self, message: str = "Too many booking attempts. Please try again later."):
        super().__init__(message, code="RATE_LIMITED", status_code=429)


class SchedulerConfigError(SchedulerException):
    """Raised when the scheduler encounters a configuration problem (missing settings, etc.)."""

    def __init__(self, message: str = "Scheduler configuration error"):
        super().__init__(message, code="CONFIG_ERROR", status_code=500)


class CalendarConflictError(SchedulerException):
    """Raised when a calendar conflict is detected during booking or rescheduling."""

    def __init__(self, message: str = "Calendar conflict detected"):
        super().__init__(message, code="CALENDAR_CONFLICT", status_code=409)


# ============================================================================
# EXCEPTION HANDLER
# ============================================================================

async def scheduler_exception_handler(request: Request, exc: SchedulerException) -> JSONResponse:
    """Convert a SchedulerException into a structured JSON error response.

    Includes the correlation ID so that clients can reference it in support
    tickets and engineers can grep logs by request_id.

    Register with FastAPI via:
        app.add_exception_handler(SchedulerException, scheduler_exception_handler)
    """
    request_id = get_request_id()
    return JSONResponse(
        status_code=exc.status_code,
        content=SchedulerErrorResponse(
            error=exc.message,
            code=exc.code,
            request_id=request_id,
        ).dict(),
    )


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    # Middleware
    "SchedulerTimingMiddleware",
    "scheduler_timing_middleware",
    # API versioning middleware
    "SchedulerAPIVersionMiddleware",
    "scheduler_api_version_middleware",
    # API versioning constants & registry
    "CURRENT_API_VERSION",
    "SUPPORTED_API_VERSIONS",
    "ENDPOINT_VERSIONS",
    # Deprecation decorator
    "deprecated_endpoint",
    # Correlation / request tracing
    "get_request_id",
    "get_correlated_logger",
    # Response models
    "SchedulerErrorDetail",
    "SchedulerErrorResponse",
    "SchedulerSuccessResponse",
    # Exceptions
    "SchedulerException",
    "SlotUnavailableError",
    "BookingRateLimitError",
    "SchedulerConfigError",
    "CalendarConflictError",
    # Handler
    "scheduler_exception_handler",
]
