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
    V2LoanCreateRequest,
    V2LoanUpdateRequest,
    V2Meta,
    apply_sparse_fields,
    build_link_header,
    build_pagination_link_header,
    decode_cursor,
    encode_cursor,
    _parse_field_name,
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
    """Validate sparse fieldset against LOAN_FIELDS.

    Supports dot-notation for nested fields (e.g. ``property.address``).
    Only the top-level portion is validated against LOAN_FIELDS.
    """
    if not fields_param:
        return None
    requested = {f.strip() for f in fields_param.split(",") if f.strip()}
    top_level = {_parse_field_name(f) for f in requested}
    invalid = top_level - LOAN_FIELDS
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


def _get_request_id(request) -> Optional[str]:
    """Extract request_id from request.state (set by RequestContextMiddleware)."""
    return getattr(getattr(request, "state", None), "request_id", None)


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
        except Exception as _exc:  # noqa: BLE001
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

        envelope = V2Envelope(
            data=items,
            meta=V2Meta(
                api_version="2.0",
                request_id=_get_request_id(request),
                cursor=next_cursor,
                has_more=has_more,
                total=total,
            ),
        ).model_dump(exclude_none=True)

        # Build pagination Link header (HATEOAS)
        headers = {}
        if next_cursor:
            filter_params = {}
            if stage:
                filter_params["stage"] = stage
            if loan_type:
                filter_params["loan_type"] = loan_type
            if loan_officer_id:
                filter_params["loan_officer_id"] = str(loan_officer_id)
            if q:
                filter_params["q"] = q
            if limit != 20:
                filter_params["limit"] = str(limit)
            link = build_pagination_link_header("/api/v2/loans", next_cursor, filter_params)
            if link:
                headers["Link"] = link

        return JSONResponse(content=envelope, headers=headers) if headers else envelope

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
        except Exception as _exc:  # noqa: BLE001
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
        # Build Link header before sparse filtering removes FK fields
        link_header = build_link_header("loan", item_dict)
        item_dict = apply_sparse_fields(item_dict, field_set)

        envelope = V2Envelope(
            data=item_dict,
            meta=V2Meta(
                api_version="2.0",
                request_id=_get_request_id(request),
            ),
        ).model_dump(exclude_none=True)

        headers = {}
        if link_header:
            headers["Link"] = link_header
        return JSONResponse(content=envelope, headers=headers)

    except Exception as exc:
        logger.exception("V2 get_loan failed")
        return _problem_response(ProblemDetail.internal_error(str(exc)))
    finally:
        db.close()


# ---------------------------------------------------------------------------
# POST /api/v2/loans — Create a loan
# ---------------------------------------------------------------------------

@router.post(
    "",
    summary="Create loan (V2)",
    status_code=201,
    response_description="Created loan in V2 envelope",
)
async def create_loan_v2(
    request: Request,
    body: V2LoanCreateRequest,
):
    """Create a new loan with V2 response envelope.

    Uses the same validation pipeline as V1 but returns the response
    wrapped in a V2Envelope with RFC 7807 errors.
    """
    from db import get_db
    from database.models import Loan
    from auth.dependencies import get_current_user_flexible

    db: Session = next(get_db())
    try:
        try:
            current_user = await get_current_user_flexible(request)
        except Exception as _exc:  # noqa: BLE001
            return _problem_response(ProblemDetail(
                type="https://api.perenniaai.com/problems/unauthorized",
                title="Unauthorized",
                status=401,
                detail="Valid authentication required",
            ))

        create_data = body.model_dump(exclude_unset=True)

        # Generate loan number if not provided
        loan_number = create_data.get("loan_number")
        if not loan_number:
            import uuid
            loan_number = f"LOAN-{uuid.uuid4().hex[:8].upper()}"

        # Check for duplicate loan number
        if create_data.get("loan_number"):
            existing = db.query(Loan).filter(
                Loan.loan_number == loan_number
            ).first()
            if existing:
                return _problem_response(ProblemDetail.bad_request(
                    f"Loan with number '{loan_number}' already exists",
                    errors=[{"field": "loan_number", "message": "duplicate loan number"}],
                ))

        # Build loan fields
        loan_fields = {
            "loan_number": loan_number,
            "borrower_name": create_data.get("borrower_name") or "Unknown Borrower",
            "borrower_email": create_data.get("borrower_email"),
            "stage": create_data.get("stage") or "APPLICATION",
            "loan_officer_id": current_user.id,
            "organization_id": getattr(current_user, "organization_id", None),
        }

        # Set loan officer name
        lo_name = getattr(current_user, "full_name", "") or ""
        if not lo_name:
            first = getattr(current_user, "first_name", "") or ""
            last = getattr(current_user, "last_name", "") or ""
            lo_name = f"{first} {last}".strip()
        if lo_name:
            loan_fields["loan_officer_name"] = lo_name

        # Optional fields
        for field in ("program", "loan_type", "amount", "purchase_price",
                       "down_payment", "rate", "term",
                       "property_address", "property_city",
                       "property_state", "property_zip"):
            if field in create_data and create_data[field] is not None:
                loan_fields[field] = create_data[field]

        # Default amount to 1.0 if not provided (conversion loans)
        if "amount" not in loan_fields or not loan_fields.get("amount"):
            loan_fields["amount"] = 1.0

        db_loan = Loan(**loan_fields)
        db.add(db_loan)
        db.commit()
        db.refresh(db_loan)

        logger.info(f"V2 loan created: {db_loan.loan_number} (ID: {db_loan.id})")

        item_dict = _loan_to_dict(db_loan)
        link_header = build_link_header("loan", item_dict)

        envelope = V2Envelope(
            data=item_dict,
            meta=V2Meta(
                api_version="2.0",
                request_id=_get_request_id(request),
            ),
        ).model_dump(exclude_none=True)

        headers = {}
        if link_header:
            headers["Link"] = link_header
        return JSONResponse(status_code=201, content=envelope, headers=headers)

    except Exception as exc:
        db.rollback()
        logger.exception("V2 create_loan failed")
        return _problem_response(ProblemDetail.internal_error(str(exc)))
    finally:
        db.close()


# ---------------------------------------------------------------------------
# PATCH /api/v2/loans/{loan_id} — Partial update
# ---------------------------------------------------------------------------

@router.patch(
    "/{loan_id}",
    summary="Update loan (V2)",
    response_description="Updated loan in V2 envelope",
)
async def update_loan_v2(
    request: Request,
    loan_id: int,
    body: V2LoanUpdateRequest,
):
    """Partially update a loan.

    Uses PATCH semantics: only provided fields are updated.
    Stage transitions are validated against the loan state machine.
    Use ``force_stage: true`` in the request body (admin only) to override.
    Returns RFC 7807 errors.
    """
    from db import get_db
    from database.models import Loan
    from auth.dependencies import get_current_user_flexible

    db: Session = next(get_db())
    try:
        try:
            current_user = await get_current_user_flexible(request)
        except Exception as _exc:  # noqa: BLE001
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

        update_data = body.model_dump(exclude_unset=True)
        force_stage = update_data.pop("force_stage", False)

        if not update_data:
            return _problem_response(ProblemDetail.bad_request(
                "No fields provided for update"
            ))

        # Validate stage transition if stage is being changed
        if "stage" in update_data and update_data["stage"]:
            old_stage = getattr(loan, "stage", "") or ""
            if hasattr(old_stage, "value"):
                old_stage = old_stage.value
            new_stage = update_data["stage"]

            try:
                from routes.loans_crud_routes import _validate_stage_transition
                user_role = getattr(current_user, "permission_role", None) or getattr(current_user, "role", None)
                transition_error = _validate_stage_transition(
                    current_stage=old_stage,
                    new_stage=new_stage,
                    user_role=user_role,
                    force=force_stage,
                )
                if transition_error:
                    return _problem_response(ProblemDetail.bad_request(
                        transition_error,
                        errors=[{"field": "stage", "message": transition_error}],
                    ))
            except ImportError:
                # Stage validation not available, allow the transition
                logger.warning("Could not import stage validation; allowing transition")

        # Apply updates (protect immutable fields)
        _protected = {"id", "organization_id", "created_at", "loan_officer_id", "loan_number"}
        for key, value in update_data.items():
            if key not in _protected and hasattr(loan, key):
                setattr(loan, key, value)

        loan.updated_at = datetime.now(timezone.utc)

        db.commit()
        db.refresh(loan)

        logger.info(f"V2 loan updated: {loan.loan_number} (ID: {loan.id})")

        item_dict = _loan_to_dict(loan)
        link_header = build_link_header("loan", item_dict)

        envelope = V2Envelope(
            data=item_dict,
            meta=V2Meta(
                api_version="2.0",
                request_id=_get_request_id(request),
            ),
        ).model_dump(exclude_none=True)

        headers = {}
        if link_header:
            headers["Link"] = link_header
        return JSONResponse(content=envelope, headers=headers)

    except Exception as exc:
        db.rollback()
        logger.exception("V2 update_loan failed")
        return _problem_response(ProblemDetail.internal_error(str(exc)))
    finally:
        db.close()
