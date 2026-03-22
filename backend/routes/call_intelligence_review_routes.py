"""
API Routes for Call Intelligence Review Queue

Provides endpoints for human review of low-confidence extractions.

Endpoints:
- GET /api/call-intelligence/reviews - List pending reviews
- GET /api/call-intelligence/reviews/{review_id} - Get single review
- POST /api/call-intelligence/reviews/{review_id}/decision - Submit decision
- GET /api/call-intelligence/reviews/stats - Get review statistics
- GET /api/call-intelligence/reviews/loan/{loan_id} - Get reviews for a loan
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/call-intelligence/reviews",
    tags=["call-intelligence", "reviews"],
)


# =============================================================================
# Request/Response Models
# =============================================================================

class ReviewDecisionRequest(BaseModel):
    """Request to submit a review decision."""
    decision: str = Field(..., description="Decision: approved, rejected, or modified")
    final_value: Optional[Any] = Field(None, description="Corrected value (required for 'modified')")
    notes: Optional[str] = Field(None, description="Reviewer notes")


class ReviewItemResponse(BaseModel):
    """Response model for a review item."""
    review_id: str
    call_id: str
    loan_id: Optional[int]
    extraction_type: str
    field_name: str
    extracted_value: Any
    confidence_score: float
    source_text: str
    status: str
    reviewed_by: Optional[int] = None
    reviewed_at: Optional[str] = None
    reviewer_notes: Optional[str] = None
    final_value: Optional[Any] = None
    created_at: str

    class Config:
        from_attributes = True


class ReviewStatsResponse(BaseModel):
    """Response model for review statistics."""
    total_pending: int
    total_approved: int
    total_rejected: int
    total_modified: int
    by_extraction_type: Dict[str, int]
    by_priority: Dict[str, int]
    avg_review_time_hours: float
    oldest_pending_hours: float


class ReviewDecisionResponse(BaseModel):
    """Response after submitting a review decision."""
    success: bool
    review_id: str
    decision: str
    message: str
    updated_loan_field: bool
    errors: List[str] = []


class ReviewListResponse(BaseModel):
    """Response for list of reviews."""
    items: List[ReviewItemResponse]
    total: int
    page: int
    page_size: int
    has_more: bool


# =============================================================================
# Dependencies (injected from main app via set_dependencies)
# =============================================================================

from database import get_db

_get_current_user = None


def set_dependencies(user_dependency):
    """Store reference to main app's get_current_user dependency."""
    global _get_current_user
    _get_current_user = user_dependency


async def get_current_user(request: Request, db=Depends(get_db)):
    """Current user dependency - delegates to main app's auth."""
    auth_header = request.headers.get("Authorization", "")
    token = auth_header[7:] if auth_header.startswith("Bearer ") else ""

    if not token:
        raise HTTPException(status_code=401, detail="Could not validate credentials")

    if _get_current_user is None:
        raise HTTPException(status_code=503, detail="Authentication service not initialized")

    return await _get_current_user(token=token, request=request, db=db)


def get_review_service(db=Depends(get_db)):
    """Get review service instance."""
    from services.call_intelligence import HumanReviewService
    return HumanReviewService(db)


# =============================================================================
# Routes
# =============================================================================

@router.get("", response_model=ReviewListResponse)
async def list_pending_reviews(
    loan_id: Optional[int] = Query(None, description="Filter by loan ID"),
    extraction_type: Optional[str] = Query(None, description="Filter by extraction type"),
    status: str = Query("pending", description="Filter by status"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    service: Any = Depends(get_review_service),
    current_user: dict = Depends(get_current_user),
):
    """
    List reviews with optional filters.

    Returns paginated list of review items sorted by priority
    (lowest confidence first).
    """
    offset = (page - 1) * page_size
    org_id = current_user.get("organization_id") or current_user.get("org_id")

    try:
        items = await service.get_pending_reviews(
            loan_id=loan_id,
            extraction_type=extraction_type,
            limit=page_size + 1,  # Get one extra to check has_more
            offset=offset,
            organization_id=org_id,
        )

        has_more = len(items) > page_size
        if has_more:
            items = items[:page_size]

        return ReviewListResponse(
            items=[ReviewItemResponse(**item.to_dict()) for item in items],
            total=len(items),  # Would be actual count from DB
            page=page,
            page_size=page_size,
            has_more=has_more,
        )

    except Exception as e:
        logger.exception("Failed to list reviews")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/stats", response_model=ReviewStatsResponse)
async def get_review_stats(
    loan_id: Optional[int] = Query(None, description="Filter by loan ID"),
    days: int = Query(30, ge=1, le=365, description="Days to include"),
    service: Any = Depends(get_review_service),
    current_user: dict = Depends(get_current_user),
):
    """
    Get review queue statistics.

    Returns counts of pending, approved, rejected, and modified reviews,
    plus breakdown by extraction type.
    """
    org_id = current_user.get("organization_id") or current_user.get("org_id")
    try:
        stats = await service.get_stats(loan_id=loan_id, days=days, organization_id=org_id)
        return ReviewStatsResponse(**stats.to_dict())

    except Exception as e:
        logger.exception("Failed to get review stats")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/loan/{loan_id}", response_model=ReviewListResponse)
async def get_reviews_for_loan(
    loan_id: int,
    status: Optional[str] = Query(None, description="Filter by status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    service: Any = Depends(get_review_service),
    current_user: dict = Depends(get_current_user),
):
    """
    Get all reviews for a specific loan.

    Returns all reviews (pending and completed) for the given loan.
    """
    offset = (page - 1) * page_size
    org_id = current_user.get("organization_id") or current_user.get("org_id")

    try:
        items = await service.get_pending_reviews(
            loan_id=loan_id,
            limit=page_size + 1,
            offset=offset,
            organization_id=org_id,
        )

        has_more = len(items) > page_size
        if has_more:
            items = items[:page_size]

        return ReviewListResponse(
            items=[ReviewItemResponse(**item.to_dict()) for item in items],
            total=len(items),
            page=page,
            page_size=page_size,
            has_more=has_more,
        )

    except Exception as e:
        logger.exception(f"Failed to get reviews for loan {loan_id}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{review_id}", response_model=ReviewItemResponse)
async def get_review(
    review_id: str,
    service: Any = Depends(get_review_service),
    current_user: dict = Depends(get_current_user),
):
    """
    Get a single review item by ID.

    Returns full details including source text and any previous
    review attempts.
    """
    org_id = current_user.get("organization_id") or current_user.get("org_id")
    try:
        item = await service.get_review(review_id, organization_id=org_id)

        if not item:
            raise HTTPException(status_code=404, detail=f"Review {review_id} not found")

        return ReviewItemResponse(**item.to_dict())

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get review {review_id}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{review_id}/decision", response_model=ReviewDecisionResponse)
async def submit_review_decision(
    review_id: str,
    request: ReviewDecisionRequest,
    service: Any = Depends(get_review_service),
    current_user: dict = Depends(get_current_user),
):
    """
    Submit a review decision.

    Decisions:
    - approved: Accept the extracted value as-is
    - rejected: Mark extraction as incorrect (won't be used)
    - modified: Accept with a corrected value (requires final_value)

    Returns confirmation with updated status.
    """
    # Validate decision
    valid_decisions = ["approved", "rejected", "modified"]
    if request.decision not in valid_decisions:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid decision. Must be one of: {valid_decisions}"
        )

    if request.decision == "modified" and request.final_value is None:
        raise HTTPException(
            status_code=400,
            detail="final_value is required for 'modified' decision"
        )

    org_id = current_user.get("organization_id") or current_user.get("org_id")
    try:
        result = await service.submit_review(
            review_id=review_id,
            decision=request.decision,
            reviewer_id=current_user["id"],
            final_value=request.final_value,
            notes=request.notes,
            organization_id=org_id,
        )

        if not result.success:
            raise HTTPException(
                status_code=400,
                detail=result.errors[0] if result.errors else "Review submission failed"
            )

        return ReviewDecisionResponse(**result.to_dict())

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to submit review for {review_id}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/bulk/decision", response_model=Dict[str, Any])
async def submit_bulk_decisions(
    decisions: List[Dict[str, Any]],
    service: Any = Depends(get_review_service),
    current_user: dict = Depends(get_current_user),
):
    """
    Submit multiple review decisions at once.

    Each item in decisions should have:
    - review_id: str
    - decision: str (approved/rejected/modified)
    - final_value: Optional[Any] (required for modified)
    - notes: Optional[str]

    Returns summary of results.
    """
    results = {
        "total": len(decisions),
        "succeeded": 0,
        "failed": 0,
        "errors": [],
    }

    org_id = current_user.get("organization_id") or current_user.get("org_id")
    for item in decisions:
        try:
            result = await service.submit_review(
                review_id=item["review_id"],
                decision=item["decision"],
                reviewer_id=current_user["id"],
                final_value=item.get("final_value"),
                notes=item.get("notes"),
                organization_id=org_id,
            )

            if result.success:
                results["succeeded"] += 1
            else:
                results["failed"] += 1
                results["errors"].append({
                    "review_id": item["review_id"],
                    "error": result.errors[0] if result.errors else "Unknown error",
                })

        except Exception as e:
            results["failed"] += 1
            results["errors"].append({
                "review_id": item.get("review_id", "unknown"),
                "error": "Internal server error",
            })

    return results


@router.get("/call/{call_id}", response_model=List[ReviewItemResponse])
async def get_reviews_for_call(
    call_id: str,
    service: Any = Depends(get_review_service),
    current_user: dict = Depends(get_current_user),
):
    """
    Get all reviews for a specific call.

    Returns all reviews associated with the given call ID.
    """
    org_id = current_user.get("organization_id") or current_user.get("org_id")
    try:
        items = await service.get_reviews_for_call(call_id, organization_id=org_id)
        return [ReviewItemResponse(**item.to_dict()) for item in items]

    except Exception as e:
        logger.exception(f"Failed to get reviews for call {call_id}")
        raise HTTPException(status_code=500, detail="Internal server error")
