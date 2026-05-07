"""
V2 Leads Endpoints - Perennia AI

Mirrors the V1 leads routes with V2 API conventions:
- Cursor-based pagination on list endpoints
- Sparse fieldsets (``?fields=id,name,stage``)
- ISO 8601 datetimes with mandatory timezone offsets
- RFC 7807 Problem Details for all errors
- Consistent ``V2Envelope`` response wrapper

URL prefix: ``/api/v2/leads`` (applied by parent ``api_v2/__init__.py``)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, or_, cast, String
from sqlalchemy.orm import Session

from schemas.api_v2 import (
    CursorInfo,
    CursorPage,
    ProblemDetail,
    V2Envelope,
    V2Meta,
    apply_sparse_fields,
    decode_cursor,
    encode_cursor,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/leads", tags=["V2 Leads"])

# ---------------------------------------------------------------------------
# Sparse fieldset definition for leads
# ---------------------------------------------------------------------------
LEAD_FIELDS = {
    "id", "name", "first_name", "last_name", "email", "phone",
    "stage", "source", "ai_score", "sentiment", "next_action",
    "loan_type", "preapproval_amount", "credit_score",
    "owner_id", "last_contact", "loan_number",
    "property_type", "property_value", "loan_amount",
    "interest_rate", "loan_term", "closing_date",
    "organization_id", "referral_partner_id",
    "created_at", "updated_at",
}


def _validate_lead_fields(fields_param: Optional[str]) -> Optional[set]:
    """Validate sparse fieldset against LEAD_FIELDS."""
    if not fields_param:
        return None
    requested = {f.strip() for f in fields_param.split(",") if f.strip()}
    invalid = requested - LEAD_FIELDS
    if invalid:
        raise ValueError(
            f"Unknown fields: {', '.join(sorted(invalid))}. "
            f"Allowed: {', '.join(sorted(LEAD_FIELDS))}"
        )
    return requested


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _format_datetime(dt) -> Optional[str]:
    """Format a datetime as ISO 8601 with timezone."""
    if dt is None:
        return None
    if isinstance(dt, str):
        return dt
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _lead_to_dict(lead) -> Dict[str, Any]:
    """Convert a SQLAlchemy Lead to a plain dict with V2 formatting."""
    return {
        "id": lead.id,
        "name": getattr(lead, "name", None),
        "first_name": getattr(lead, "first_name", None),
        "last_name": getattr(lead, "last_name", None),
        "email": getattr(lead, "email", None),
        "phone": getattr(lead, "phone", None),
        "stage": getattr(lead, "stage", None),
        "source": getattr(lead, "source", None),
        "ai_score": getattr(lead, "ai_score", None),
        "sentiment": getattr(lead, "sentiment", None),
        "next_action": getattr(lead, "next_action", None),
        "loan_type": getattr(lead, "loan_type", None),
        "preapproval_amount": float(lead.preapproval_amount) if getattr(lead, "preapproval_amount", None) else None,
        "credit_score": getattr(lead, "credit_score", None),
        "owner_id": getattr(lead, "owner_id", None),
        "last_contact": _format_datetime(getattr(lead, "last_contact", None)),
        "loan_number": getattr(lead, "loan_number", None),
        "property_type": getattr(lead, "property_type", None),
        "property_value": float(lead.property_value) if getattr(lead, "property_value", None) else None,
        "loan_amount": float(lead.loan_amount) if getattr(lead, "loan_amount", None) else None,
        "interest_rate": float(lead.interest_rate) if getattr(lead, "interest_rate", None) else None,
        "loan_term": getattr(lead, "loan_term", None),
        "closing_date": _format_datetime(getattr(lead, "closing_date", None)),
        "organization_id": getattr(lead, "organization_id", None),
        "referral_partner_id": getattr(lead, "referral_partner_id", None),
        "created_at": _format_datetime(getattr(lead, "created_at", None)),
        "updated_at": _format_datetime(getattr(lead, "updated_at", None)),
    }


def _problem_response(problem: ProblemDetail) -> JSONResponse:
    """Build a JSONResponse from a ProblemDetail."""
    return JSONResponse(
        status_code=problem.status,
        content=problem.model_dump(exclude_none=True),
        headers={"Content-Type": "application/problem+json"},
    )


# ---------------------------------------------------------------------------
# ROUTES
# ---------------------------------------------------------------------------

@router.get(
    "",
    summary="List leads (V2 - cursor pagination)",
    response_description="Paginated list of leads in V2 envelope",
)
async def list_leads_v2(
    request: Request,
    cursor: Optional[str] = Query(None, description="Opaque cursor for pagination"),
    limit: int = Query(20, ge=1, le=100, description="Page size"),
    stage: Optional[str] = Query(None, description="Filter by stage"),
    source: Optional[str] = Query(None, description="Filter by source"),
    owner_id: Optional[int] = Query(None, description="Filter by owner/LO"),
    q: Optional[str] = Query(None, description="Search query (name, email, phone)"),
    fields: Optional[str] = Query(None, description="Sparse fieldset (e.g. id,name,stage)"),
):
    """List leads with cursor-based pagination.

    Cursor Pagination
    -----------------
    - First request: omit ``cursor``
    - Next page: pass ``cursor=<value from response.meta.cursor>``
    - Check ``meta.has_more`` to know if more pages exist

    Sparse Fieldsets
    ----------------
    Use ``?fields=id,name,stage`` to receive only the requested fields
    (``id`` is always included).
    """
    from db import get_db
    from database.models import Lead
    from auth.dependencies import get_current_user_flexible

    # Validate sparse fields
    try:
        field_set = _validate_lead_fields(fields)
    except ValueError as exc:
        return _problem_response(ProblemDetail.bad_request(str(exc)))

    # Resolve cursor
    cursor_id = None
    if cursor:
        try:
            cursor_data = decode_cursor(cursor)
            cursor_id = cursor_data.get("id")
        except ValueError as exc:
            return _problem_response(ProblemDetail.bad_request(f"Invalid cursor: {exc}"))

    db: Session = next(get_db())
    try:
        # Authenticate
        try:
            current_user = await get_current_user_flexible(request)
        except Exception:
            return _problem_response(ProblemDetail(
                type="https://api.perenniaai.com/problems/unauthorized",
                title="Unauthorized",
                status=401,
                detail="Valid authentication required",
            ))

        query = db.query(Lead).filter(Lead.deleted_at.is_(None))

        # Tenant isolation
        if hasattr(current_user, "organization_id") and current_user.organization_id:
            query = query.filter(Lead.organization_id == current_user.organization_id)

        # Filters
        if stage:
            query = query.filter(cast(Lead.stage, String) == stage)
        if source:
            query = query.filter(Lead.source == source)
        if owner_id:
            query = query.filter(Lead.owner_id == owner_id)
        if q:
            search_term = f"%{q}%"
            query = query.filter(
                or_(
                    Lead.name.ilike(search_term),
                    Lead.email.ilike(search_term),
                    Lead.phone.ilike(search_term),
                )
            )

        # Get total count (cheap for filtered queries)
        total = query.count()

        # Cursor-based pagination
        if cursor_id is not None:
            query = query.filter(Lead.id > cursor_id)

        query = query.order_by(Lead.id.asc())
        leads = query.limit(limit + 1).all()

        has_more = len(leads) > limit
        if has_more:
            leads = leads[:limit]

        # Build response items
        items = []
        for lead in leads:
            item_dict = _lead_to_dict(lead)
            item_dict = apply_sparse_fields(item_dict, field_set)
            items.append(item_dict)

        # Build cursor info
        next_cursor = None
        if has_more and leads:
            next_cursor = encode_cursor({"id": leads[-1].id})

        return V2Envelope(
            data=items,
            meta=V2Meta(
                api_version="2.0",
                cursor=next_cursor,
                has_more=has_more,
                total=total,
            ),
        ).model_dump(exclude_none=True)

    except Exception as exc:
        logger.exception("V2 list_leads failed")
        return _problem_response(ProblemDetail.internal_error(str(exc)))
    finally:
        db.close()


@router.get(
    "/{lead_id}",
    summary="Get lead by ID (V2)",
    response_description="Single lead in V2 envelope",
)
async def get_lead_v2(
    request: Request,
    lead_id: int,
    fields: Optional[str] = Query(None, description="Sparse fieldset"),
):
    """Get a single lead by ID with V2 formatting."""
    from db import get_db
    from database.models import Lead
    from auth.dependencies import get_current_user_flexible

    try:
        field_set = _validate_lead_fields(fields)
    except ValueError as exc:
        return _problem_response(ProblemDetail.bad_request(str(exc)))

    db: Session = next(get_db())
    try:
        try:
            current_user = await get_current_user_flexible(request)
        except Exception:
            return _problem_response(ProblemDetail(
                type="https://api.perenniaai.com/problems/unauthorized",
                title="Unauthorized",
                status=401,
                detail="Valid authentication required",
            ))

        query = db.query(Lead).filter(Lead.id == lead_id, Lead.deleted_at.is_(None))
        if hasattr(current_user, "organization_id") and current_user.organization_id:
            query = query.filter(Lead.organization_id == current_user.organization_id)

        lead = query.first()
        if not lead:
            return _problem_response(ProblemDetail.not_found(
                f"Lead with id '{lead_id}' not found",
                instance=f"/api/v2/leads/{lead_id}",
            ))

        item_dict = _lead_to_dict(lead)
        item_dict = apply_sparse_fields(item_dict, field_set)

        return V2Envelope(
            data=item_dict,
            meta=V2Meta(api_version="2.0"),
        ).model_dump(exclude_none=True)

    except Exception as exc:
        logger.exception("V2 get_lead failed")
        return _problem_response(ProblemDetail.internal_error(str(exc)))
    finally:
        db.close()
