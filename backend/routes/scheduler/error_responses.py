"""
Standardized error responses for all scheduler endpoints.

Provides a consistent error format across appointments, settings, public booking,
and other scheduler sub-modules:

    {
        "error": "Human-readable error summary",
        "code": "VALIDATION_ERROR",
        "detail": "Technical detail (non-production only)",
        "timestamp": "2026-03-18T12:34:56.789Z"
    }

The `detail` field is only included in non-production environments to aid debugging
without leaking internals to end users.

Usage:
    from routes.scheduler.error_responses import (
        scheduler_error, validation_error, not_found_error,
        conflict_error, rate_limit_error, internal_error,
        forbidden_error, unauthorized_error, service_unavailable_error,
    )

    # Raise helpers (raise HTTPException internally):
    validation_error("name is required")
    not_found_error("Appointment not found")
    conflict_error("Time slot already booked")

    # Or use the generic form:
    scheduler_error(400, VALIDATION_ERROR, "Invalid status",
                    detail=f"Got '{value}', expected one of: {allowed}")
"""

import os
import logging
from datetime import datetime, timezone

from fastapi import HTTPException
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

# ============================================================================
# ENVIRONMENT DETECTION
# ============================================================================

_RAILWAY_ENVIRONMENT = os.getenv("RAILWAY_ENVIRONMENT", "")
_IS_PRODUCTION = _RAILWAY_ENVIRONMENT.lower() == "production"


def _is_production() -> bool:
    """Check if running in production environment."""
    return _IS_PRODUCTION


def _utc_timestamp() -> str:
    """Return current UTC timestamp in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat()


# ============================================================================
# ERROR CODES
# ============================================================================

# Validation / input errors
VALIDATION_ERROR = "VALIDATION_ERROR"

# Resource errors
NOT_FOUND = "NOT_FOUND"
CONFLICT = "APPOINTMENT_CONFLICT"
SLOT_UNAVAILABLE = "SLOT_UNAVAILABLE"

# Auth / permission errors
FORBIDDEN = "FORBIDDEN"
UNAUTHORIZED = "UNAUTHORIZED"

# Rate limiting
RATE_LIMITED = "RATE_LIMITED"

# Server / initialization errors
INTERNAL_ERROR = "INTERNAL_ERROR"
SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"

# Settings-specific
INVALID_SECTION = "INVALID_SECTION"
IMPORT_ERROR = "IMPORT_ERROR"
RESET_ERROR = "RESET_ERROR"


# ============================================================================
# ERROR BODY BUILDER
# ============================================================================

def _build_error_body(
    error: str,
    code: str,
    detail: str = None,
) -> dict:
    """
    Build the standardized error response body.

    Always includes: error, code, timestamp.
    Conditionally includes: detail (non-production only).

    Args:
        error: Human-readable error message safe for end users.
        code: Machine-readable error code (e.g. VALIDATION_ERROR).
        detail: Optional technical detail (suppressed in production).

    Returns:
        dict suitable for JSONResponse or HTTPException detail.
    """
    body = {
        "error": error,
        "code": code,
        "timestamp": _utc_timestamp(),
    }
    if detail and not _is_production():
        body["detail"] = detail
    return body


# ============================================================================
# CORE ERROR FUNCTION (raises HTTPException)
# ============================================================================

def scheduler_error(
    status_code: int,
    error_code: str,
    message: str,
    detail: str = None,
) -> None:
    """
    Raise a standardized HTTPException for scheduler endpoints.

    The response body always includes 'error' (human-readable), 'code'
    (machine-readable), and 'timestamp'.  The 'detail' field with technical
    specifics is only included in non-production environments.

    Args:
        status_code: HTTP status code (400, 403, 404, 409, 422, 500, etc.)
        error_code: Machine-readable error code (e.g. VALIDATION_ERROR)
        message: Human-readable message safe for end users
        detail: Optional technical detail (suppressed in production)

    Raises:
        HTTPException with a structured detail body.
    """
    body = _build_error_body(error=message, code=error_code, detail=detail)
    raise HTTPException(status_code=status_code, detail=body)


# ============================================================================
# CONVENIENCE HELPERS -- each raises HTTPException with proper status code
# ============================================================================

def validation_error(message: str, detail: str = None) -> None:
    """Raise a 400 validation error.

    Use for invalid input, missing required fields, bad format, etc.
    """
    scheduler_error(400, VALIDATION_ERROR, message, detail=detail)


def not_found_error(message: str, detail: str = None) -> None:
    """Raise a 404 not-found error.

    Use when a requested resource (appointment, label, booking link, etc.)
    does not exist or is not accessible to the caller.
    """
    scheduler_error(404, NOT_FOUND, message, detail=detail)


def conflict_error(message: str, detail: str = None) -> None:
    """Raise a 409 conflict error.

    Use for scheduling conflicts, duplicate resources, or state-transition
    violations (e.g. trying to activate a test when one is already active).
    """
    scheduler_error(409, CONFLICT, message, detail=detail)


def rate_limit_error(message: str = "Too many requests. Please try again later.", detail: str = None) -> None:
    """Raise a 429 rate-limit error.

    Use when a caller exceeds the allowed request rate.
    """
    scheduler_error(429, RATE_LIMITED, message, detail=detail)


def internal_error(message: str = "An unexpected error occurred.", detail: str = None) -> None:
    """Raise a 500 internal server error.

    Use for unexpected failures. The detail is suppressed in production.
    """
    scheduler_error(500, INTERNAL_ERROR, message, detail=detail)


def forbidden_error(message: str = "Admin access required", detail: str = None) -> None:
    """Raise a 403 forbidden error.

    Use when the user lacks permission for the requested action.
    """
    scheduler_error(403, FORBIDDEN, message, detail=detail)


def unauthorized_error(message: str = "Authentication required", detail: str = None) -> None:
    """Raise a 401 unauthorized error.

    Use when authentication is missing or invalid (expired token, etc.).
    """
    scheduler_error(401, UNAUTHORIZED, message, detail=detail)


def service_unavailable_error(message: str = "Service temporarily unavailable", detail: str = None) -> None:
    """Raise a 503 service-unavailable error.

    Use when a required subsystem (scheduler models, external service) is
    not initialized or unreachable.
    """
    scheduler_error(503, SERVICE_UNAVAILABLE, message, detail=detail)


# ============================================================================
# JSONResponse BUILDERS (for cases where you need to return, not raise)
# ============================================================================

def error_json_response(
    status_code: int,
    error_code: str,
    message: str,
    detail: str = None,
) -> JSONResponse:
    """
    Return a JSONResponse with the standardized error body.

    Use this instead of scheduler_error() when you need to return an error
    response directly (e.g. inside try/except blocks in public endpoints
    that catch HTTPException and re-wrap).

    Args:
        status_code: HTTP status code.
        error_code: Machine-readable error code.
        message: Human-readable error message.
        detail: Optional technical detail (suppressed in production).

    Returns:
        JSONResponse with the error body and correct status code.
    """
    body = _build_error_body(error=message, code=error_code, detail=detail)
    return JSONResponse(status_code=status_code, content=body)


# ============================================================================
# __all__
# ============================================================================

__all__ = [
    # Error codes
    "VALIDATION_ERROR",
    "NOT_FOUND",
    "CONFLICT",
    "SLOT_UNAVAILABLE",
    "FORBIDDEN",
    "UNAUTHORIZED",
    "RATE_LIMITED",
    "INTERNAL_ERROR",
    "SERVICE_UNAVAILABLE",
    "INVALID_SECTION",
    "IMPORT_ERROR",
    "RESET_ERROR",
    # Core function
    "scheduler_error",
    # Convenience helpers (raise HTTPException)
    "validation_error",
    "not_found_error",
    "conflict_error",
    "rate_limit_error",
    "internal_error",
    "forbidden_error",
    "unauthorized_error",
    "service_unavailable_error",
    # JSONResponse builder
    "error_json_response",
    # Utilities
    "_build_error_body",
    "_is_production",
]
