"""
Mobile Error Response Utilities

Provides a consistent error response format for mobile clients (iOS Capacitor app).
Mobile clients are identified by User-Agent containing "Perennia" or "Capacitor".

This is a utility module — route handlers import and use these helpers directly.
It does NOT wrap all responses as middleware (too invasive).

Usage:
    from middleware.mobile_error_handler import mobile_error, MobileErrorCode, is_mobile_client

    @router.get("/example")
    async def example(request: Request):
        if not item:
            raise mobile_error(MobileErrorCode.ENTITY_NOT_FOUND, "Lead not found")

    # Or use the JSONResponse builder directly:
    from middleware.mobile_error_handler import mobile_error_response

    return mobile_error_response(
        code=MobileErrorCode.VALIDATION_ERROR,
        message="Invalid stage value",
        status_code=422,
        details={"field": "stage", "allowed": ["New", "PROCESSING"]},
    )
"""

import enum
import logging
from typing import Any, Dict, Optional

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


class MobileErrorCode(str, enum.Enum):
    """Standardized error codes for mobile clients.

    Mobile apps use these codes for programmatic error handling
    (retry logic, offline queue management, auth refresh, etc.).
    """
    ENTITY_NOT_FOUND = "ENTITY_NOT_FOUND"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    AUTH_EXPIRED = "AUTH_EXPIRED"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    RATE_LIMITED = "RATE_LIMITED"
    CONFLICT = "CONFLICT"
    SERVER_ERROR = "SERVER_ERROR"
    SYNC_CONFLICT = "SYNC_CONFLICT"
    OFFLINE_QUEUE_FULL = "OFFLINE_QUEUE_FULL"


# Map error codes to default HTTP status codes
_DEFAULT_STATUS_CODES: Dict[MobileErrorCode, int] = {
    MobileErrorCode.ENTITY_NOT_FOUND: 404,
    MobileErrorCode.VALIDATION_ERROR: 422,
    MobileErrorCode.AUTH_EXPIRED: 401,
    MobileErrorCode.AUTH_REQUIRED: 401,
    MobileErrorCode.RATE_LIMITED: 429,
    MobileErrorCode.CONFLICT: 409,
    MobileErrorCode.SERVER_ERROR: 500,
    MobileErrorCode.SYNC_CONFLICT: 409,
    MobileErrorCode.OFFLINE_QUEUE_FULL: 413,
}


def is_mobile_client(request: Request) -> bool:
    """Check if the request comes from a Perennia mobile client.

    Looks for "Perennia" or "Capacitor" in the User-Agent header.
    """
    user_agent = request.headers.get("user-agent", "")
    return "Perennia" in user_agent or "Capacitor" in user_agent


def mobile_error_body(
    code: MobileErrorCode,
    message: str,
    retry_after: Optional[int] = None,
    details: Optional[Dict[str, Any]] = None,
) -> dict:
    """Build the standardized mobile error body.

    Returns:
        {
            "error": {
                "code": "ENTITY_NOT_FOUND",
                "message": "Lead not found",
                "retry_after": null,
                "details": {}
            }
        }
    """
    return {
        "error": {
            "code": code.value if isinstance(code, MobileErrorCode) else code,
            "message": message,
            "retry_after": retry_after,
            "details": details or {},
        }
    }


def mobile_error_response(
    code: MobileErrorCode,
    message: str,
    status_code: Optional[int] = None,
    retry_after: Optional[int] = None,
    details: Optional[Dict[str, Any]] = None,
) -> JSONResponse:
    """Build a JSONResponse with the standardized mobile error format.

    Args:
        code: One of the MobileErrorCode enum values.
        message: Human-readable error description.
        status_code: HTTP status code. Defaults based on error code.
        retry_after: Seconds the client should wait before retrying (for rate limits).
        details: Additional context for the error.

    Returns:
        FastAPI JSONResponse with consistent error structure.
    """
    if status_code is None:
        status_code = _DEFAULT_STATUS_CODES.get(code, 500)

    headers = {}
    if retry_after is not None:
        headers["Retry-After"] = str(retry_after)

    return JSONResponse(
        status_code=status_code,
        content=mobile_error_body(code, message, retry_after, details),
        headers=headers or None,
    )


def mobile_error(
    code: MobileErrorCode,
    message: str,
    status_code: Optional[int] = None,
    retry_after: Optional[int] = None,
    details: Optional[Dict[str, Any]] = None,
) -> HTTPException:
    """Build an HTTPException with the standardized mobile error format.

    Raises an HTTPException whose detail is the mobile error dict, so
    FastAPI's default exception handler serializes it as JSON.

    Usage:
        raise mobile_error(MobileErrorCode.ENTITY_NOT_FOUND, "Lead not found")
    """
    if status_code is None:
        status_code = _DEFAULT_STATUS_CODES.get(code, 500)

    body = mobile_error_body(code, message, retry_after, details)

    headers = {}
    if retry_after is not None:
        headers["Retry-After"] = str(retry_after)

    return HTTPException(
        status_code=status_code,
        detail=body,
        headers=headers or None,
    )


__all__ = [
    "MobileErrorCode",
    "is_mobile_client",
    "mobile_error",
    "mobile_error_body",
    "mobile_error_response",
]
