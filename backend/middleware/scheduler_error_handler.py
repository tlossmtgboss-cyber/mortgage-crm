"""
Perennia AI - Centralized Scheduler Exception Handler

Maps SchedulerError subclasses from `exceptions.py` to consistent JSON
error responses.  Each SchedulerError carries its own `status_code` and
`code`, so a single handler covers the entire hierarchy.

Response format (matches the domain error_response.py pattern):

    {
        "success": false,
        "error": {
            "code": "APPOINTMENT_NOT_FOUND",
            "message": "Appointment with id '42' not found",
            "details": {},
            "status": 404
        }
    }

Usage:
    from middleware.scheduler_error_handler import register_scheduler_error_handlers
    register_scheduler_error_handlers(app)
"""

import logging
import os
import traceback

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from exceptions import SchedulerError

logger = logging.getLogger(__name__)


# =============================================================================
# HELPERS
# =============================================================================

def _is_production() -> bool:
    """Check if running in production environment."""
    return bool(
        os.getenv("RAILWAY_ENVIRONMENT")
        or os.getenv("ENVIRONMENT") == "production"
    )


def _record_to_ring_buffer(request: Request, exc: Exception):
    """Record error to the ring buffer if available."""
    try:
        from utils.error_handling import _record_error
        _record_error(
            method=request.method,
            path=request.url.path,
            error_type=type(exc).__name__,
            error_msg=str(exc),
            tb=traceback.format_exc(),
        )
    except ImportError:
        pass


# =============================================================================
# PUBLIC ENDPOINT ERROR SANITIZATION
# =============================================================================

_SAFE_PUBLIC_MESSAGES = {
    400: "Invalid booking request. Please check your information and try again.",
    403: "This action is not allowed.",
    404: "Booking page not found.",
    409: "This time slot has already been booked. Please select another time.",
    410: "This booking link is no longer available.",
    422: "Invalid request data.",
    429: "Too many requests. Please wait a moment and try again.",
}


def _is_public_path(request: Request) -> bool:
    """Check whether the request targets a public (unauthenticated) scheduler endpoint."""
    path = request.url.path
    return "/public/" in path or "/book/" in path


def _sanitize_for_public(status_code: int, message: str, request: Request) -> str:
    """Return a safe message for public endpoints; pass-through for authenticated ones."""
    if _is_public_path(request) and _is_production():
        return _SAFE_PUBLIC_MESSAGES.get(status_code, "Something went wrong. Please try again later.")
    return message


# =============================================================================
# HANDLER
# =============================================================================

async def scheduler_exception_handler(request: Request, exc: SchedulerError) -> JSONResponse:
    """
    Centralized error handler for all SchedulerError subclasses.

    - 5xx errors are logged at ERROR with full traceback.
    - 4xx errors are logged at INFO (expected client errors).
    - Public endpoints get sanitized messages in production.
    - All errors are recorded to the ring buffer for diagnostics.
    """
    status_code = exc.status_code

    # Logging: severity depends on status code
    if status_code >= 500:
        logger.error(
            "Scheduler error: %s - %s [%s %s]",
            exc.code, exc.message, request.method, request.url.path,
            exc_info=True,
        )
        _record_to_ring_buffer(request, exc)
    else:
        logger.info(
            "Scheduler error: %s - %s [%s %s]",
            exc.code, exc.message, request.method, request.url.path,
        )

    # Sanitize message for public endpoints
    client_message = _sanitize_for_public(status_code, exc.message, request)

    # Build response body
    body = {
        "success": False,
        "error": {
            "code": exc.code,
            "message": client_message,
            "details": exc.details if not (_is_public_path(request) and _is_production()) else {},
            "status": status_code,
        },
    }

    # Add Retry-After header for rate limit errors
    headers = {}
    retry_after = exc.details.get("retry_after") if exc.details else None
    if retry_after is not None:
        headers["Retry-After"] = str(retry_after)

    return JSONResponse(
        status_code=status_code,
        content=body,
        headers=headers if headers else None,
    )


# =============================================================================
# REGISTRATION
# =============================================================================

def register_scheduler_error_handlers(app: FastAPI):
    """
    Register the centralized scheduler exception handler with FastAPI.

    Because SchedulerError is the base class, this single handler catches
    all scheduler exception subclasses (AppointmentNotFoundError,
    AppointmentConflictError, etc.).  FastAPI dispatches to the most
    specific exception handler first, so existing PerenniaError handlers
    are not affected.
    """
    app.add_exception_handler(SchedulerError, scheduler_exception_handler)
    logger.info("Scheduler exception handler registered (SchedulerError hierarchy)")
