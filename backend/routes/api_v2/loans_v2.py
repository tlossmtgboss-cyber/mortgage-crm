"""
V2 Loans Endpoints - Perennia AI

Mirrors the V1 loans routes with V2 API conventions:
- Cursor-based pagination on list endpoints
- Sparse fieldsets (``?fields=id,loan_number,stage``)
- ISO 8601 datetimes with mandatory timezone offsets
- RFC 7807 Problem Details for all errors
- Consistent ``V2Envelope`` response wrapper

URL prefix: ``/api/v2/loans`` (applied by parent ``api_v2/__init__.py``)
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

router = APIRouter(prefix="/loans", tags=["V2 Loans"])

# ---------------------------------------------------------------------------
# Sparse fieldset definition for loans
# ---------------------------------------------------------------------------
LOAN_FIELDS = {
    "id", "loan_number", "borrower_name", "borrower_email",
    "stage", "program", "loan_type", "amount", "purchase_price",
    "down_payment", "rate", "term",
    "property_address", "property_city", "property_state", "property_zip",
    "lock_date", "closing_date", "funded_date",
    "loan_officer_id", "loan_officer_name", "processor", "underwriter",
    "days_in_stage", "sla_status", "risk_score",
    "organization_id",
    "created_at", "updated_at",
}


def _validate_loan_fields(fields_param: Optional[str]) -> Optional[set]:
    """Validate sparse fieldset against LOAN_FIELDS."""
    if not fields_param:
        return None
    requested = {f.strip() for f in fields_param.split(",") if f.strip()}
    invalid = requested - LOAN_FIELDS
    if invalid:
        raise ValueError(
            f"Unknown fields: {', '.join(sorted(invalid))}. "
            f"Allowed: {', '.join(sorted(LOAN_FIELDS))}"
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


def _loan_to_dict(loan) -> Dict[str, Any]:
    """Convert a SQLAlchemy Loan to a plain dict with V2 formatting."""
    return {
        "id": loan.id,
        "loan_number": getattr(loan, "loan_number", None),
        "borrower_name": getattr(loan, "borrower_name", None),
        "borrower_email": getattr(loan, "borrower_email", None),
        "stage": getattr(loan, "stage", None),
        "program": getattr(loan, "program", None),
        "loan_type": getattr(loan, "loan_type", None),
        "amount": float(loan.amount) if getattr(loan, "amount", None) else None,
        "purchase_price": float(loan.purchase_price) if getattr(loan, "purchase_price", None) else None,
        "down_payment": float(loan.down_payment) if getattr(loan, "down_payment", None) else None,
        "rate": float(loan.rate) if getattr(loan, "rate", None) else None,
        "term": getattr(loan, "term", None),
        "property_address": getattr(loan, "property_address", None),
        "property_city": getattr(loan, "property_city", None),
        "property_state": getattr(loan, "property_state", None),
        "property_zip": getattr(loan, "property_zip", None),
        "lock_date": _format_datetime(getattr(loan, "lock_date", None)),
        "closing_date": _format_datetime(getattr(loan, "closing_date", None)),
        "funded_date": _format_datetime(getattr(loan, "funded_date", None)),
        "loan_officer_id": getattr(loan, "loan_officer_id", None),
        "loan_officer_name": getattr(loan, "loan_officer_name", None),
        "processor": getattr(loan, "processor", None),
        "underwriter": getattr(loan, "underwriter", None),
        "days_in_stage": getattr(loan, "days_in_stage", None),
        "sla_status": getattr(loan, "sla_status", None),
        "risk_score": getattr(loan, "risk_score", None),
        "organization_id": getattr(loan, "organization_id", None),
        "created_at": _format_datetime(getattr(loan, "created_at", None)),
        "updated_at": _format_datetime(getattr(loan, "updated_at", None)),
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
    summary="List loans (V2 - cursor pagination)",
    response_description="Paginated list of loans in V2 envelope",
)
async def list_loans_v2(
    request: Request,
    cursor: Optional[str] = Query(None, description="Opaque cursor for pagination"),
    limit: int = Query(20, ge=1, le=100, description="Page size"),
    stage: Optional[str] = Query(None, description="Filter by stage (e.g. PROCESSING, UNDERWRITING)"),
    loan_type: Optional[str] = Query(None, description="Filter by loan type"),
    loan_officer_id: Optional[int] = Query(None, description="Filter by loan officer"),
    q: Optional[str] = Query(None, description="Search query (borrower name, loan number)"),
    fields: Optional[str] = Query(None, description="Sparse fieldset (e.g. id,loan_number,stage)"),
):
    """List loans with cursor-based pagination.

    Cursor Pagination
    -----------------
    - First request: omit ``cursor``
    - Next page: pass ``cursor=<value from response.meta.cursor>``
    - Check ``meta.has_more`` to know if more pages exist

    Sparse Fieldsets
    ----------------
    Use ``?fields=id,loan_number,stage,amount`` to receive only the
    requested fields (``id`` is always included).
    """
    from db import get_db
    from database.models import Loan
    from auth.dependencies import get_current_user_flexible

    # Validate sparse fields
    try:
        field_set = _validate_loan_fields(fields)
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

        query = db.query(Loan).filter(Loan.deleted_at.is_(None))

        # Tenant isolation
        if hasattr(current_user, "organization_id") and current_user.organization_id:
            query = query.filter(Loan.organization_id == current_user.organization_id)

        # Filters
        if stage:
            query = query.filter(cast(Loan.stage, String) == stage.upper())
        if loan_type:
            query = query.filter(Loan.loan_type == loan_type)
        if loan_officer_id:
            query = query.filter(Loan.loan_officer_id == loan_officer_id)
        if q:
            search_term = f"%{q}%"
            query = query.filter(
                or_(
                    Loan.borrower_name.ilike(search_term),
                    Loan.loan_number.ilike(search_term),
                )
            )

        # Get total count
        total = query.count()

        # Cursor-based pagination
        if cursor_id is not None:
            query = query.filter(Loan.id > cursor_id)

        query = query.order_by(Loan.id.asc())
        loans = query.limit(limit + 1).all()

        has_more = len(loans) > limit
        if has_more:
            loans = loans[:limit]

        # Build response items
        items = []
        for loan in loans:
            item_dict = _loan_to_dict(loan)
            item_dict = apply_sparse_fields(item_dict, field_set)
            items.append(item_dict)

        # Build cursor info
        next_cursor = None
        if has_more and loans:
            next_cursor = encode_cursor({"id": loans[-1].id})

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
        logger.exception("V2 list_loans failed")
        return _problem_response(ProblemDetail.internal_error(str(exc)))
    finally:
        db.close()


@router.get(
    "/{loan_id}",
    summary="Get loan by ID (V2)",
    response_description="Single loan in V2 envelope",
)
async def get_loan_v2(
    request: Request,
    loan_id: int,
    fields: Optional[str] = Query(None, description="Sparse fieldset"),
):
    """Get a single loan by ID with V2 formatting."""
    from db import get_db
    from database.models import Loan
    from auth.dependencies import get_current_user_flexible

    try:
        field_set = _validate_loan_fields(fields)
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

        query = db.query(Loan).filter(Loan.id == loan_id, Loan.deleted_at.is_(None))
        if hasattr(current_user, "organization_id") and current_user.organization_id:
            query = query.filter(Loan.organization_id == current_user.organization_id)

        loan = query.first()
        if not loan:
            return _problem_response(ProblemDetail.not_found(
                f"Loan with id '{loan_id}' not found",
                instance=f"/api/v2/loans/{loan_id}",
            ))

        item_dict = _loan_to_dict(loan)
        item_dict = apply_sparse_fields(item_dict, field_set)

        return V2Envelope(
            data=item_dict,
            meta=V2Meta(api_version="2.0"),
        ).model_dump(exclude_none=True)

    except Exception as exc:
        logger.exception("V2 get_loan failed")
        return _problem_response(ProblemDetail.internal_error(str(exc)))
    finally:
        db.close()
