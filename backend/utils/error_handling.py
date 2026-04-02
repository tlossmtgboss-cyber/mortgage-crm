"""
Perennia AI - Standardized Error Handling Utilities

This module provides comprehensive error handling for the entire application:
- Custom exception classes with error codes
- Structured error responses
- Exception handler registration for FastAPI
- Logging utilities

Usage:
    from utils.error_handling import (
        ValidationException,
        PermissionException,
        NotFoundException,
        DatabaseException,
        success_response,
        register_exception_handlers
    )
"""

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum
import logging
import traceback

logger = logging.getLogger(__name__)


# =============================================================================
# ERROR RING BUFFER — Captures recent errors for diagnostic access
# =============================================================================
# Stores the last N errors with full stack traces in memory.
# Accessible via /health/recent-errors (no auth required, admin API key recommended).
# This solves the production debugging problem where error_handling.py sanitizes
# 500 responses and Railway logs scroll away quickly.

from collections import deque
import threading

_MAX_RECENT_ERRORS = 50
_recent_errors: deque = deque(maxlen=_MAX_RECENT_ERRORS)
_error_lock = threading.Lock()


def _record_error(method: str, path: str, error_type: str, error_msg: str, tb: str = ""):
    """Record an error to the ring buffer (thread-safe)."""
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "method": method,
        "path": path,
        "error_type": error_type,
        "error_message": str(error_msg)[:500],
        "traceback": tb[:2000] if tb else "",
    }
    with _error_lock:
        _recent_errors.append(entry)


def get_recent_errors(limit: int = 20) -> list:
    """Get the most recent errors (newest first)."""
    with _error_lock:
        errors = list(_recent_errors)
    return list(reversed(errors))[:limit]


# =============================================================================
# ERROR CODES
# =============================================================================

class ErrorCode(str, Enum):
    """Standardized error codes for frontend consumption"""
    # Validation errors (1xxx)
    VALIDATION_ERROR = "VALIDATION_ERROR"
    INVALID_INPUT = "INVALID_INPUT"
    MISSING_FIELD = "MISSING_FIELD"
    INVALID_FORMAT = "INVALID_FORMAT"

    # Authentication/Authorization errors (2xxx)
    UNAUTHORIZED = "UNAUTHORIZED"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    TOKEN_EXPIRED = "TOKEN_EXPIRED"
    INVALID_TOKEN = "INVALID_TOKEN"

    # Resource errors (3xxx)
    NOT_FOUND = "NOT_FOUND"
    ALREADY_EXISTS = "ALREADY_EXISTS"
    CONFLICT = "CONFLICT"
    GONE = "GONE"

    # Database errors (4xxx)
    DATABASE_ERROR = "DATABASE_ERROR"
    TRANSACTION_FAILED = "TRANSACTION_FAILED"
    INTEGRITY_ERROR = "INTEGRITY_ERROR"
    CONNECTION_ERROR = "CONNECTION_ERROR"

    # External service errors (5xxx)
    EXTERNAL_SERVICE_ERROR = "EXTERNAL_SERVICE_ERROR"
    TIMEOUT = "TIMEOUT"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"

    # Business logic errors (6xxx)
    BUSINESS_RULE_VIOLATION = "BUSINESS_RULE_VIOLATION"
    QUOTA_EXCEEDED = "QUOTA_EXCEEDED"
    RATE_LIMITED = "RATE_LIMITED"

    # Server errors (9xxx)
    INTERNAL_ERROR = "INTERNAL_ERROR"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"


# =============================================================================
# CUSTOM EXCEPTIONS
# =============================================================================

class APIException(Exception):
    """Base exception for all API errors"""

    def __init__(
        self,
        message: str,
        code: ErrorCode = ErrorCode.INTERNAL_ERROR,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        details: Optional[Dict[str, Any]] = None,
        field_errors: Optional[Dict[str, str]] = None,
    ):
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}
        self.field_errors = field_errors or {}
        super().__init__(self.message)

    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary for JSON response"""
        result = {
            "success": False,
            "error": {
                "code": self.code.value,
                "message": self.message,
            }
        }

        if self.field_errors:
            result["error"]["field_errors"] = self.field_errors

        if self.details:
            result["error"]["details"] = self.details

        return result


class ValidationException(APIException):
    """Exception for validation errors"""

    def __init__(
        self,
        message: str = "Validation failed",
        field_errors: Optional[Dict[str, str]] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            message=message,
            code=ErrorCode.VALIDATION_ERROR,
            status_code=status.HTTP_400_BAD_REQUEST,
            details=details,
            field_errors=field_errors,
        )


class PermissionException(APIException):
    """Exception for permission denied errors"""

    def __init__(
        self,
        message: str = "You don't have permission to perform this action",
        required_permission: Optional[str] = None,
    ):
        details = {}
        if required_permission:
            details["required_permission"] = required_permission

        super().__init__(
            message=message,
            code=ErrorCode.PERMISSION_DENIED,
            status_code=status.HTTP_403_FORBIDDEN,
            details=details,
        )


class NotFoundException(APIException):
    """Exception for resource not found errors"""

    def __init__(
        self,
        message: str = "Resource not found",
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
    ):
        details = {}
        if resource_type:
            details["resource_type"] = resource_type
        if resource_id:
            details["resource_id"] = resource_id

        super().__init__(
            message=message,
            code=ErrorCode.NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            details=details,
        )


class ConflictException(APIException):
    """Exception for resource conflict errors"""

    def __init__(
        self,
        message: str = "Resource already exists",
        conflict_field: Optional[str] = None,
    ):
        details = {}
        if conflict_field:
            details["conflict_field"] = conflict_field

        super().__init__(
            message=message,
            code=ErrorCode.ALREADY_EXISTS,
            status_code=status.HTTP_409_CONFLICT,
            details=details,
        )


class DatabaseException(APIException):
    """Exception for database errors"""

    def __init__(
        self,
        message: str = "A database error occurred. Please try again.",
        original_error: Optional[str] = None,
    ):
        details = {}
        if original_error:
            # Don't expose internal details in production
            details["internal_ref"] = hash(original_error) % 100000

        super().__init__(
            message=message,
            code=ErrorCode.DATABASE_ERROR,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            details=details,
        )


class ExternalServiceException(APIException):
    """Exception for external service errors"""

    def __init__(
        self,
        message: str = "External service error",
        service_name: Optional[str] = None,
    ):
        details = {}
        if service_name:
            details["service"] = service_name

        super().__init__(
            message=message,
            code=ErrorCode.EXTERNAL_SERVICE_ERROR,
            status_code=status.HTTP_502_BAD_GATEWAY,
            details=details,
        )


class RateLimitException(APIException):
    """Exception for rate limiting"""

    def __init__(
        self,
        message: str = "Too many requests. Please try again later.",
        retry_after: Optional[int] = None,
    ):
        details = {}
        if retry_after:
            details["retry_after_seconds"] = retry_after

        super().__init__(
            message=message,
            code=ErrorCode.RATE_LIMITED,
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            details=details,
        )


class BusinessRuleException(APIException):
    """Exception for business rule violations"""

    def __init__(
        self,
        message: str,
        rule_code: Optional[str] = None,
    ):
        details = {}
        if rule_code:
            details["rule_code"] = rule_code

        super().__init__(
            message=message,
            code=ErrorCode.BUSINESS_RULE_VIOLATION,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details=details,
        )


# =============================================================================
# SUCCESS RESPONSE
# =============================================================================

def success_response(
    data: Optional[Any] = None,
    message: str = "Success",
    status_code: int = status.HTTP_200_OK,
) -> Dict[str, Any]:
    """Create a standardized success response"""
    response = {
        "success": True,
        "message": message,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    if data is not None:
        response["data"] = data

    return response


def created_response(
    data: Any,
    message: str = "Resource created successfully",
) -> Dict[str, Any]:
    """Create a standardized 201 response"""
    return success_response(data=data, message=message, status_code=status.HTTP_201_CREATED)


# =============================================================================
# EXCEPTION HANDLERS
# =============================================================================

async def api_exception_handler(request: Request, exc: APIException) -> JSONResponse:
    """Handle custom API exceptions"""

    # Log the error
    logger.warning(
        f"API Exception: {exc.code.value} - {exc.message}",
        extra={
            "path": request.url.path,
            "method": request.method,
            "error_code": exc.code.value,
            "status_code": exc.status_code,
        }
    )

    return JSONResponse(
        status_code=exc.status_code,
        content=exc.to_dict(),
    )


async def validation_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle Pydantic validation errors"""
    from pydantic import ValidationError

    if isinstance(exc, ValidationError):
        field_errors = {}
        for error in exc.errors():
            field = ".".join(str(loc) for loc in error["loc"])
            field_errors[field] = error["msg"]

        logger.warning(
            f"Validation error: {field_errors}",
            extra={"path": request.url.path, "method": request.method}
        )

        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "success": False,
                "error": {
                    "code": ErrorCode.VALIDATION_ERROR.value,
                    "message": "Validation failed",
                    "field_errors": field_errors,
                }
            },
        )

    # Fallback
    raise exc


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle unexpected exceptions"""

    # Log the full traceback
    logger.error(
        f"Unhandled exception: {str(exc)}",
        extra={
            "path": request.url.path,
            "method": request.method,
        },
        exc_info=True,
    )

    # Record to ring buffer for diagnostic access
    _record_error(
        method=request.method,
        path=request.url.path,
        error_type=type(exc).__name__,
        error_msg=str(exc),
        tb=traceback.format_exc(),
    )

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "success": False,
            "error": {
                "code": ErrorCode.INTERNAL_ERROR.value,
                "message": "An unexpected error occurred. Please try again.",
            }
        },
    )


async def http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Handle HTTPException — sanitize 500-level responses in production
    to prevent leaking stack traces, SQL errors, or internal paths.
    """
    import os
    from fastapi import HTTPException
    if not isinstance(exc, HTTPException):
        raise exc

    is_prod = bool(os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("ENVIRONMENT") == "production")

    if exc.status_code >= 500 and is_prod:
        # Log the real error server-side
        logger.error(
            f"HTTP {exc.status_code} on {request.method} {request.url.path}: {exc.detail}",
            extra={"path": request.url.path, "method": request.method},
        )
        # Record to ring buffer for diagnostic access
        _record_error(
            method=request.method,
            path=request.url.path,
            error_type=f"HTTPException({exc.status_code})",
            error_msg=str(exc.detail),
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": "Internal server error"},
        )

    # For non-500 errors (or non-production), pass through as-is
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )


def register_exception_handlers(app: FastAPI):
    """Register all exception handlers with the FastAPI app"""
    from fastapi import HTTPException
    from pydantic import ValidationError

    # Register HTTPException handler to sanitize 500-level details in production
    app.add_exception_handler(HTTPException, http_exception_handler)

    # Register custom exception handlers
    app.add_exception_handler(APIException, api_exception_handler)
    app.add_exception_handler(ValidationException, api_exception_handler)
    app.add_exception_handler(PermissionException, api_exception_handler)
    app.add_exception_handler(NotFoundException, api_exception_handler)
    app.add_exception_handler(ConflictException, api_exception_handler)
    app.add_exception_handler(DatabaseException, api_exception_handler)
    app.add_exception_handler(ExternalServiceException, api_exception_handler)
    app.add_exception_handler(RateLimitException, api_exception_handler)
    app.add_exception_handler(BusinessRuleException, api_exception_handler)

    # Register Pydantic validation error handler
    app.add_exception_handler(ValidationError, validation_error_handler)

    # Register generic exception handler (catch-all)
    app.add_exception_handler(Exception, generic_exception_handler)

    logger.info("Exception handlers registered successfully")


# =============================================================================
# VALIDATION HELPERS
# =============================================================================

def validate_required_fields(data: Dict, required: List[str]) -> Dict[str, str]:
    """Validate that required fields are present and non-empty"""
    errors = {}

    for field in required:
        value = data.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            errors[field] = f"{field} is required"

    return errors


def validate_field_length(
    value: str,
    field_name: str,
    min_length: Optional[int] = None,
    max_length: Optional[int] = None,
) -> Optional[str]:
    """Validate field length constraints"""
    if value is None:
        return None

    if min_length is not None and len(value) < min_length:
        return f"{field_name} must be at least {min_length} characters"

    if max_length is not None and len(value) > max_length:
        return f"{field_name} must be at most {max_length} characters"

    return None


def raise_if_errors(field_errors: Dict[str, str]):
    """Raise ValidationException if there are field errors"""
    if field_errors:
        raise ValidationException(
            message="Validation failed",
            field_errors=field_errors,
        )
