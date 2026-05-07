"""
API V2 Response Schemas - Perennia AI

Strict V2 response types with:
- RFC 7807 Problem Details for errors
- Cursor-based pagination
- Sparse fieldset utilities
- Consistent response envelope

Version Negotiation
-------------------
Clients may select API version via:
1. URL path prefix:  /api/v2/scheduler/appointments
2. Accept header:    Accept: application/vnd.perennia.v2+json

The middleware sets ``request.state.api_version`` which route handlers
can inspect.  V2 routes MUST return ``V2Envelope`` responses.
"""

from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
from typing import Any, Dict, Generic, List, Optional, TypeVar

from pydantic import BaseModel, Field, field_validator


# =============================================================================
# RFC 7807 Problem Details
# =============================================================================

class ProblemDetail(BaseModel):
    """RFC 7807 Problem Details for HTTP APIs.

    See https://www.rfc-editor.org/rfc/rfc7807

    Attributes:
        type: A URI reference that identifies the problem type.
        title: A short, human-readable summary of the problem type.
        status: The HTTP status code.
        detail: A human-readable explanation specific to this occurrence.
        instance: A URI reference that identifies the specific occurrence.
        errors: Optional list of field-level validation errors.
    """
    type: str = Field(
        default="about:blank",
        description="URI reference identifying the problem type",
    )
    title: str = Field(
        ...,
        description="Short human-readable summary of the problem",
    )
    status: int = Field(
        ...,
        ge=400,
        le=599,
        description="HTTP status code",
    )
    detail: Optional[str] = Field(
        default=None,
        description="Human-readable explanation specific to this occurrence",
    )
    instance: Optional[str] = Field(
        default=None,
        description="URI reference identifying the specific occurrence",
    )
    errors: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="Field-level validation errors",
    )

    @classmethod
    def not_found(cls, detail: str, instance: str = None) -> "ProblemDetail":
        return cls(
            type="https://api.perenniaai.com/problems/not-found",
            title="Resource Not Found",
            status=404,
            detail=detail,
            instance=instance,
        )

    @classmethod
    def bad_request(cls, detail: str, errors: List[Dict] = None, instance: str = None) -> "ProblemDetail":
        return cls(
            type="https://api.perenniaai.com/problems/bad-request",
            title="Bad Request",
            status=400,
            detail=detail,
            errors=errors,
            instance=instance,
        )

    @classmethod
    def unsupported_version(cls, detail: str) -> "ProblemDetail":
        return cls(
            type="https://api.perenniaai.com/problems/unsupported-version",
            title="Unsupported API Version",
            status=400,
            detail=detail,
        )

    @classmethod
    def validation_error(cls, detail: str, errors: List[Dict]) -> "ProblemDetail":
        return cls(
            type="https://api.perenniaai.com/problems/validation-error",
            title="Validation Error",
            status=422,
            detail=detail,
            errors=errors,
        )

    @classmethod
    def internal_error(cls, detail: str = "An unexpected error occurred") -> "ProblemDetail":
        return cls(
            type="https://api.perenniaai.com/problems/internal-error",
            title="Internal Server Error",
            status=500,
            detail=detail,
        )


# =============================================================================
# CURSOR PAGINATION
# =============================================================================

def encode_cursor(values: Dict[str, Any]) -> str:
    """Encode cursor values to an opaque string token.

    The cursor payload is a JSON object base64-encoded so clients treat it
    as an opaque string.  The payload contains the sort key value(s) and
    the item ID needed to resume pagination.
    """
    payload = json.dumps(values, default=str)
    return base64.urlsafe_b64encode(payload.encode()).decode()


def decode_cursor(cursor: str) -> Dict[str, Any]:
    """Decode an opaque cursor string back to its component values.

    Raises ValueError if the cursor is malformed.
    """
    try:
        payload = base64.urlsafe_b64decode(cursor.encode()).decode()
        return json.loads(payload)
    except Exception as exc:
        raise ValueError(f"Invalid cursor: {exc}") from exc


T = TypeVar("T")


class CursorInfo(BaseModel):
    """Cursor pointers for forward/backward traversal."""
    next: Optional[str] = Field(default=None, description="Cursor to fetch the next page")
    prev: Optional[str] = Field(default=None, description="Cursor to fetch the previous page")


class CursorPage(BaseModel, Generic[T]):
    """Cursor-based pagination container.

    Instead of offset/limit, cursor pagination uses opaque tokens that
    point to the boundary of each page.  This avoids the consistency
    problems of offset-based pagination when data changes between pages.

    Attributes:
        data: The list of items for the current page.
        cursor: Contains ``next`` and ``prev`` cursor strings.
        has_more: True when additional pages exist after ``cursor.next``.
        total_count: Optional total count (only included when cheap to compute).
    """
    data: List[T] = Field(default_factory=list)
    cursor: CursorInfo = Field(default_factory=CursorInfo)
    has_more: bool = False
    total_count: Optional[int] = Field(
        default=None,
        description="Total count (included only when cheap to compute)",
    )


# =============================================================================
# V2 RESPONSE ENVELOPE
# =============================================================================

class V2Meta(BaseModel):
    """Metadata about the API response."""
    api_version: str = "2.0"
    request_id: Optional[str] = None
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
    )
    deprecated: bool = False
    sunset: Optional[str] = None
    # Pagination metadata (populated on list endpoints)
    cursor: Optional[str] = Field(default=None, description="Opaque cursor for next page")
    has_more: Optional[bool] = Field(default=None, description="True if more pages exist")
    total: Optional[int] = Field(default=None, description="Total count when available")


class V2Envelope(BaseModel, Generic[T]):
    """Standard V2 response envelope.

    Every V2 response is wrapped in this envelope to provide a
    consistent structure for clients.

    Attributes:
        data: The response payload.
        meta: Metadata about the request/response.
        included: Related resources when ``?include=`` is used.
    """
    data: T
    meta: V2Meta = Field(default_factory=V2Meta)
    included: Optional[Dict[str, List[Dict[str, Any]]]] = None


# =============================================================================
# SPARSE FIELDSET UTILITIES
# =============================================================================

APPOINTMENT_FIELDS = {
    "id", "title", "description", "status", "meeting_type", "meeting_mode",
    "scheduled_start", "scheduled_end", "duration_minutes", "timezone",
    "attendee_name", "attendee_email", "attendee_phone", "attendee_notes",
    "lead_id", "loan_id", "contact_id", "assigned_user_id",
    "location", "video_link", "created_at", "updated_at",
    "cancellation_reason", "internal_notes", "meeting_notes",
    "booked_by_ai", "no_show_risk_score", "uuid",
}


def _parse_field_name(field: str) -> str:
    """Extract the top-level field name from a possibly dot-notated field.

    Examples:
        ``"name"``           -> ``"name"``
        ``"contact.email"``  -> ``"contact"``
        ``"address.city"``   -> ``"address"``
    """
    return field.split(".")[0]


def validate_sparse_fields(
    fields_param: Optional[str],
    allowed: set[str] = APPOINTMENT_FIELDS,
) -> Optional[set[str]]:
    """Parse and validate the ``fields`` query parameter.

    Supports dot-notation for nested fields (e.g. ``contact.email``).
    Validation checks that the **top-level** field name is in the
    allowed set.  The full dot-notated path is preserved in the returned
    set so callers can apply nested filtering downstream.

    Args:
        fields_param: Comma-separated field names (e.g. ``"id,title,contact.email"``).
        allowed: The full set of permitted top-level field names.

    Returns:
        A set of validated field names, or None if no filtering requested.

    Raises:
        ValueError: If any requested top-level field is not in the allowed set.
    """
    if not fields_param:
        return None

    requested = {f.strip() for f in fields_param.split(",") if f.strip()}
    # Validate top-level names only
    top_level = {_parse_field_name(f) for f in requested}
    invalid = top_level - allowed
    if invalid:
        raise ValueError(
            f"Unknown fields: {', '.join(sorted(invalid))}. "
            f"Allowed: {', '.join(sorted(allowed))}"
        )
    return requested


def apply_sparse_fields(item: Dict[str, Any], fields: Optional[set[str]]) -> Dict[str, Any]:
    """Filter a dict to only include the requested fields.

    If ``fields`` is None, returns the full dict unchanged.
    The ``id`` field is always included regardless of the filter set.

    Supports dot-notation for nested field filtering: if the item
    contains a dict value and the field set includes dot-notated paths
    (e.g. ``contact.email``), only the specified nested keys are kept.
    """
    if fields is None:
        return item

    # Separate top-level fields from dot-notated nested paths
    top_level_fields: set[str] = set()
    nested_fields: Dict[str, set[str]] = {}
    for f in fields:
        if "." in f:
            parent, child = f.split(".", 1)
            top_level_fields.add(parent)
            nested_fields.setdefault(parent, set()).add(child)
        else:
            top_level_fields.add(f)

    keep = top_level_fields | {"id"}
    result = {}
    for k, v in item.items():
        if k not in keep:
            continue
        # Apply nested field filtering when the value is a dict
        if k in nested_fields and isinstance(v, dict):
            nested_keep = nested_fields[k] | {"id"} if "id" in v else nested_fields[k]
            result[k] = {nk: nv for nk, nv in v.items() if nk in nested_keep}
        else:
            result[k] = v
    return result


# =============================================================================
# RELATED RESOURCE LINK HEADERS
# =============================================================================

# Maps resource type -> list of (foreign_key_field, related_path_template, rel_name)
# The template uses {value} as a placeholder for the FK value.
RESOURCE_LINK_MAP: Dict[str, list] = {
    "lead": [
        ("id", "/api/v2/loans?lead_id={value}", "loans"),
        ("id", "/api/v2/scheduler/appointments?lead_id={value}", "appointments"),
        ("owner_id", "/api/v2/leads?owner_id={value}", "owner-leads"),
    ],
    "loan": [
        ("id", "/api/v2/scheduler/appointments?loan_id={value}", "appointments"),
        ("loan_officer_id", "/api/v2/loans?loan_officer_id={value}", "officer-loans"),
    ],
    "appointment": [
        ("lead_id", "/api/v2/leads/{value}", "lead"),
        ("loan_id", "/api/v2/loans/{value}", "loan"),
    ],
}


def build_link_header(resource_type: str, data: Dict[str, Any]) -> Optional[str]:
    """Build an RFC 8288 Link header string for related resources.

    Args:
        resource_type: One of ``"lead"``, ``"loan"``, ``"appointment"``.
        data: The resource dict (must contain the FK fields to resolve links).

    Returns:
        A Link header value like
        ``</api/v2/loans?lead_id=42>; rel="loans", ...``
        or None if no links can be generated.
    """
    link_defs = RESOURCE_LINK_MAP.get(resource_type)
    if not link_defs:
        return None

    parts = []
    for fk_field, template, rel in link_defs:
        value = data.get(fk_field)
        if value is not None:
            uri = template.replace("{value}", str(value))
            parts.append(f'<{uri}>; rel="{rel}"')

    return ", ".join(parts) if parts else None


# =============================================================================
# V2 APPOINTMENT SCHEMAS
# =============================================================================

class V2AppointmentResponse(BaseModel):
    """V2 appointment response with strict typing and ISO 8601 datetimes."""
    id: int
    uuid: Optional[str] = None
    title: str
    description: Optional[str] = None
    status: str
    meeting_type: Optional[str] = None
    meeting_mode: Optional[str] = None
    scheduled_start: Optional[str] = Field(
        None,
        description="ISO 8601 datetime with timezone (e.g. 2026-03-15T10:00:00-05:00)",
    )
    scheduled_end: Optional[str] = Field(
        None,
        description="ISO 8601 datetime with timezone",
    )
    duration_minutes: Optional[int] = None
    timezone: Optional[str] = None
    attendee_name: Optional[str] = None
    attendee_email: Optional[str] = None
    attendee_phone: Optional[str] = None
    attendee_notes: Optional[str] = None
    lead_id: Optional[int] = None
    loan_id: Optional[int] = None
    contact_id: Optional[int] = None
    assigned_user_id: Optional[int] = None
    location: Optional[str] = None
    video_link: Optional[str] = None
    cancellation_reason: Optional[str] = None
    internal_notes: Optional[str] = None
    meeting_notes: Optional[str] = None
    booked_by_ai: Optional[bool] = None
    no_show_risk_score: Optional[float] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    class Config:
        from_attributes = True


class V2AppointmentAttendee(BaseModel):
    """Attendee included resource."""
    id: Optional[int] = None
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    role: str = "attendee"


class V2MeetingInfo(BaseModel):
    """Meeting details included resource."""
    video_link: Optional[str] = None
    location: Optional[str] = None
    meeting_mode: Optional[str] = None
    duration_minutes: Optional[int] = None


class V2AppointmentCreateRequest(BaseModel):
    """V2 appointment creation request with stricter validation."""
    title: str = Field(..., min_length=1, max_length=500)
    description: Optional[str] = Field(None, max_length=5000)
    meeting_type: Optional[str] = "custom"
    meeting_mode: str = Field(default="video", pattern=r"^(video|phone|in_person|screen_share)$")
    scheduled_start: str = Field(
        ...,
        description="ISO 8601 datetime with timezone (e.g. 2026-03-15T10:00:00-05:00)",
    )
    duration_minutes: int = Field(30, ge=5, le=480)
    timezone: str = "America/Chicago"
    attendee_name: Optional[str] = Field(None, max_length=200)
    attendee_email: Optional[str] = None
    attendee_phone: Optional[str] = Field(None, max_length=20)
    attendee_notes: Optional[str] = Field(None, max_length=2000)
    lead_id: Optional[int] = None
    loan_id: Optional[int] = None
    contact_id: Optional[int] = None
    assigned_user_id: Optional[int] = None
    appointment_type_id: Optional[int] = None
    intake_responses: Optional[Dict[str, Any]] = None
    booked_by_ai: bool = False

    @field_validator("scheduled_start")
    @classmethod
    def validate_iso8601(cls, v: str) -> str:
        """Ensure the datetime is valid ISO 8601 with timezone info."""
        try:
            dt = datetime.fromisoformat(v)
        except (ValueError, TypeError) as exc:
            raise ValueError(
                f"scheduled_start must be ISO 8601 with timezone: {exc}"
            ) from exc
        if dt.tzinfo is None:
            raise ValueError(
                "scheduled_start must include timezone offset "
                "(e.g. 2026-03-15T10:00:00-05:00)"
            )
        return v


class V2AppointmentUpdateRequest(BaseModel):
    """V2 appointment update request."""
    title: Optional[str] = Field(None, min_length=1, max_length=500)
    description: Optional[str] = Field(None, max_length=5000)
    scheduled_start: Optional[str] = None
    duration_minutes: Optional[int] = Field(None, ge=5, le=480)
    meeting_mode: Optional[str] = None
    location: Optional[str] = Field(None, max_length=500)
    video_link: Optional[str] = Field(None, max_length=2000)
    status: Optional[str] = None
    cancellation_reason: Optional[str] = Field(None, max_length=2000)
    internal_notes: Optional[str] = Field(None, max_length=5000)
    meeting_notes: Optional[str] = Field(None, max_length=5000)
    attendee_name: Optional[str] = Field(None, max_length=200)
    attendee_email: Optional[str] = None
    attendee_phone: Optional[str] = Field(None, max_length=20)
    send_notification: bool = True

    @field_validator("scheduled_start")
    @classmethod
    def validate_iso8601(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        try:
            dt = datetime.fromisoformat(v)
        except (ValueError, TypeError) as exc:
            raise ValueError(
                f"scheduled_start must be ISO 8601 with timezone: {exc}"
            ) from exc
        if dt.tzinfo is None:
            raise ValueError(
                "scheduled_start must include timezone offset"
            )
        return v


# =============================================================================
# V2 LEAD SCHEMAS
# =============================================================================

class V2LeadCreateRequest(BaseModel):
    """V2 lead creation request with strict validation."""
    name: str = Field(..., min_length=1, max_length=200)
    email: Optional[str] = None
    phone: Optional[str] = Field(None, max_length=20)
    source: Optional[str] = Field(None, max_length=100)
    stage: Optional[str] = Field(None, max_length=50)
    loan_type: Optional[str] = Field(None, max_length=100)
    preapproval_amount: Optional[float] = Field(None, ge=0)
    credit_score: Optional[int] = Field(None, ge=300, le=850)
    property_type: Optional[str] = Field(None, max_length=100)
    property_value: Optional[float] = Field(None, ge=0)
    loan_amount: Optional[float] = Field(None, ge=0)
    interest_rate: Optional[float] = Field(None, ge=0, le=30)
    loan_term: Optional[int] = Field(None, ge=1, le=600)
    notes: Optional[str] = Field(None, max_length=10000)


class V2LeadUpdateRequest(BaseModel):
    """V2 lead partial update request."""
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    first_name: Optional[str] = Field(None, max_length=100)
    last_name: Optional[str] = Field(None, max_length=100)
    email: Optional[str] = None
    phone: Optional[str] = Field(None, max_length=20)
    stage: Optional[str] = Field(None, max_length=50)
    source: Optional[str] = Field(None, max_length=100)
    loan_type: Optional[str] = Field(None, max_length=100)
    notes: Optional[str] = Field(None, max_length=10000)


# =============================================================================
# V2 LOAN SCHEMAS
# =============================================================================

class V2LoanCreateRequest(BaseModel):
    """V2 loan creation request with strict validation."""
    loan_number: Optional[str] = Field(None, max_length=50)
    borrower_name: Optional[str] = Field(None, max_length=200)
    borrower_email: Optional[str] = None
    stage: Optional[str] = Field(None, max_length=50)
    program: Optional[str] = Field(None, max_length=100)
    loan_type: Optional[str] = Field(None, max_length=100)
    amount: Optional[float] = Field(None, ge=0)
    purchase_price: Optional[float] = Field(None, ge=0)
    down_payment: Optional[float] = Field(None, ge=0)
    rate: Optional[float] = Field(None, ge=0, le=30)
    term: Optional[int] = Field(None, ge=1, le=600)
    property_address: Optional[str] = Field(None, max_length=500)
    property_city: Optional[str] = Field(None, max_length=200)
    property_state: Optional[str] = Field(None, max_length=2)
    property_zip: Optional[str] = Field(None, max_length=10)


class V2LoanUpdateRequest(BaseModel):
    """V2 loan partial update request."""
    borrower_name: Optional[str] = Field(None, max_length=200)
    borrower_email: Optional[str] = None
    stage: Optional[str] = Field(None, max_length=50)
    program: Optional[str] = Field(None, max_length=100)
    loan_type: Optional[str] = Field(None, max_length=100)
    amount: Optional[float] = Field(None, ge=0)
    purchase_price: Optional[float] = Field(None, ge=0)
    down_payment: Optional[float] = Field(None, ge=0)
    rate: Optional[float] = Field(None, ge=0, le=30)
    term: Optional[int] = Field(None, ge=1, le=600)
    property_address: Optional[str] = Field(None, max_length=500)
    property_city: Optional[str] = Field(None, max_length=200)
    property_state: Optional[str] = Field(None, max_length=2)
    property_zip: Optional[str] = Field(None, max_length=10)
    force_stage: bool = Field(False, description="Override stage transition validation (admin only)")


# =============================================================================
# PAGINATION LINK HEADER BUILDER
# =============================================================================

def build_pagination_link_header(
    base_path: str,
    next_cursor: Optional[str] = None,
    query_params: Optional[Dict[str, str]] = None,
) -> Optional[str]:
    """Build RFC 8288 Link header for paginated list responses.

    Args:
        base_path: The endpoint path (e.g. ``/api/v2/leads``).
        next_cursor: The opaque cursor for the next page, or None.
        query_params: Additional query parameters to preserve (filters, etc.).

    Returns:
        A Link header value like ``</api/v2/leads?cursor=xxx>; rel="next"``
        or None if there is no next page.
    """
    if not next_cursor:
        return None

    params = dict(query_params or {})
    params["cursor"] = next_cursor
    qs = "&".join(f"{k}={v}" for k, v in params.items() if v is not None)
    return f'<{base_path}?{qs}>; rel="next"'
