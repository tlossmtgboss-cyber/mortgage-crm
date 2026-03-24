"""
Scheduler Survey Routes - Post-appointment survey system.

Endpoints:
  Authenticated:
    - POST  /surveys/send/{appointment_id}    Send survey email for a completed appointment
    - GET   /surveys/results                  Aggregate survey results for the org
    - GET   /surveys/results/{lo_id}          Survey results for a specific LO

  Public (token-based, no auth):
    - GET   /public/surveys/respond/{token}   Retrieve survey form data
    - POST  /public/surveys/respond/{token}   Submit survey response
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel, Field
import logging

from routes.scheduler._helpers import get_current_user, _get_org_id, _audit_log, _check_rate_limit, _sanitize_public_error
from db import get_db
from middleware.feature_gate import require_feature_tier
from services.survey_service import AppointmentSurveyService  # noqa: F401 — also used by test patches

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================================
# PYDANTIC SCHEMAS
# ============================================================================

class SurveyResponseBody(BaseModel):
    overall_rating: int = Field(..., ge=1, le=5, description="Overall experience rating 1-5")
    communication_rating: int = Field(..., ge=1, le=5, description="Communication quality 1-5")
    knowledge_rating: int = Field(..., ge=1, le=5, description="Knowledge & expertise 1-5")
    feedback_text: Optional[str] = Field(None, max_length=5000, description="Free-text feedback")
    would_recommend: Optional[bool] = Field(None, description="Would you recommend this LO?")


# ============================================================================
# SEND SURVEY (authenticated)
# ============================================================================

@router.post("/surveys/send/{appointment_id}", status_code=201)
@require_feature_tier("scheduler_surveys")
async def send_survey(
    appointment_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Send a post-appointment survey email to the borrower.

    Requires authentication. Creates a survey record with a secure token
    and emails the borrower a link to the survey form.
    """
    from services.survey_service import AppointmentSurveyService

    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    service = AppointmentSurveyService(db)
    result = service.create_and_send_survey(
        appointment_id=appointment_id,
        organization_id=org_id,
        lo_user_id=getattr(user, "id", None),
    )

    if not result.get("success"):
        error_msg = result.get("error", "Failed to send survey")
        status = 409 if "already sent" in error_msg.lower() else 400
        raise HTTPException(status_code=status, detail=error_msg)

    _audit_log(
        db, org_id, getattr(user, "id", None), "created",
        "appointment_survey", result.get("survey_id"),
        changes={"appointment_id": appointment_id},
        request=request,
    )
    db.commit()

    return {
        "success": True,
        "survey_id": result["survey_id"],
        "email_sent": result.get("email_sent", False),
        "survey_url": result.get("survey_url"),
        "expires_at": result.get("expires_at"),
    }


# ============================================================================
# PUBLIC: GET SURVEY FORM (token-based, no auth)
# ============================================================================

@router.get("/public/surveys/respond/{token}")
async def get_survey_form(
    token: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Public endpoint: retrieve survey form data by token.

    No authentication required. The token itself serves as authorization.
    Returns survey metadata needed to render the form, or status if
    the survey is expired/completed.
    """
    await _check_rate_limit(request, max_requests=30)
    from services.survey_service import AppointmentSurveyService

    if not token or len(token) < 20:
        raise HTTPException(status_code=400, detail=_sanitize_public_error(400, "Invalid survey token"))

    service = AppointmentSurveyService(db)
    result = service.get_survey_by_token(token)

    if result is None:
        raise HTTPException(status_code=404, detail=_sanitize_public_error(404, "Survey not found"))

    if result.get("expired"):
        return {
            "status": "expired",
            "message": "This survey has expired. Thank you for your interest.",
        }

    if result.get("completed"):
        return {
            "status": "completed",
            "message": "This survey has already been submitted. Thank you for your feedback!",
        }

    return {
        "status": "active",
        "borrower_name": result.get("borrower_name"),
        "lo_name": result.get("lo_name"),
    }


# ============================================================================
# PUBLIC: SUBMIT SURVEY RESPONSE (token-based, no auth)
# ============================================================================

@router.post("/public/surveys/respond/{token}")
async def submit_survey_response(
    token: str,
    body: SurveyResponseBody,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Public endpoint: submit survey response.

    No authentication required. The token itself serves as authorization.
    Records the borrower's ratings and feedback.
    """
    await _check_rate_limit(request, max_requests=15)
    from services.survey_service import AppointmentSurveyService

    if not token or len(token) < 20:
        raise HTTPException(status_code=400, detail=_sanitize_public_error(400, "Invalid survey token"))

    # Duplicate submission guard: reject if this survey was already completed.
    # This is checked again inside submit_response() under a row lock, but
    # doing it here avoids unnecessary processing for obvious duplicates.
    service = AppointmentSurveyService(db)
    existing = service.get_survey_by_token(token)
    if existing and existing.get("completed"):
        return {
            "success": True,
            "message": "Survey response already recorded. Thank you for your feedback!",
        }

    result = service.submit_response(
        token=token,
        overall_rating=body.overall_rating,
        communication_rating=body.communication_rating,
        knowledge_rating=body.knowledge_rating,
        feedback_text=body.feedback_text,
        would_recommend=body.would_recommend,
    )

    if not result.get("success"):
        error_msg = result.get("error", "Failed to submit survey")
        if "expired" in error_msg.lower():
            status = 410  # Gone
        elif "already" in error_msg.lower():
            status = 409  # Conflict
        elif "not found" in error_msg.lower():
            status = 404
        else:
            status = 400
        raise HTTPException(status_code=status, detail=_sanitize_public_error(status, error_msg))

    db.commit()

    return {
        "success": True,
        "message": result.get("message", "Thank you for your feedback!"),
    }


# ============================================================================
# AGGREGATE RESULTS (authenticated)
# ============================================================================

@router.get("/surveys/results")
@require_feature_tier("scheduler_surveys")
async def get_survey_results(
    request: Request,
    days: int = Query(90, ge=1, le=365, description="Lookback period in days"),
    db: Session = Depends(get_db),
):
    """
    Get aggregate survey results for the organization.

    Returns average ratings, NPS score, response rate, and recent feedback.
    """
    from services.survey_service import AppointmentSurveyService

    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    service = AppointmentSurveyService(db)
    scores = service.get_aggregate_scores(org_id, days=days)

    # Also include per-LO breakdown
    lo_breakdown = service.get_lo_breakdown(org_id, days=days)

    return {
        **scores,
        "lo_breakdown": lo_breakdown,
    }


# ============================================================================
# PER-LO RESULTS (authenticated)
# ============================================================================

@router.get("/surveys/results/{lo_id}")
@require_feature_tier("scheduler_surveys")
async def get_lo_survey_results(
    lo_id: int,
    request: Request,
    days: int = Query(90, ge=1, le=365, description="Lookback period in days"),
    db: Session = Depends(get_db),
):
    """
    Get survey results for a specific loan officer.

    Returns their average ratings, NPS, and recent feedback.
    """
    from services.survey_service import AppointmentSurveyService

    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    service = AppointmentSurveyService(db)
    scores = service.get_aggregate_scores(org_id, lo_user_id=lo_id, days=days)

    return scores
