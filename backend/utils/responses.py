"""
Perennia AI - Standard Response Utilities

Provides consistent response formatting across all API endpoints.
"""

from typing import Optional, Any, Dict
from pydantic import BaseModel
from datetime import datetime
import uuid


class ErrorResponse(BaseModel):
    """Standard error response model"""
    success: bool = False
    error_code: str
    message: str
    details: Optional[Dict[str, Any]] = None
    request_id: str
    timestamp: datetime

    class Config:
        json_schema_extra = {
            "example": {
                "success": False,
                "error_code": "VALIDATION_ERROR",
                "message": "Invalid input data",
                "details": {
                    "field_errors": {
                        "email": "Invalid email format"
                    }
                },
                "request_id": "req_abc123",
                "timestamp": "2025-12-24T07:40:00Z"
            }
        }


class SuccessResponse(BaseModel):
    """Standard success response model"""
    success: bool = True
    message: str
    data: Optional[Any] = None
    timestamp: datetime = None

    def __init__(self, **data):
        if data.get('timestamp') is None:
            data['timestamp'] = datetime.now(timezone.utc)
        super().__init__(**data)

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Settings saved successfully",
                "data": {
                    "id": "settings_123",
                    "updated_at": "2025-12-24T07:40:00Z"
                },
                "timestamp": "2025-12-24T07:40:00Z"
            }
        }


def success_response(
    message: str,
    data: Optional[Any] = None
) -> Dict[str, Any]:
    """
    Create a standard success response.

    Args:
        message: Success message to display to user
        data: Optional response data

    Returns:
        Dictionary formatted as standard success response

    Example:
        return success_response(
            message="Settings saved successfully",
            data={"id": settings.id}
        )
    """
    return {
        "success": True,
        "message": message,
        "data": data,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


def error_response(
    message: str,
    code: str = "UNKNOWN_ERROR",
    details: Optional[Dict[str, Any]] = None,
    request_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Create a standard error response.

    Args:
        message: Error message to display to user
        code: Error code for categorization
        details: Optional error details
        request_id: Optional request ID for tracking

    Returns:
        Dictionary formatted as standard error response

    Example:
        return error_response(
            message="Failed to save settings",
            code="DATABASE_ERROR",
            details={"table": "user_settings"}
        )
    """
    return {
        "success": False,
        "error_code": code,
        "message": message,
        "details": details,
        "request_id": request_id or str(uuid.uuid4())[:12],
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


def validation_error_response(
    field_errors: Dict[str, str],
    message: str = "Validation failed"
) -> Dict[str, Any]:
    """
    Create a validation error response with field-specific errors.

    Args:
        field_errors: Dictionary of field names to error messages
        message: Overall error message

    Returns:
        Dictionary formatted as validation error response

    Example:
        return validation_error_response({
            "email": "Invalid email format",
            "phone": "Phone number is required"
        })
    """
    return error_response(
        message=message,
        code="VALIDATION_ERROR",
        details={"field_errors": field_errors}
    )
