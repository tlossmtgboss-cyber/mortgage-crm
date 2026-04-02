"""
Perennia AI - Backend Error Handling Utilities

Custom exception classes for consistent error handling across the application.
"""

from enum import Enum
from typing import Optional, Dict, Any
from datetime import datetime
import uuid


class ErrorCode(str, Enum):
    """Standard error codes used across the application"""

    # Validation errors
    VALIDATION_ERROR = "VALIDATION_ERROR"
    REQUIRED_FIELD = "REQUIRED_FIELD"
    INVALID_FORMAT = "INVALID_FORMAT"

    # Authentication/Authorization
    AUTH_ERROR = "AUTH_ERROR"
    SESSION_EXPIRED = "SESSION_EXPIRED"
    INSUFFICIENT_PERMISSIONS = "INSUFFICIENT_PERMISSIONS"
    INVALID_TOKEN = "INVALID_TOKEN"

    # Network errors
    NETWORK_ERROR = "NETWORK_ERROR"
    TIMEOUT = "TIMEOUT"

    # Server errors
    SERVER_ERROR = "SERVER_ERROR"
    DATABASE_ERROR = "DATABASE_ERROR"
    EXTERNAL_SERVICE_ERROR = "EXTERNAL_SERVICE_ERROR"

    # Rate limiting
    RATE_LIMIT = "RATE_LIMIT"
    QUOTA_EXCEEDED = "QUOTA_EXCEEDED"

    # Resource errors
    NOT_FOUND = "NOT_FOUND"
    ALREADY_EXISTS = "ALREADY_EXISTS"
    CONFLICT = "CONFLICT"

    # Generic
    UNKNOWN_ERROR = "UNKNOWN_ERROR"


class AppException(Exception):
    """
    Base exception class for all application exceptions.

    Usage:
        raise AppException("Something went wrong", ErrorCode.SERVER_ERROR, 500)
    """

    def __init__(
        self,
        message: str,
        code: ErrorCode = ErrorCode.UNKNOWN_ERROR,
        status_code: int = 500,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}
        self.request_id = str(uuid.uuid4())[:12]
        self.timestamp = datetime.now(timezone.utc)

    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary for JSON response"""
        return {
            "success": False,
            "error_code": self.code.value,
            "message": self.message,
            "details": self.details,
            "request_id": self.request_id,
            "timestamp": self.timestamp.isoformat()
        }


class ValidationException(AppException):
    """
    Validation error exception.

    Usage:
        raise ValidationException(
            "Invalid input data",
            field_errors={"email": "Invalid email format"}
        )
    """

    def __init__(
        self,
        message: str = "Validation failed",
        field_errors: Optional[Dict[str, str]] = None
    ):
        super().__init__(
            message=message,
            code=ErrorCode.VALIDATION_ERROR,
            status_code=400,
            details={"field_errors": field_errors or {}}
        )
        self.field_errors = field_errors or {}


class AuthenticationException(AppException):
    """Authentication error exception"""

    def __init__(self, message: str = "Authentication failed"):
        super().__init__(
            message=message,
            code=ErrorCode.AUTH_ERROR,
            status_code=401
        )


class PermissionException(AppException):
    """Permission/Authorization error exception"""

    def __init__(self, message: str = "Insufficient permissions"):
        super().__init__(
            message=message,
            code=ErrorCode.INSUFFICIENT_PERMISSIONS,
            status_code=403
        )


class NotFoundException(AppException):
    """Resource not found exception"""

    def __init__(
        self,
        message: str = "Resource not found",
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None
    ):
        details = {}
        if resource_type:
            details["resource_type"] = resource_type
        if resource_id:
            details["resource_id"] = resource_id

        super().__init__(
            message=message,
            code=ErrorCode.NOT_FOUND,
            status_code=404,
            details=details
        )


class ConflictException(AppException):
    """Resource conflict exception (e.g., duplicate)"""

    def __init__(self, message: str = "Resource already exists"):
        super().__init__(
            message=message,
            code=ErrorCode.ALREADY_EXISTS,
            status_code=409
        )


class RateLimitException(AppException):
    """Rate limit exceeded exception"""

    def __init__(
        self,
        message: str = "Rate limit exceeded. Please try again later.",
        retry_after: Optional[int] = None
    ):
        details = {}
        if retry_after:
            details["retry_after_seconds"] = retry_after

        super().__init__(
            message=message,
            code=ErrorCode.RATE_LIMIT,
            status_code=429,
            details=details
        )


class ExternalServiceException(AppException):
    """External service error exception (Telnyx, SendGrid, etc.)"""

    def __init__(
        self,
        message: str = "External service error",
        service_name: Optional[str] = None
    ):
        details = {}
        if service_name:
            details["service"] = service_name

        super().__init__(
            message=message,
            code=ErrorCode.EXTERNAL_SERVICE_ERROR,
            status_code=502,
            details=details
        )


class DatabaseException(AppException):
    """Database error exception"""

    def __init__(self, message: str = "Database error occurred. Please try again."):
        super().__init__(
            message=message,
            code=ErrorCode.DATABASE_ERROR,
            status_code=500
        )


class TimeoutException(AppException):
    """Operation timeout exception"""

    def __init__(self, message: str = "Operation timed out. Please try again."):
        super().__init__(
            message=message,
            code=ErrorCode.TIMEOUT,
            status_code=504
        )
