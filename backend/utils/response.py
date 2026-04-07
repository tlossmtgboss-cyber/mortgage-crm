"""
Standardized API Response Envelope

All API responses should use these helpers for consistent structure:
  Success: {"success": True, "data": ..., "meta": {...}}
  Error:   {"success": False, "error": {"code": "...", "message": "..."}}
  List:    {"success": True, "data": [...], "meta": {"total": N, "limit": N, "offset": N}}
"""
from typing import Any, Optional, Dict, List
from fastapi.responses import JSONResponse


def success_response(data: Any = None, meta: Optional[Dict] = None, status_code: int = 200) -> JSONResponse:
    """Standard success response."""
    body = {"success": True}
    if data is not None:
        body["data"] = data
    if meta:
        body["meta"] = meta
    return JSONResponse(status_code=status_code, content=body)


def error_response(code: str, message: str, status_code: int = 400, details: Any = None) -> JSONResponse:
    """Standard error response."""
    body = {
        "success": False,
        "error": {"code": code, "message": message}
    }
    if details:
        body["error"]["details"] = details
    return JSONResponse(status_code=status_code, content=body)


def paginated_response(items: List, total: int, limit: int, offset: int) -> JSONResponse:
    """Standard paginated list response."""
    return JSONResponse(content={
        "success": True,
        "data": items,
        "meta": {
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": offset + limit < total
        }
    })


def clamp_pagination(limit: int, offset: int, max_limit: int = 100) -> tuple:
    """Clamp pagination parameters to safe ranges."""
    limit = max(1, min(limit, max_limit))
    offset = max(0, offset)
    return limit, offset


# Standard error codes
class ErrorCodes:
    NOT_FOUND = "NOT_FOUND"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    RATE_LIMITED = "RATE_LIMITED"
    CONFLICT = "CONFLICT"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
