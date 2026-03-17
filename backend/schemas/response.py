"""
Standard API Response Envelope for Scheduler Endpoints.

Provides a consistent response format across all scheduler endpoints:
    {
        "success": true/false,
        "data": <payload>,
        "message": "optional message",
        "errors": [{"field": "...", "message": "..."}],
        "meta": {"total": 100, "page": 1, "page_size": 25, "total_pages": 4}
    }

Usage in route handlers:
    from schemas.response import APIResponse, success_response, error_response, paginated_response

    # Simple success
    return success_response(data={"id": 1, "name": "foo"})

    # Success with message
    return success_response(data={"id": 1}, message="Created successfully", status_code=201)

    # Error
    return error_response("Booking link not found", status_code=404)

    # Paginated list
    return paginated_response(data=items, total=100, page=1, page_size=25)
"""

from __future__ import annotations

from pydantic import BaseModel
from typing import Any, Generic, List, Optional, TypeVar
from fastapi.responses import JSONResponse

T = TypeVar("T")


class APIResponse(BaseModel, Generic[T]):
    """Standard API response envelope for all scheduler endpoints."""

    success: bool
    data: Optional[T] = None
    message: Optional[str] = None
    errors: Optional[List[dict]] = None
    meta: Optional[dict] = None  # pagination, timing, etc.

    @classmethod
    def ok(cls, data: Any = None, message: Optional[str] = None, meta: Optional[dict] = None) -> "APIResponse":
        return cls(success=True, data=data, message=message, meta=meta)

    @classmethod
    def fail(cls, message: str, errors: Optional[List[dict]] = None) -> "APIResponse":
        return cls(success=False, message=message, errors=errors)

    @classmethod
    def paginated(cls, data: Any, total: int, page: int, page_size: int, message: Optional[str] = None) -> "APIResponse":
        return cls(
            success=True,
            data=data,
            message=message,
            meta={
                "total": total,
                "page": page,
                "page_size": page_size,
                "total_pages": (total + page_size - 1) // page_size if page_size > 0 else 0,
            },
        )

    class Config:
        # Allow arbitrary types so Generic[T] works with dicts, lists, etc.
        arbitrary_types_allowed = True


class PaginationParams(BaseModel):
    """Query parameters for paginated list endpoints."""

    page: int = 1
    page_size: int = 25

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        return self.page_size


# ============================================================================
# Helper functions that return JSONResponse directly
# ============================================================================

def success_response(
    data: Any = None,
    message: Optional[str] = None,
    status_code: int = 200,
    meta: Optional[dict] = None,
) -> JSONResponse:
    """Return a successful API response as a JSONResponse."""
    return JSONResponse(
        status_code=status_code,
        content=APIResponse.ok(data=data, message=message, meta=meta).model_dump(),
    )


def error_response(
    message: str,
    status_code: int = 400,
    errors: Optional[List[dict]] = None,
) -> JSONResponse:
    """Return an error API response as a JSONResponse."""
    return JSONResponse(
        status_code=status_code,
        content=APIResponse.fail(message=message, errors=errors).model_dump(),
    )


def paginated_response(
    data: Any,
    total: int,
    page: int,
    page_size: int,
    message: Optional[str] = None,
) -> JSONResponse:
    """Return a paginated API response as a JSONResponse."""
    return JSONResponse(
        content=APIResponse.paginated(
            data=data, total=total, page=page, page_size=page_size, message=message,
        ).model_dump(),
    )


# ============================================================================
# Dict-based helpers for gradual migration (return plain dicts, not JSONResponse)
# ============================================================================

def envelope(
    data: Any = None,
    message: Optional[str] = None,
    meta: Optional[dict] = None,
) -> dict:
    """Wrap a data payload in the standard envelope dict.

    Use this in route handlers that return plain dicts (FastAPI auto-serializes).
    This avoids the overhead of JSONResponse while providing the consistent shape.

    Example::

        return envelope(data={"id": 1}, message="Created")
        # {"success": true, "data": {"id": 1}, "message": "Created", "errors": null, "meta": null}
    """
    return {
        "success": True,
        "data": data,
        "message": message,
        "errors": None,
        "meta": meta,
    }


def envelope_error(
    message: str,
    errors: Optional[List[dict]] = None,
) -> dict:
    """Wrap an error in the standard envelope dict."""
    return {
        "success": False,
        "data": None,
        "message": message,
        "errors": errors,
        "meta": None,
    }


def envelope_page(
    data: Any,
    total: int,
    page: int,
    page_size: int,
    message: Optional[str] = None,
) -> dict:
    """Wrap paginated data in the standard envelope dict."""
    return {
        "success": True,
        "data": data,
        "message": message,
        "errors": None,
        "meta": {
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size if page_size > 0 else 0,
        },
    }
