"""
Scheduler A/B Testing Routes - Booking page optimization.

Endpoints:
  Authenticated (admin):
    - POST   /ab-tests                         Create A/B test
    - GET    /ab-tests                         List tests for org
    - GET    /ab-tests/{test_id}/results       Get results with statistical significance
    - PUT    /ab-tests/{test_id}/status        Activate/complete test

  Public (no auth):
    - GET    /public/ab-tests/assign/{booking_link_id}  Assign visitor to variant
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from datetime import datetime, timezone
from typing import Optional, List
from pydantic import BaseModel, Field
import html
import logging

try:
    import nh3
except ImportError:
    nh3 = None

from routes.scheduler._helpers import (
    get_current_user, get_models, _get_org_id, _is_scheduler_admin,
    _audit_log,
)
from db import get_db
from database.models.ab_test import ABTest, ABTestResult, ABTestStatus, ABTestElementType
from services.ab_test_service import ABTestService

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================================
# PYDANTIC SCHEMAS
# ============================================================================

class CreateABTestRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)
    element_type: str = Field(..., description="headline, cta_button, layout, or color_scheme")
    variant_a: dict = Field(..., description="Configuration for variant A")
    variant_b: dict = Field(..., description="Configuration for variant B")
    traffic_split: int = Field(50, ge=1, le=99, description="Percentage of traffic to variant A")
    start_date: Optional[str] = None
    end_date: Optional[str] = None


class UpdateStatusRequest(BaseModel):
    status: str = Field(..., description="draft, active, or completed")


class RecordEventRequest(BaseModel):
    test_id: int
    variant: str = Field(..., pattern="^[AB]$")
    visitor_id: str = Field(..., min_length=1, max_length=64)
    event_type: str = Field(..., description="impression or conversion")


# ============================================================================
# INPUT SANITIZATION
# ============================================================================

def _sanitize(value: Optional[str]) -> Optional[str]:
    """Strip HTML from user input."""
    if value is None:
        return None
    if nh3:
        return nh3.clean(value, tags=set())
    return html.escape(value)


def _parse_optional_datetime(value: Optional[str]) -> Optional[datetime]:
    """Parse an ISO datetime string or return None."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail=f"Invalid datetime format: {value}. Use ISO 8601.")


def _test_to_dict(test: ABTest) -> dict:
    """Serialize an ABTest to a JSON-safe dict."""
    return {
        "id": test.id,
        "organization_id": test.organization_id,
        "name": test.name,
        "description": test.description,
        "status": test.status,
        "element_type": test.element_type,
        "variant_a": test.variant_a,
        "variant_b": test.variant_b,
        "traffic_split": test.traffic_split,
        "start_date": test.start_date.isoformat() if test.start_date else None,
        "end_date": test.end_date.isoformat() if test.end_date else None,
        "created_at": test.created_at.isoformat() if test.created_at else None,
        "updated_at": test.updated_at.isoformat() if test.updated_at else None,
    }


# ============================================================================
# AUTHENTICATED ENDPOINTS
# ============================================================================

@router.post("/ab-tests")
async def create_ab_test(
    body: CreateABTestRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Create a new A/B test (admin only)."""
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    if not _is_scheduler_admin(user):
        raise HTTPException(status_code=403, detail="Admin access required")

    # Validate element type
    valid_types = [e.value for e in ABTestElementType]
    if body.element_type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid element_type. Must be one of: {', '.join(valid_types)}",
        )

    # Check for active test on same element type (only one active per element type per org)
    existing_active = db.query(ABTest).filter(
        ABTest.organization_id == org_id,
        ABTest.element_type == body.element_type,
        ABTest.status == ABTestStatus.ACTIVE.value,
    ).first()

    if existing_active:
        raise HTTPException(
            status_code=409,
            detail=f"An active A/B test already exists for element type '{body.element_type}'. "
                   f"Complete or delete test '{existing_active.name}' first.",
        )

    test = ABTest(
        organization_id=org_id,
        name=_sanitize(body.name),
        description=_sanitize(body.description),
        element_type=body.element_type,
        variant_a=body.variant_a,
        variant_b=body.variant_b,
        traffic_split=body.traffic_split,
        start_date=_parse_optional_datetime(body.start_date),
        end_date=_parse_optional_datetime(body.end_date),
        status=ABTestStatus.DRAFT.value,
    )
    db.add(test)
    db.flush()

    _audit_log(
        db, org_id, user.id, "ab_test_created", "ab_test",
        entity_id=test.id,
        changes={"name": test.name, "element_type": test.element_type},
        request=request,
    )
    db.commit()

    return {
        "success": True,
        "test": _test_to_dict(test),
        "message": f"A/B test '{test.name}' created",
    }


@router.get("/ab-tests")
async def list_ab_tests(
    request: Request,
    status: Optional[str] = Query(None, description="Filter by status: draft, active, completed"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """List A/B tests for the organization."""
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    query = db.query(ABTest).filter(ABTest.organization_id == org_id)

    if status:
        valid_statuses = [s.value for s in ABTestStatus]
        if status not in valid_statuses:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}",
            )
        query = query.filter(ABTest.status == status)

    total = query.count()
    tests = query.order_by(ABTest.created_at.desc()).offset(offset).limit(limit).all()

    # Fetch summary stats for each test
    test_ids = [t.id for t in tests]
    stats = {}
    if test_ids:
        from sqlalchemy import func
        stat_rows = db.query(
            ABTestResult.ab_test_id,
            func.sum(ABTestResult.impressions).label("total_impressions"),
            func.sum(ABTestResult.bookings).label("total_bookings"),
        ).filter(
            ABTestResult.ab_test_id.in_(test_ids),
        ).group_by(ABTestResult.ab_test_id).all()

        for row in stat_rows:
            stats[row.ab_test_id] = {
                "total_impressions": int(row.total_impressions or 0),
                "total_bookings": int(row.total_bookings or 0),
            }

    results = []
    for test in tests:
        test_dict = _test_to_dict(test)
        test_stats = stats.get(test.id, {"total_impressions": 0, "total_bookings": 0})
        test_dict["total_impressions"] = test_stats["total_impressions"]
        test_dict["total_bookings"] = test_stats["total_bookings"]
        results.append(test_dict)

    return {
        "tests": results,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/ab-tests/{test_id}/results")
async def get_ab_test_results(
    test_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """Get detailed results with statistical significance for an A/B test."""
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    # Verify test belongs to org
    test = db.query(ABTest).filter(
        ABTest.id == test_id,
        ABTest.organization_id == org_id,
    ).first()
    if not test:
        raise HTTPException(status_code=404, detail=f"A/B test {test_id} not found")

    service = ABTestService(db)

    try:
        results = service.calculate_results(test_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    # Add test config to results
    results["test_config"] = _test_to_dict(test)

    return {"success": True, "results": results}


@router.put("/ab-tests/{test_id}/status")
async def update_ab_test_status(
    test_id: int,
    body: UpdateStatusRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Activate or complete an A/B test (admin only)."""
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    if not _is_scheduler_admin(user):
        raise HTTPException(status_code=403, detail="Admin access required")

    test = db.query(ABTest).filter(
        ABTest.id == test_id,
        ABTest.organization_id == org_id,
    ).first()
    if not test:
        raise HTTPException(status_code=404, detail=f"A/B test {test_id} not found")

    valid_statuses = [s.value for s in ABTestStatus]
    if body.status not in valid_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}",
        )

    # Validate status transitions
    old_status = test.status
    new_status = body.status

    valid_transitions = {
        ABTestStatus.DRAFT.value: [ABTestStatus.ACTIVE.value],
        ABTestStatus.ACTIVE.value: [ABTestStatus.COMPLETED.value],
        ABTestStatus.COMPLETED.value: [],  # Terminal state
    }

    allowed = valid_transitions.get(old_status, [])
    if new_status not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot transition from '{old_status}' to '{new_status}'. "
                   f"Allowed transitions: {', '.join(allowed) if allowed else 'none (terminal state)'}",
        )

    # If activating, check no other active test for same element type
    if new_status == ABTestStatus.ACTIVE.value:
        existing_active = db.query(ABTest).filter(
            ABTest.organization_id == org_id,
            ABTest.element_type == test.element_type,
            ABTest.status == ABTestStatus.ACTIVE.value,
            ABTest.id != test_id,
        ).first()
        if existing_active:
            raise HTTPException(
                status_code=409,
                detail=f"Another active test exists for '{test.element_type}': '{existing_active.name}'",
            )
        test.start_date = test.start_date or datetime.now(timezone.utc)

    if new_status == ABTestStatus.COMPLETED.value:
        test.end_date = test.end_date or datetime.now(timezone.utc)

    test.status = new_status

    _audit_log(
        db, org_id, user.id, "ab_test_status_changed", "ab_test",
        entity_id=test.id,
        changes={"old_status": old_status, "new_status": new_status},
        request=request,
    )
    db.commit()

    return {
        "success": True,
        "test": _test_to_dict(test),
        "message": f"A/B test status changed from '{old_status}' to '{new_status}'",
    }


# ============================================================================
# PUBLIC ENDPOINTS (no auth required)
# ============================================================================

@router.get("/public/ab-tests/assign/{booking_link_id}")
async def public_assign_variant(
    booking_link_id: int,
    visitor_id: str = Query(..., min_length=1, max_length=64),
    request: Request = None,
    db: Session = Depends(get_db),
):
    """Assign a visitor to A/B test variants for a booking link's org.

    Returns all active test assignments for the organization. The visitor_id
    should be a stable identifier (cookie, browser fingerprint) so returning
    visitors see consistent variants.

    This endpoint is public and does not require authentication.
    """
    models = get_models()
    BookingLink = models.get("BookingLink") if models else None

    if not BookingLink:
        raise HTTPException(status_code=503, detail="Booking system not available")

    # Look up the booking link to find the org
    link = db.query(BookingLink).filter(BookingLink.id == booking_link_id).first()
    if not link:
        raise HTTPException(status_code=404, detail="Booking link not found")

    org_id = link.organization_id

    # Get all active tests for this org
    active_tests = db.query(ABTest).filter(
        ABTest.organization_id == org_id,
        ABTest.status == ABTestStatus.ACTIVE.value,
    ).all()

    if not active_tests:
        return {
            "assignments": [],
            "message": "No active A/B tests",
        }

    service = ABTestService(db)

    assignments = []
    for test in active_tests:
        variant = service.assign_variant(test.id, visitor_id)
        service.record_impression(test.id, variant, visitor_id)

        variant_config = test.variant_a if variant == "A" else test.variant_b

        assignments.append({
            "test_id": test.id,
            "element_type": test.element_type,
            "variant": variant,
            "config": variant_config,
        })

    db.commit()

    return {
        "assignments": assignments,
        "visitor_id": visitor_id,
    }


@router.post("/public/ab-tests/record")
async def public_record_event(
    body: RecordEventRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Record an impression or conversion event for an A/B test.

    This endpoint is public and does not require authentication.
    Used by the booking page frontend to track visitor interactions.
    """
    service = ABTestService(db)

    # Verify test exists and is active
    test = db.query(ABTest).filter(
        ABTest.id == body.test_id,
        ABTest.status == ABTestStatus.ACTIVE.value,
    ).first()
    if not test:
        raise HTTPException(status_code=404, detail="Active A/B test not found")

    try:
        if body.event_type == "impression":
            service.record_impression(body.test_id, body.variant, body.visitor_id)
        elif body.event_type == "conversion":
            service.record_conversion(body.test_id, body.variant, body.visitor_id)
        else:
            raise HTTPException(
                status_code=400,
                detail="event_type must be 'impression' or 'conversion'",
            )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    db.commit()

    return {"success": True, "event_type": body.event_type}
